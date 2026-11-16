"""Confirm and independently review a historical investment decision."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from .decision_evidence import evidence_context, exposure_bounds
from .decision_funding import search_funding, verify_funding
from .decision_market import prepare_market
from .decision_release import review_binding, seal_report
from .decision_replay import evaluate, stress_percentile, verify, verify_stress_percentile


ACTIONS = ("compare", "evaluate", "audit")
PRIORITIES = {
    "terminal_return": "Highest terminal return",
    "terminal_loss": "Lowest terminal loss",
    "max_drawdown": "Lowest maximum drawdown",
    "annualized_volatility": "Lowest annualized volatility",
    "recovery_days": "Shortest observed recovery",
}
RISK_METRICS = ("terminal_loss", "max_drawdown", "worst_rolling_12m", "recovery_days")
SCOPE_FIELDS = ("knowledge_date", "custom_start", "custom_end", "include_2023",
                "upload_source", "upload_published_on", "upload_sha256")
METHODS = {"market": "decision-cad-v1", "replay": "decision-buy-hold-v1",
           "rules": "decision-policy-v1", "exposures": "decision-exposure-v1",
           "funding": "decision-funding-v1", "amounts": "decision-capital-amounts-v1"}
_TOLERANCE = 1e-10


def _encode(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class ConfirmedDecision:
    """A detached snapshot of the terms the user confirmed."""

    _body: str
    _trace: str

    @property
    def data(self):
        return json.loads(self._body)

    @property
    def id(self):
        return _digest(self._body)

    @property
    def trace(self):
        return json.loads(self._trace)


@dataclass(frozen=True)
class FundingAuthorization:
    decision_id: str
    sources: tuple[str, ...]
    allow_smaller: bool


def _number(value, label, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum)):
        raise ValueError(f"{label} is outside its supported range.")
    return float(value)


def _symbol(value):
    if not isinstance(value, str):
        raise ValueError("Enter a valid ticker symbol.")
    symbol = value.strip().upper()
    if not symbol or len(symbol) > 32 or not symbol[0].isalnum() or not all(
        character.isascii() and (character.isalnum() or character in ".-^=") for character in symbol
    ):
        raise ValueError("Enter a valid ticker symbol.")
    return symbol


def _portfolios(raw, action):
    if len(raw) != (2 if action == "compare" else 1):
        raise ValueError("Confirm two complete allocations for comparison or one starting allocation for this action.")
    portfolios = []
    for entry in raw:
        label = entry.get("label", "").strip()
        weights = {}
        for ticker, weight in entry.get("weights", {}).items():
            ticker = _symbol(ticker)
            if ticker in weights:
                raise ValueError("Each ticker may appear only once per allocation.")
            weights[ticker] = _number(weight, "Allocation weight", 1)
        if not label or len(label) > 80 or len(weights) > 50 or not math.isclose(
            math.fsum(weights.values()), 1, abs_tol=_TOLERANCE, rel_tol=0
        ):
            raise ValueError("Give each allocation a name and enter weights that sum to 100%.")
        portfolios.append({"label": label, "weights": {ticker: weight for ticker, weight in weights.items() if weight}})
    if len({item["label"] for item in portfolios}) != len(portfolios):
        raise ValueError("Use a different label for each allocation.")
    return portfolios


def _limits(draft):
    limits = []
    for item in draft.get("risk_limits", ()):
        metric, windows = item.get("metric"), item.get("windows", "default")
        if not isinstance(metric, str) or not metric:
            raise ValueError("Name the metric for every risk limit.")
        if isinstance(windows, list):
            if not windows or any(not isinstance(name, str) for name in windows) or len(set(windows)) != len(windows):
                raise ValueError("Select a valid set of windows for each risk limit.")
        elif windows not in ("default", "all"):
            if not isinstance(windows, str) or not windows:
                raise ValueError("Select a valid window for each risk limit.")
            windows = [windows]
        cap = _number(item.get("cap"), "Risk limit", None if metric == "recovery_days" else 1)
        if metric == "recovery_days" and not cap.is_integer():
            raise ValueError("A recovery-day limit must use a whole number of calendar days.")
        limits.append({"metric": metric, "cap": cap, "windows": windows, "excerpt": item.get("excerpt", "")})
    return limits


def _constraints(draft):
    output = []
    for item in draft.get("constraints", ()):
        selector = item.get("asset_set", {})
        if not isinstance(selector, Mapping) or len(selector) != 1:
            raise ValueError("Each asset rule needs exactly one asset group.")
        axis, subject = next(iter(selector.items()))
        if axis == "symbols":
            if not isinstance(subject, (tuple, list)) or not subject:
                raise ValueError("A holdings rule requires at least one ticker.")
            subject = sorted({_symbol(ticker) for ticker in subject})
        elif not isinstance(subject, str) or not subject.strip():
            raise ValueError("Specify which class, issuer, sector, or exclusion list the rule applies to.")
        low, high = item.get("min"), item.get("max")
        low = _number(low, "Minimum exposure", 1) if low is not None else None
        high = _number(high, "Maximum exposure", 1) if high is not None else None
        if (low is None and high is None) or (low is not None and high is not None and low > high):
            raise ValueError("Enter a consistent minimum or maximum exposure.")
        output.append({"asset_set": {axis: subject}, "min": low, "max": high, "excerpt": item.get("excerpt", "")})
    return output


def _trade(raw, portfolio):
    symbol, source = _symbol(raw.get("symbol")), _symbol(raw.get("source"))
    unit = raw.get("unit")
    if unit not in {"percentage_points", "percent", "fraction", "shares", "amount_cad"}:
        raise ValueError("Confirm the purchase in percentage points, in shares, or as a CAD amount.")
    quantity = _number(raw.get("quantity"), "Purchase size", 1 if unit == "fraction" else 100 if
                       unit in ("percent", "percentage_points") else None)
    if source == symbol or source not in portfolio["weights"] or not quantity:
        raise ValueError("Select a positive purchase amount and a different existing holding to sell.")
    result = {"symbol": symbol, "source": source, "quantity": quantity, "unit": unit}
    if unit in {"shares", "amount_cad"}:
        result["portfolio_value_cad"] = _number(raw.get("portfolio_value_cad"), "Portfolio value in CAD")
        if not result["portfolio_value_cad"]:
            raise ValueError("Confirm the starting portfolio value in CAD to use a share count or amount.")
    return result


def confirm_decision(draft, *, scope=None):
    """Validate confirmed material terms. Model hints alone never run the engine."""
    action = draft.get("intent")
    if action not in ACTIONS:
        raise ValueError("Choose Compare, Evaluate, or Audit.")
    if draft.get("missing"):
        raise ValueError("Resolve the remaining information before confirming.")
    portfolios = _portfolios(draft.get("portfolios", ()), action)
    priority = draft.get("priority")
    if priority is not None and (action != "compare" or priority not in PRIORITIES):
        raise ValueError("Select an available comparison metric.")
    scope = scope or {}
    assumption_kind = draft.get("assumption_kind", "user_defined")
    if assumption_kind not in {"user_defined", "team_defined"}:
        raise ValueError("Identify whether the confirmed rules came from the user or a team example.")
    capital = draft.get("capital")
    if capital is not None:
        if not isinstance(capital, Mapping) or capital.get("currency") != "CAD":
            raise ValueError("Confirm a starting portfolio value in CAD.")
        capital = {"value": _number(capital.get("value"), "Starting portfolio value"), "currency": "CAD"}
        if not capital["value"]:
            raise ValueError("The starting portfolio value must be positive.")
    body = {
        "intent": action, "portfolios": portfolios,
        "constraints": _constraints(draft), "risk_limits": _limits(draft), "priority": priority,
        "ranking_window": draft.get("ranking_window") if priority else None,
        "trade": _trade(draft.get("trade") or {}, portfolios[0]) if action == "audit" else None,
        "scope": {key: scope[key] for key in SCOPE_FIELDS if key in scope},
        "profile": {key: value for key, value in (draft.get("profile") or {}).items() if key in {
            "objective", "horizon_years", "withdrawal_time", "risk_tolerance", "esg", "esg_screen",
            "finance_literacy", "method_literacy", "task_goal", "view", "preset",
        }},
        "origin": draft.get("origin", "user_defined"),
        "capital": capital,
        "assumption_kind": assumption_kind,
    }
    if body["trade"] and body["trade"].get("portfolio_value_cad") is not None:
        trade_capital = body["trade"]["portfolio_value_cad"]
        if capital is not None and capital["value"] != trade_capital:
            raise ValueError("The purchase conversion and report must use the same confirmed capital.")
        body["capital"] = {"value": trade_capital, "currency": "CAD"}
    return ConfirmedDecision(_encode(body), _encode(draft.get("trace", ())))


def authorize_funding(confirmed, *, sources, allow_smaller=False):
    if not isinstance(confirmed, ConfirmedDecision) or confirmed.data["intent"] != "audit":
        raise ValueError("First confirm the original audit.")
    data = confirmed.data
    source_symbols = tuple(dict.fromkeys(_symbol(source) for source in sources))
    if (type(allow_smaller) is not bool or not source_symbols
            or not set(source_symbols) <= data["portfolios"][0]["weights"].keys()
            or data["trade"]["symbol"] in source_symbols):
        raise ValueError("Choose one or more existing holdings as approved funding sources.")
    return FundingAuthorization(confirmed.id, source_symbols, allow_smaller)


def _selected_windows(limit, available, excluded):
    requested = limit["windows"]
    if requested == "default":
        return ["2022", "2025"]
    if requested == "all":
        return sorted(set(available) | set(excluded))
    return requested


def _risk_value(metrics, name):
    if name == "worst_rolling_12m":
        worst = metrics["rolling"]["12m"]["worst_return"]
        return None if worst is None else max(0.0, -worst)
    return metrics.get(name) if name in RISK_METRICS else None


def _candidate_rules(candidate, options, data, context, gaps, exposures):
    rules = []
    weights = options[candidate]["weights"]
    windows = options[candidate]["windows"]
    for idx, rule in enumerate(data["constraints"], start=1):
        axis, subject = next(iter(rule["asset_set"].items()))
        supported = axis in {"symbols", "issuer", "sector", "asset_class", "exclusion_list"}
        label = f"{axis.replace('_', ' ').title()} · {', '.join(subject) if isinstance(subject, list) else subject}"
        if axis == "symbols":
            lower = upper = math.fsum(weights.get(ticker, 0) for ticker in subject)
            sources = []
        elif context is not None and axis in {"issuer", "sector", "asset_class", "exclusion_list"}:
            bound = exposure_bounds(weights, context, "controversy" if axis == "exclusion_list" else axis, subject)
            sources = sorted({row["source_id"] for row in bound.get("coefficients", {}).values() if row.get("source_id")})
            lower, upper = bound["lower"], bound["upper"]
            exposures.append({"candidate": candidate, "axis": axis, "subject": subject, **bound})
        else:
            lower, upper, sources = 0.0, 1.0, []
        for key, boundary, extreme in (("min", lower, upper), ("max", upper, lower)):
            limit = rule[key]
            if limit is None:
                continue
            slack = (boundary - limit) if key == "min" else (limit - boundary)
            possible_slack = (extreme - limit) if key == "min" else (limit - extreme)
            state = ("pass" if slack >= -_TOLERANCE else "fail" if possible_slack < -_TOLERANCE else "unknown") if supported else "unknown"
            rules.append({"id": f"exposure-{idx}-{key}", "candidate": candidate, "label": f"{label} {key}",
                          "lower": lower, "upper": upper, "limit": limit, "status": state,
                          "headroom": slack if state != "unknown" else None, "source_ids": sources, "unit": "fraction"})
    for idx, limit in enumerate(data["risk_limits"], start=1):
        metric, cap = limit["metric"], limit["cap"]
        for window in _selected_windows(limit, windows, gaps):
            values = windows.get(window)
            actual = _risk_value(values, metric) if values else None
            valid = actual is not None and values["coverage_status"] == "verified"
            state = "unknown" if not valid else "pass" if actual <= cap + _TOLERANCE else "fail"
            rules.append({"id": f"risk-{idx}-{window}", "candidate": candidate, "label": metric.replace("_", " ").title(),
                          "metric": metric, "window": window, "actual": actual, "limit": cap, "status": state,
                          "headroom": cap - actual if valid else None,
                          "unit": "days" if metric == "recovery_days" else "fraction"})
    if (data["profile"].get("esg") or data["profile"].get("esg_screen")) and not any(
            "exclusion_list" in item["asset_set"] for item in data["constraints"]):
        rules.append({"id": "screening-request", "candidate": candidate, "label": "Controversy screening",
                      "status": "unknown", "reason": "Confirm an exclusion list and coverage before applying a screening rule."})
    return rules


def _trade_size(trade, market):
    if trade["unit"] == "fraction":
        return trade["quantity"], None
    if trade["unit"] in ("percent", "percentage_points"):
        return trade["quantity"] / 100, None
    latest = max(market["windows"].values(), key=lambda entry: entry["dates"][-1])
    as_of = latest["dates"][-1]
    capital = trade["portfolio_value_cad"]
    price = latest["cad_prices"][trade["symbol"]][-1]
    notional = trade["quantity"] * price if trade["unit"] == "shares" else trade["quantity"]
    size = notional / capital
    if not math.isfinite(notional) or not math.isfinite(size):
        raise ValueError("The share count and confirmed capital exceed supported measurement bounds.")
    checked_notional = Decimal(str(trade["quantity"])) * (Decimal(str(price)) if trade["unit"] == "shares" else Decimal(1))
    checked_size = checked_notional / Decimal(str(capital))
    if not math.isclose(size, float(checked_size), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Independent purchase conversion did not match.")
    return size, {"as_of": as_of, "currency": "CAD", "price": price, "notional": notional}


def _capital_amounts(capital, weights, entry, metrics):
    """Scale verified paths using their actual initial and peak denominators."""
    if capital is None:
        return {}
    initial = capital["value"]
    positions = {day: index for index, day in enumerate(entry["dates"])}
    peak, trough = positions[metrics["peak_date"]], positions[metrics["trough_date"]]
    prices = entry["cad_prices"]
    total = math.fsum(weights.values())
    peak_value = initial * math.fsum((weight / total) * prices[ticker][peak] / prices[ticker][0]
                                    for ticker, weight in weights.items())
    amounts = {"terminal_return_amount": initial * metrics["terminal_return"],
               "terminal_loss_amount": initial * metrics["terminal_loss"],
               "drawdown_peak_amount": peak_value,
               "drawdown_loss_amount": peak_value * metrics["max_drawdown"]}
    # The check constructs actual hypothetical units independently and values
    # them at the relevant dates, instead of multiplying the reported percent.
    exact_total = sum((Decimal(str(weight)) for weight in weights.values()), Decimal(0))
    units = {ticker: Decimal(str(initial)) * Decimal(str(weight)) / exact_total / Decimal(str(prices[ticker][0]))
             for ticker, weight in weights.items()}
    def value(index):
        return sum((count * Decimal(str(prices[ticker][index])) for ticker, count in units.items()), Decimal(0))
    change = value(-1) - value(0)
    checked = {"terminal_return_amount": change, "terminal_loss_amount": max(Decimal(0), -change),
               "drawdown_peak_amount": value(peak), "drawdown_loss_amount": value(peak) - value(trough)}
    if any(not math.isfinite(number) or not math.isclose(number, float(checked[key]), abs_tol=1e-8, rel_tol=1e-10)
           for key, number in amounts.items()):
        raise ValueError("Independent capital amount verification failed.")
    return amounts


def _verify_rules(data, options, excluded, context, quantity, claimed):
    """Check every rule with separate decimal arithmetic, including unknowns.

    This does not call the rule renderer. A missing rule, changed bound, or
    changed disposition fails the publication path even if the metrics agree.
    """
    expected = {}
    tolerance = Decimal(str(_TOLERANCE))

    def keep(candidate, identity, **fields):
        expected[candidate, identity] = fields

    for candidate, option in options.items():
        for index, constraint in enumerate(data["constraints"], 1):
            axis, subject = next(iter(constraint["asset_set"].items()))
            supported = axis in {"symbols", "issuer", "sector", "asset_class", "exclusion_list"}
            if axis == "symbols":
                low = high = sum((Decimal(str(option["weights"].get(ticker, 0))) for ticker in subject), Decimal(0))
            elif context is not None and axis in {"issuer", "sector", "asset_class", "exclusion_list"}:
                bound = exposure_bounds(option["weights"], context, "controversy" if axis == "exclusion_list" else axis, subject)
                coefficients = bound["coefficients"]
                low, high = (sum((Decimal(str(option["weights"][ticker])) * Decimal(str(row[key]))
                                  for ticker, row in coefficients.items()), Decimal(0)) for key in ("lower", "upper"))
            else:
                low, high = Decimal(0), Decimal(1)
            for direction in ("min", "max"):
                if constraint[direction] is None:
                    continue
                cap = Decimal(str(constraint[direction]))
                certain = low - cap if direction == "min" else cap - high
                possible = high - cap if direction == "min" else cap - low
                status = ("pass" if certain >= -tolerance else "fail" if possible < -tolerance else "unknown") if supported else "unknown"
                keep(candidate, f"exposure-{index}-{direction}", lower=float(low), upper=float(high),
                     limit=float(cap), status=status, headroom=float(certain) if status != "unknown" else None)
        for index, rule in enumerate(data["risk_limits"], 1):
            chosen = (["2022", "2025"] if rule["windows"] == "default" else
                      sorted(set(option["windows"]) | set(excluded)) if rule["windows"] == "all" else rule["windows"])
            for window in chosen:
                row = option["windows"].get(window)
                metric = rule["metric"]
                actual = None
                if row is not None and metric in RISK_METRICS:
                    if metric == "worst_rolling_12m":
                        worst = row.get("rolling", {}).get("12m", {}).get("worst_return")
                        actual = max(0.0, -worst) if worst is not None else None
                    else:
                        actual = row.get(metric)
                covered = row is not None and row["coverage_status"] == "verified" and actual is not None
                slack = Decimal(str(rule["cap"])) - Decimal(str(actual)) if covered else None
                keep(candidate, f"risk-{index}-{window}", actual=actual, limit=rule["cap"],
                     status=("pass" if slack >= -tolerance else "fail") if covered else "unknown",
                     headroom=float(slack) if covered else None)
        if (data["profile"].get("esg") or data["profile"].get("esg_screen")) and not any(
            "exclusion_list" in rule["asset_set"] for rule in data["constraints"]
        ):
            keep(candidate, "screening-request", status="unknown")
    if data["trade"] is not None:
        available = data["portfolios"][0]["weights"][data["trade"]["source"]]
        keep("Original proposal", "original-funding", actual=available, limit=quantity,
             status="pass" if Decimal(str(available)) >= Decimal(str(quantity)) else "fail",
             headroom=float(Decimal(str(available)) - Decimal(str(quantity))))
    if len(claimed) != len(expected):
        raise ValueError("Independent rule verification found a missing or extra rule.")
    seen = set()
    for row in claimed:
        key = row.get("candidate"), row.get("id")
        if key in seen or key not in expected:
            raise ValueError("Independent rule verification found an unknown or repeated rule.")
        seen.add(key)
        for field, value in expected[key].items():
            actual = row.get(field)
            equal = (type(actual) in (int, float) and math.isfinite(actual) and
                     math.isclose(actual, value, abs_tol=1e-12, rel_tol=0)) if type(value) in (int, float) else actual == value
            if not equal:
                raise ValueError(f"Independent rule verification rejected {field} for {key[1]}.")


def _order(data, options, rules):
    priority = data["priority"]
    if not priority:
        return None
    options = {label: option for label, option in options.items()
               if all(rule["status"] == "pass" for rule in rules if rule["candidate"] == label)}
    if not options:
        return {"metric": priority, "status": "no_verified_eligible_options", "order": [],
                "reason": "No candidate has passed every binding rule; metric ranking is withheld."}
    windows = set.intersection(*({name for name, values in option["windows"].items()
                                  if values["coverage_status"] == "verified" and values.get(priority) is not None}
                                 for option in options.values()))
    window = data["ranking_window"] or next((name for name in ("full_history", "2025", "2022", "2023", "custom")
                                            if name in windows), None)
    if window not in windows:
        return None
    order = [{"candidate": label, "value": option["windows"][window][priority]} for label, option in options.items()]
    return {"metric": priority, "window": window, "status": "ranked_eligible_options", "order": sorted(order, key=lambda item: item["value"],
                                                                  reverse=priority == "terminal_return")}


def _tensions(profile, options):
    risk = str(profile.get("risk_tolerance", "")).casefold()
    objective = str(profile.get("objective", "")).casefold()
    if "conserv" not in objective and "preserv" not in objective and "low" not in risk:
        return []
    original, proposed = options.get("Starting allocation"), options.get("Original proposal")
    if original is None or proposed is None:
        return []
    overlaps = original["windows"].keys() & proposed["windows"].keys()
    if any(proposed["windows"][key]["max_drawdown"] > original["windows"][key]["max_drawdown"] + _TOLERANCE
           for key in overlaps):
        return ["The proposed trade raised observed drawdown in a shared window despite a stated preference for limiting loss."]
    return []


def _fund(approved, data, weights, windows, market_gaps, quantity, rules):
    trade = data["trade"]
    if any(set(item["asset_set"]) != {"symbols"} for item in data["constraints"]) or any(
        rule["id"] == "screening-request" for rule in rules
    ):
        return {"status": "unassessed", "reasons": ["A binding exposure or screening rule has no verified solver coefficients."]}
    limits = []
    for item in data["risk_limits"]:
        selected = _selected_windows(item, windows, market_gaps)
        if not selected or any(key not in windows or windows[key]["coverage"]["status"] != "verified" for key in selected):
            return {"status": "unassessed", "reasons": ["A binding replay window lacks verified coverage."]}
        limits.append({**item, "windows": selected})
    args = (weights, trade["symbol"], quantity, approved.sources, windows, data["constraints"], limits)
    claimed = search_funding(*args, allow_smaller=approved.allow_smaller)
    if claimed["status"] == "unassessed":
        return claimed
    checked = verify_funding(*args, allow_smaller=approved.allow_smaller, claimed=claimed)
    if checked["status"] != "verified":
        raise ValueError("The independent funding verification failed. The result was withheld.")
    return {**claimed, "resolved_risk_limits": limits}


def _metric_records(options, scope, confirmed_id):
    records = {}
    denominators = {
        "terminal_return": "initial portfolio CAD value", "terminal_loss": "initial portfolio CAD value",
        "max_drawdown": "portfolio CAD value at its preceding maximum",
        "annualized_volatility": "sample standard deviation of close-to-close fractional CAD returns; 252 sessions",
        "recovery_days": "calendar days from the maximum-drawdown peak to first recovery",
        "days_underwater": "calendar days from the maximum-drawdown peak to recovery or final observation",
        "terminal_return_amount": "CAD change from confirmed starting capital",
        "terminal_loss_amount": "nonnegative CAD loss from confirmed starting capital",
        "drawdown_peak_amount": "CAD value at the portfolio maximum-drawdown peak",
        "drawdown_loss_amount": "CAD decline from that peak to its corresponding trough",
    }
    for label, option in options.items():
        for window, row in option["windows"].items():
            for field, value in row.items():
                if type(value) not in (float, int) or field == "observations":
                    continue
                unit = "CAD" if field.endswith("_amount") else "days" if field in ("recovery_days", "days_underwater") else "fraction"
                metric_id = _digest(_encode([label, window, field]))[:18]
                if field == "max_drawdown" or field.startswith("drawdown_"):
                    dates = [row["peak_date"], row["trough_date"]]
                elif field in ("recovery_days", "days_underwater"):
                    dates = [row["peak_date"], row["trough_date"], row.get("recovery_date") or row["end_date"]]
                else:
                    dates = [row["start_date"], row["end_date"]]
                price_rows = {ticker: {day: entry for day in dates if (entry := ticker_rows.get(day))}
                              for ticker in option["weights"] if (ticker_rows := scope.get("price_rows", {}).get(ticker))}
                records[metric_id] = {"metric_id": metric_id, "candidate": label, "window": window,
                                      "metric": field, "value": value, "unit": unit, "denominator": denominators.get(field, "See the versioned replay definition"),
                                      "formula_version": METHODS["amounts"] if field.endswith("_amount") else METHODS["replay"], "formula_id": f"replay.{field}",
                                      "input_hash": scope["input_digest"], "as_of": row["end_date"],
                                      "source_ids": sorted(scope["source_sha256"].values()), "source_rows": price_rows,
                                      "policy_version": confirmed_id, "verification_status": "verified",
                                      "coverage_status": row["coverage_status"], "kind": "historical_calculation"}
    return records


def run_decision(confirmed, market_data, *, upload=None, funding=None, code_version=None):
    if not isinstance(confirmed, ConfirmedDecision):
        raise ValueError("Confirm the draft before running the historical engine.")
    if funding is not None and (not isinstance(funding, FundingAuthorization) or funding.decision_id != confirmed.id):
        raise ValueError("Funding authorization belongs to different confirmed inputs.")
    data = confirmed.data
    scope = dict(data["scope"])
    digest = hashlib.sha256(upload).hexdigest() if upload is not None else None
    if digest != scope.pop("upload_sha256", None):
        raise ValueError("The uploaded price file changed. Confirm the inputs again.")
    trade = data["trade"]
    portfolios = {p["label"]: p["weights"] for p in data["portfolios"]}
    assets = set().union(*(weights for weights in portfolios.values()))
    if trade:
        assets.add(trade["symbol"])
    market = prepare_market(market_data, sorted(assets), upload=upload, **scope)
    excluded = dict(market["excluded"])
    windows = {}
    for key, window in market["windows"].items():
        if window["coverage"]["status"] == "incomplete":
            excluded[key] = "Required observations are missing from this window."
        else:
            windows[key] = window
    if not windows:
        raise ValueError("No window has enough source coverage to publish a replay.")

    quantity, conversion, structural = None, None, []
    if trade:
        baseline = next(iter(portfolios.values()))
        quantity, conversion = _trade_size(trade, {**market, "windows": windows})
        portfolios = {"Starting allocation": baseline}
        available = baseline[trade["source"]]
        can_fund = quantity <= available
        structural.append({"id": "original-funding", "candidate": "Original proposal", "label": "Funding available",
                           "status": "pass" if can_fund else "fail", "actual": available, "limit": quantity,
                           "headroom": available - quantity, "unit": "fraction"})
        if can_fund:
            proposed = dict(baseline)
            proposed[trade["source"]] = float(Decimal(str(proposed[trade["source"]])) - Decimal(str(quantity)))
            proposed[trade["symbol"]] = float(Decimal(str(proposed.get(trade["symbol"], 0))) + Decimal(str(quantity)))
            portfolios["Original proposal"] = proposed

    context = None
    if any(set(item["asset_set"]) != {"symbols"} for item in data["constraints"]):
        context = evidence_context(market_data, sorted(assets), knowledge_date=market["knowledge_date"])
    options, exposures = {}, []
    for label, weights in portfolios.items():
        replay = {}
        for key, entry in windows.items():
            args = (weights, entry["dates"], entry["cad_prices"])
            local = entry.get("local_prices")
            claimed = evaluate(*args, local_prices=local)
            checked = verify(*args, claimed, local_prices=local)
            checked.update(_capital_amounts(data["capital"], weights, entry, checked))
            replay[key] = {**checked, "coverage_status": entry["coverage"]["status"], "coverage": entry["coverage"],
                           "start_date": entry["dates"][0], "end_date": entry["dates"][-1]}
        if (full := windows.get("full_history")) is not None:
            full_days = set(full["dates"])
            for key in replay.keys() & {"2022", "2023", "2025"}:
                entry = replay[key]
                start, end = entry["start_date"], entry["end_date"]
                if start in full_days and end in full_days:
                    args = (weights, full["dates"], full["cad_prices"], start, end)
                    entry["relative_stress"] = verify_stress_percentile(*args, stress_percentile(*args))
        options[label] = {"weights": weights, "windows": replay}

    rules = structural + [rule for candidate in options for rule in
                          _candidate_rules(candidate, options, data, context, excluded, exposures)]
    _verify_rules(data, options, excluded, context, quantity, rules)
    alternatives = _fund(funding, data, baseline, windows, excluded, quantity, rules) if funding else None
    decision_rules = [rule for rule in rules if data["intent"] != "audit" or rule["candidate"] != "Starting allocation"]
    incomplete_rules = any(rule["status"] == "unknown" for rule in decision_rules)
    verdict = "fail" if any(rule["status"] == "fail" for rule in decision_rules) else (
        "unknown" if any(rule["status"] == "unknown" for rule in decision_rules) else
        "pass" if decision_rules else "no_binding_rules")
    gaps = [f"{key}: {reason}" for key, reason in excluded.items()]
    gaps.extend(f"{key}: independent session coverage unavailable. Metrics describe the observed path."
                for key, window in windows.items() if window["coverage"]["status"] != "verified")
    gaps.extend(str(item) for item in (context or {}).get("gaps", ()))
    gaps.extend(f"{rule['candidate']}: {rule['label']} remains unassessed under the available evidence."
                for rule in decision_rules if rule["status"] == "unknown")
    provenance = dict(market["provenance"])
    provenance.pop("price_rows", None)
    if context is not None:
        provenance["exposure"] = context
    market_scope = {"knowledge_date": market["knowledge_date"], "windows": list(windows), "excluded": excluded}
    records = _metric_records(options, market["provenance"], confirmed.id)
    facts = {
        "intent": data["intent"], "status": "limited" if gaps or incomplete_rules else "verified",
        "verdict": verdict, "options": options, "rules": rules, "ranking": _order(data, options, rules),
        "gaps": gaps, "assumptions": ["Fictional buy-and-hold replay in CAD using adjusted closes.",
                                      "Transaction costs, taxes, and intraday moves are outside this replay.",
                                      ("Team-defined example rules were explicitly confirmed; they are not inferred from the organizer persona."
                                       if data["assumption_kind"] == "team_defined" else "Binding rules are user-defined and explicitly confirmed.")],
        "funding": alternatives, "trade_conversion": conversion, "exposure": exposures,
        "profile_tensions": _tensions(data["profile"], options) if data["intent"] == "audit" else [], "metric_records": records,
        "market_scope": market_scope, "governance": [
            {"id": "historical_only", "status": "pass"},
            {"id": "independent_review", "status": "pass"},
            {"id": "rule_coverage", "status": "flag" if incomplete_rules else "pass"},
            {"id": "alternative_authorization", "status": "pass" if funding else "n/a"},
            {"id": "profile_tension", "status": "flag" if data["intent"] == "audit" and _tensions(data["profile"], options) else "pass"},
            {"id": "assumption_labels", "status": "pass", "reason": "Historical calculations and user-confirmed rules are identified separately."},
            {"id": "time_consistency", "status": "flag" if excluded else "pass", "reason": "Evidence is qualified against the confirmed knowledge date."},
            {"id": "evidence_coverage", "status": "flag" if gaps else "pass"},
            {"id": "numeric_tampering", "status": "pass", "reason": "Prices, metrics and each binding rule passed separate verification."},
        ],
    }
    versions = review_binding(data, facts, input_provenance=provenance, method_versions=METHODS)
    reviews = {**versions, "status": "verified", "method_versions": METHODS,
               "checks": {"market": "verified", "metrics": "verified", "funding": "checked" if funding else "skipped"}}
    if funding:
        data = {**data, "authorized_funding": {"sources": list(funding.sources), "allow_smaller": funding.allow_smaller}}
        reviews.update(review_binding(data, facts, input_provenance=provenance, method_versions=METHODS))
    return seal_report(data, facts, reviews, input_provenance=provenance, trace=confirmed.trace, code_version=code_version)
