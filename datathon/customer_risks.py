"""Profile-triggered risk tools, with explicit evidence gaps and independent checks."""

from bisect import bisect_left
from calendar import monthrange
from datetime import date
from fractions import Fraction
from math import fsum, isclose
import re

from .decision_replay import evaluate, verify
from .decision_evidence import evidence_context, exposure_bounds, SECTORS
from .decision_intake import _risk
from .customer_bonds import qualified_bond_disclosures, duration_scenarios, credit_breakdown


def historical_details(item):
    """Reuse extended metrics, stress replay and FX attribution from the existing engine."""
    dates = [row["date"] for row in item["rows"]]
    values = [row["price"] for row in item["rows"]]
    local_map = {row["date"]: row["price"] for row in item["asset"]["rows"]}
    local = {"asset": [local_map[day] for day in dates]}
    metric = evaluate({"asset": 1.0}, dates, {"asset": values}, local)
    verify({"asset": 1.0}, dates, {"asset": values}, metric, local)
    stress = []
    for label, first, last in (("2022 market decline", "2021-12-31", "2022-12-30"),
                               ("Early 2025", "2024-12-31", "2025-04-08")):
        if first not in dates or last not in dates:
            stress.append({"label": label, "status": "missing_market_data", "reason": "Exact stress endpoints are not both present."})
            continue
        a, b = dates.index(first), dates.index(last)
        checked = evaluate({"asset": 1.0}, dates[a:b + 1], {"asset": values[a:b + 1]})
        verify({"asset": 1.0}, dates[a:b + 1], {"asset": values[a:b + 1]}, checked)
        stress.append({"label": label, "status": "assessed", "start": first, "end": last,
                       "return": checked["terminal_return"], "drawdown": checked["max_drawdown"]})
    return {"symbol": item["asset"]["symbol"], "currency": item["basis"], "metrics": metric, "stress": stress,
            "volatility_basis": "withheld" if item["asset"].get("instrument_type") == "CRYPTOCURRENCY" else "252-observation convention"}


_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_MONEY = re.compile(rf"(?:(CAD|USD)\s*\$?\s*({_NUMBER})|({_NUMBER})\s*(CAD|USD))\b", re.I)
_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "twelve": "12"}


def withdrawal_schedule(profile):
    excerpts = [field["excerpt"] for field in profile["fields"]["withdrawal"]]
    if not excerpts:
        return None, "Add the withdrawal amount, currency, timing and frequency."
    if len(excerpts) != 1:
        return None, "Confirm one withdrawal schedule; multiple or conflicting schedules have not been combined."
    original = excerpts[0]
    text = re.sub(r"\b(" + "|".join(_WORDS) + r")\b", lambda match: _WORDS[match[0]], original.lower())
    money = list(_MONEY.finditer(text))
    if len(money) != 1:
        return None, "State one withdrawal amount with CAD or USD."
    match = money[0]
    currency, amount = (match[1] or match[4]).upper(), float((match[2] or match[3]).replace(",", ""))
    if not 0 < amount <= 1e10:
        return None, "The withdrawal amount must be positive."
    frequency = "monthly" if re.search(r"monthly|every month|per month", text) else "once"
    if re.search(r"weekly|quarterly|every year|annually", text):
        return None, "Only a single withdrawal or a fixed monthly schedule is currently supported."
    first = re.search(r"(?:in|after|starting in|start in)\s+(\d+)\s+(months?|years?)", text)
    if "next month" in text:
        first_month = 1
    elif first:
        first_month = int(first[1]) * (12 if first[2].startswith("year") else 1)
    else:
        return None, "When does the first withdrawal occur, expressed in months from the start?"
    duration = re.search(r"for\s+(\d+)\s+(months?|years?)", text)
    if frequency == "monthly" and not duration:
        return None, "For how many months should the monthly withdrawals continue?"
    count = int(duration[1]) * (12 if duration[2].startswith("year") else 1) if frequency == "monthly" else 1
    if not 1 <= first_month <= 600 or not 1 <= count <= 600:
        return None, "Use a positive withdrawal start and duration within the supported simulation horizon."
    return {"amount": amount, "currency": currency, "first_month": first_month, "count": count,
            "frequency": frequency, "excerpt": original,
            "timing_basis": "Relative months are mapped onto the beginning of each observed historical path.",
            "liquidation_rule": "Sell fractional units at the first included daily close on or after each due date; no fees or tax."}, None


def add_months(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def replay_withdrawals(rows, capital, schedule):
    """One historical path; never a retirement-success probability."""
    days = [date.fromisoformat(row["date"]) for row in rows]
    events = {}
    for number in range(schedule["count"]):
        due = add_months(days[0], schedule["first_month"] + (number if schedule["frequency"] == "monthly" else 0))
        index = bisect_left(days, due)
        if index >= len(days):
            raise ValueError("The available historical path is shorter than the complete withdrawal schedule.")
        events[index] = events.get(index, 0) + schedule["amount"]
    units = capital / rows[0]["price"]
    exact_units = Fraction(str(capital)) / Fraction(str(rows[0]["price"]))
    cumulative, shortfall = 0., 0.
    path, withdrawals = [], []
    for index, row in enumerate(rows):
        before = units * row["price"]
        requested = events.get(index, 0.)
        paid = min(requested, before)
        units -= paid / row["price"]
        units = max(0., units)
        cumulative += paid
        shortfall += requested - paid
        exact_price = Fraction(str(row["price"]))
        exact_paid = min(Fraction(str(requested)), exact_units * exact_price)
        exact_units -= exact_paid / exact_price
        remaining = units * row["price"]
        if not isclose(remaining, float(exact_units * exact_price), rel_tol=1e-9, abs_tol=1e-7):
            raise ValueError("Independent withdrawal replay verification failed.")
        baseline = capital * row["price"] / rows[0]["price"]
        point = {"date": row["date"], "with_withdrawals": remaining, "without_withdrawals": baseline,
                 "paid": paid, "shortfall": requested - paid}
        path.append(point)
        if requested:
            withdrawals.append({"date": row["date"], "requested": requested, "paid": paid,
                                "shortfall": requested - paid, "remaining": remaining,
                                "below_previous_high": row["price"] < max(prior["price"] for prior in rows[:index + 1])})
    return {"path": path, "withdrawals": withdrawals, "total_requested": schedule["amount"] * schedule["count"],
            "total_paid": cumulative, "shortfall": shortfall, "remaining": path[-1]["with_withdrawals"],
            "without_withdrawals": path[-1]["without_withdrawals"], "schedule": schedule,
            "withdrawals_during_declines": sum(item["below_previous_high"] for item in withdrawals),
            "recovery_note": "The no-withdrawal recovery metric does not describe this cash-withdrawal path."}


def purchasing_power(rows, cpi):
    levels = {row["month"]: row["index"] for row in cpi["rows"]}
    month_ends = {}
    for row in rows:
        if row["date"][:7] in levels:
            month_ends[row["date"][:7]] = row
    if len(month_ends) < 2:
        raise ValueError("Fewer than two monthly prices align with Canadian CPI.")
    months = sorted(month_ends)
    first, last = months[0], months[-1]
    nominal = month_ends[last]["price"] / month_ends[first]["price"]
    inflation = levels[last] / levels[first]
    real = nominal / inflation - 1
    exact = (Fraction(str(month_ends[last]["price"])) / Fraction(str(month_ends[first]["price"]))
             * Fraction(str(levels[first])) / Fraction(str(levels[last])) - 1)
    if not isclose(real, float(exact), rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("Independent purchasing-power verification failed.")
    return {"start": month_ends[first]["date"], "end": month_ends[last]["date"],
            "first_cpi_month": first, "last_cpi_month": last, "nominal_return": nominal - 1,
            "cpi_change": inflation - 1, "real_return": real, "source_url": cpi["source_url"],
            "alignment": "Last observed close in each CPI reference month; latest CPI vintage, retrospective only."}


def quantify_risks(risks, profile, analyses, budget, *, cpi=None, market_data=None, today=None):
    """Fill supported plan items; leave every other item with a precise gap."""
    today = today or date.today().isoformat()
    weights = profile.get("weights")
    combined = None
    by_symbol = {item["asset"]["symbol"]: item for item in analyses}
    if weights and set(weights) <= by_symbol.keys() and len({by_symbol[symbol]["basis"] for symbol in weights}) == 1:
        dates = sorted(set.intersection(*(set(row["date"] for row in by_symbol[symbol]["rows"]) for symbol in weights)))
        if len(dates) >= 20:
            prices = {symbol: {row["date"]: row["price"] for row in by_symbol[symbol]["rows"]} for symbol in weights}
            series = {symbol: [prices[symbol][day] for day in dates] for symbol in weights}
            local_maps = {symbol: {row["date"]: row["price"] for row in by_symbol[symbol]["asset"]["rows"]} for symbol in weights}
            local_series = {symbol: [local_maps[symbol][day] for day in dates] for symbol in weights}
            metric = evaluate(weights, dates, series, local_series)
            verify(weights, dates, series, metric, local_series)
            rows = [{"date": row["date"], "price": row["value"] * 100} for row in metric["observed_path"]]
            combined = {"asset": {"symbol": "Stated portfolio", "rows": rows}, "rows": rows,
                        "basis": by_symbol[next(iter(weights))]["basis"], "combined_metrics": metric}
    targets = [combined] if combined else analyses
    bonds, bond_gaps = qualified_bond_disclosures(list(by_symbol), today)
    for risk in risks:
        try:
            if risk["id"] == "historical_market":
                risk["results"] = [historical_details(item) for item in analyses]
                if combined:
                    risk["results"].append({"symbol": "Stated portfolio", "currency": combined["basis"],
                        "metrics": combined["combined_metrics"], "stress": [], "weights": weights})
            elif risk["id"] == "cash_needs":
                schedule, missing = withdrawal_schedule(profile)
                if missing:
                    risk["limitation"] = missing + " This is a funding-needs check, not a complete market-liquidity analysis."
                    if missing.startswith("Only"):
                        risk["status"] = "not_supported"
                elif not budget or budget["currency"] != schedule["currency"]:
                    risk["limitation"] = "Confirm the available investment amount in the withdrawal currency."
                else:
                    for item in targets:
                        if item["basis"] != schedule["currency"]:
                            continue
                        risk["results"].append({"symbol": item["asset"]["symbol"], "currency": item["basis"],
                                                **replay_withdrawals(item["rows"], budget["amount"], schedule)})
                    risk["status"] = "assessed" if risk["results"] else "missing_market_data"
            elif risk["id"] == "purchasing_power" and cpi:
                risk["results"] = [{"symbol": item["asset"]["symbol"], **purchasing_power(item["rows"], cpi)}
                                   for item in targets if item["basis"] == "CAD"]
                risk["status"] = "assessed" if risk["results"] else "missing_market_data"
                if not risk["results"]:
                    risk["limitation"] = "Canadian purchasing power needs a verified CAD path; the current path is in another currency."
            elif risk["id"] in {"interest_rate", "credit"}:
                function = duration_scenarios if risk["id"] == "interest_rate" else credit_breakdown
                risk["results"] = [function(record) for record in bonds.values()]
                risk["status"] = "assessed" if risk["results"] else "missing_market_data"
                if risk["results"]:
                    risk["limitation"] = ("Only the named, dated disclosures are covered. Unknown holdings remain unassessed. "
                        "This is a current disclosure snapshot, not evidence that was available throughout the historical replay.")
                risk["disclosure_gaps"] = bond_gaps
            elif risk["id"] == "market_liquidity" and budget:
                for item in analyses:
                    trading = item["asset"].get("trading", [])[-20:]
                    sizing = item["valuation"]
                    if len(trading) < 20 or not sizing:
                        continue
                    average = fsum(row["close"] * row["volume"] for row in trading) / len(trading)
                    if average <= 0:
                        continue
                    local_amount = budget["amount"] * (weights.get(item["asset"]["symbol"], 0) if weights else 1) / sizing["fx_rate"]
                    ratio = local_amount / average
                    exact_average = sum(Fraction(str(row["close"])) * Fraction(str(row["volume"])) for row in trading) / len(trading)
                    if not isclose(ratio, float(Fraction(str(local_amount)) / exact_average), rel_tol=1e-9, abs_tol=1e-12):
                        raise ValueError("Independent trading-volume check failed.")
                    risk["results"].append({"symbol": item["asset"]["symbol"], "ratio": ratio,
                        "average_daily_traded_value": average, "currency": item["asset"]["currency"],
                        "observations": len(trading), "start": trading[0]["date"], "end": trading[-1]["date"],
                        "basis": "Close times reported volume, not transaction-level notional or a spread."})
                risk["status"] = "assessed" if risk["results"] else "missing_market_data"
            elif risk["id"] in {"concentration", "controversy"}:
                tickers = [item["asset"]["symbol"] for item in analyses]
                context = evidence_context(market_data, tickers, knowledge_date=today)
                if risk["id"] == "controversy" and not any(re.search(r"gpfg|norges", field["excerpt"], re.I)
                        for values in profile["fields"].values() for field in values):
                    risk["status"] = "needs_client_information"
                    risk["limitation"] = "Name the exclusion or observation list you want checked. A general ESG preference is not silently replaced with a GPFG test."
                    continue
                requested_sectors = [sector for sector in SECTORS if any(sector.lower() in field["excerpt"].lower()
                    for field in profile["fields"]["concentration"])]
                axes = [("controversy", "gpfg_exclusions")] if risk["id"] == "controversy" else [
                    ("asset_class", "equity"), *[("sector", sector) for sector in sorted(requested_sectors or SECTORS)],
                    *[("issuer", symbol) for symbol in tickers]]
                portfolios = {"Stated portfolio": weights} if combined else {symbol: {symbol: 1.0} for symbol in tickers}
                for symbol, allocation in portfolios.items():
                    for axis, subject in axes:
                        result = exposure_bounds(allocation, context, axis, subject)
                        if result["coverage"] and (result["upper"] or axis in {"asset_class", "controversy"}):
                            risk["results"].append({"symbol": symbol, "axis": axis, "subject": subject, **result})
                risk["status"] = "assessed" if risk["results"] else "missing_market_data"
                risk["coverage_note"] = "Bounds apply to each standalone asset. Partial coverage does not complete ETF look-through or all concentration checks."
        except (ValueError, ArithmeticError) as exc:
            risk["status"] = "missing_market_data"
            risk["limitation"] = str(exc)
            risk["results"] = []
    return risks


def risk_blocks(risks):
    blocks, required = {}, None
    for risk in risks:
        key = "risk." + risk["id"]
        if risk["status"] != "assessed":
            blocks[key] = {"title": risk["id"].replace("_", " ").capitalize() + " · evidence gap",
                           "text": risk["reason"] + " " + risk["limitation"], "sources": []}
            continue
        summaries, sources = [], []
        for row in risk["results"]:
            symbol = row["symbol"]
            if risk["id"] == "cash_needs":
                event_dates = ", ".join(item["date"] for item in row["withdrawals"])
                summaries.append(f"For {symbol}, the replay starts at {row['path'][0]['date']} and the asset path ends at {row['path'][-1]['date']}. "
                    f"Scheduled withdrawals actually occur on: {event_dates}. Relative timing is mapped onto the historical starting date, not today. "
                    "Replaying the stated withdrawal schedule against this observed path required "
                    f"{row['currency']} {row['total_requested']:,.2f}. The replay paid {row['currency']} {row['total_paid']:,.2f}, "
                    f"left a funding shortfall of {row['currency']} {row['shortfall']:,.2f}, and ended with "
                    f"{row['currency']} {row['remaining']:,.2f} in assets. {row['withdrawals_during_declines']} scheduled withdrawal dates "
                    "occurred below a previous market high. The full initial amount is invested in fractional units at the start of this "
                    "historical path; no whole-share cash remainder is retained. Scheduled withdrawals sell fractional units at the first "
                    "included close on or after the due date. This is one historical scenario, not a retirement-success probability. "
                    + row["recovery_note"] + " A shortfall in this path does not establish certain future failure; a surplus does not guarantee future funding.")
                if row["shortfall"] > .005:
                    required = key
            elif risk["id"] == "purchasing_power":
                summaries.append(f"Between {row['start']} and {row['end']}, {symbol}'s CAD nominal change was "
                    f"{row['nominal_return']:+.2%}, Canadian CPI rose {row['cpi_change']:.2%}, and the inflation-adjusted change "
                    f"was {row['real_return']:+.2%}. The CPI observations refer to months, not publication dates; this is retrospective.")
                sources.append(row["source_url"])
            elif risk["id"] == "market_liquidity":
                summaries.append(f"For {symbol}, the stated amount was {row['ratio']:.6%} of average daily close-times-volume "
                    f"over {row['observations']} observations from {row['start']} to {row['end']}. "
                    "This limited proxy does not establish the bid/ask spread, price impact or ability to liquidate an ETF's underlying assets.")
            elif risk["id"] == "interest_rate":
                summaries.append(f"{symbol}'s issuer reports effective duration of {row['duration_years']:.2f} years as of {row['as_of']}, "
                    f"observed on {row['observed_on']}. Under the explicit illustrative +100 basis-point parallel yield shock, "
                    f"the first-order price change is {row['scenarios'][1]['approximate_price_change']:+.2%}; "
                    f"under -100 basis points it is {row['scenarios'][0]['approximate_price_change']:+.2%}. {row['limitation']}")
                sources.append(row["source_url"])
            elif risk["id"] == "credit":
                summaries.append(f"{symbol}'s issuer rating breakdown as of {row['as_of']} reports "
                    f"{row['reported_below_investment_grade']:.2%} in disclosed below-investment-grade buckets and "
                    f"{row['unrated_weight']:.2%} explicitly unrated, with {row['unclassified_or_rounding_weight']:.2%} "
                    "unclassified or rounding residual. These describe underlying securities, not a credit rating of the ETF, "
                    "a default probability or a repayment guarantee.")
                sources.append(row["source_url"])
            elif risk["id"] in {"concentration", "controversy"}:
                summaries.append(f"For the standalone {symbol} position, dated {row['axis']} evidence bounds "
                    f"{row['subject']} exposure between {row['lower']:.2%} and {row['upper']:.2%}; "
                    f"unassessed weight is {row['unassessed_weight']:.2%}. This is a source-specific bound, not a whole-portfolio or ESG verdict.")
                sources.extend(value["source_url"] for value in row["coefficients"].values() if value.get("source_url"))
            elif risk["id"] == "historical_market":
                metric = row["metrics"]
                parts = [f"{symbol}: terminal loss {metric['terminal_loss']:.2%}"]
                if row.get("volatility_basis") == "withheld":
                    parts.append("annualized volatility withheld because this instrument trades on a different calendar")
                else:
                    parts.append(f"annualized observed volatility {metric['annualized_volatility']:.2%} (252-observation convention; session coverage uncertified)")
                if metric["worst_month"]["return"] is not None:
                    parts.append(f"worst complete monthly return {metric['worst_month']['return']:.2%} ({metric['worst_month']['month']})")
                for period in ("12m", "36m"):
                    rolling = metric["rolling"][period]
                    parts.append(f"worst rolling {period} return {rolling['worst_return']:.2%}" if rolling["worst_return"] is not None
                                 else f"rolling {period} unavailable because the aligned history is too short")
                parts.append(f"maximum-drawdown recovery {metric['recovery_days']} calendar days from its peak" if metric["recovery_status"] == "recovered"
                             else "maximum drawdown still unrecovered at the final observation" if metric["recovery_status"] == "unrecovered" else "no drawdown observed")
                if row["currency"] == "CAD" and metric["fx_decomposition"]:
                    parts.append(f"local-price return {metric['fx_decomposition']['local_return']:.2%}; "
                                 f"FX impact including interaction {metric['fx_decomposition']['fx_impact']:.2%}")
                for stress in row["stress"]:
                    parts.append(f"{stress['label']}: return {stress['return']:+.2%}, drawdown {stress['drawdown']:.2%}" if stress["status"] == "assessed"
                                 else f"{stress['label']}: exact replay endpoints missing")
                summaries.append("; ".join(parts) + ".")
        blocks[key] = {"title": risk["id"].replace("_", " ").capitalize() + " · assessed evidence",
                       "text": " ".join(summaries) + " " + risk["limitation"], "sources": list(dict.fromkeys(sources))}
    return blocks, required


def explicit_rule_checks(profile, analyses):
    """No precise rule is inferred from age, willingness, or qualitative labels."""
    checks = []
    for field in ("loss", "capacity", "concentration"):
        for statement in profile["fields"][field]:
            rule = _risk(statement["excerpt"])
            if not rule:
                continue
            for item in analyses:
                metrics = item["metrics"]["extended"]
                actual = metrics.get(rule["metric"])
                if rule["metric"] == "worst_rolling_12m":
                    value = metrics["rolling"]["12m"]["worst_return"]
                    actual = max(0, -value) if value is not None else None
                status = "unknown"
                reason = "The stated rule requires complete coverage and a confirmed window; no pass is inferred from this observational sample."
                if rule["windows"] != "default":
                    actual = None
                    reason = "The rule names a different replay window. Use the historical decision workbench to confirm that window."
                elif rule["metric"] == "max_drawdown" and actual is not None and actual > rule["cap"]:
                    status = "observed_breach"
                    reason = "An observed peak-to-trough decline already exceeds the explicit cap. Missing observations cannot erase that observed breach."
                checks.append({"symbol": item["asset"]["symbol"], "metric": rule["metric"], "cap": rule["cap"],
                               "actual": actual, "status": status, "reason": reason, "source_excerpt": statement["excerpt"]})
    return checks
