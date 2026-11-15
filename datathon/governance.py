"""Independent consistency and suitability checks for the simulation."""

from collections.abc import Mapping
from math import fsum, isfinite

from .evidence import validate_issuer_snapshot
from .market_calendar import starter_calendar_gap


SOURCES = ("QQQ", "ZST.TO")
RESERVE = "ZST.TO"
ISSUER = "NVDA"
EPSILON = 1e-8
BOUNDARY_EPSILON = 1e-10
METRICS = ("terminal_loss", "max_drawdown")


class MissingEvidence(ValueError):
    """A claim could change when the missing input is known."""


def _fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("A portfolio fraction must be numeric.")
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError("A portfolio fraction must be between zero and one.")
    return float(value)


def _weights(candidate, assets):
    weights = candidate.get("weights", candidate)
    if set(weights) != assets:
        raise ValueError("Candidate weights must cover all assets in the baseline.")
    weights = {name: _fraction(weight) for name, weight in weights.items()}
    if abs(fsum(weights.values()) - 1) > EPSILON:
        raise ValueError("Portfolio weights must add to one.")
    return weights


def _window_specs(policy, dates):
    if dates is not None:
        if isinstance(dates, Mapping):
            return tuple((name, None, None, list(items)) for name, items in dates.items())
        return (("stress", None, None, list(dates)),)
    specs = []
    for window in policy.get("windows", ()):
        if isinstance(window, Mapping):
            specs.append((window["id"], window["start"], window["end"], None))
        else:
            specs.append((window.id, window.start, window.end, None))
    return tuple(specs)


def _growth_windows(prices, assets, specs, fx_dates, *, official_starter=False):
    if not specs or prices is None or not assets.issubset(prices):
        raise MissingEvidence("The frozen prices or stress window definitions are missing.")
    all_dates = set.intersection(*(set(prices[ticker]) for ticker in assets))
    if fx_dates is not None:
        all_dates.intersection_update(fx_dates)
    windows = {}
    for window_id, start, end, specified in specs:
        if window_id in windows:
            raise ValueError("Stress window identifiers must be unique.")
        if specified is not None:
            if sorted(set(specified)) != specified:
                raise ValueError("Stress observations must be unique and chronological.")
            if not set(specified).issubset(all_dates):
                raise MissingEvidence("A stress window references unavailable prices or FX dates.")
            window_dates = specified
        else:
            window_dates = sorted(day for day in all_dates if start <= day <= end)
            if not window_dates or window_dates[0] != start or window_dates[-1] != end:
                raise MissingEvidence("Frozen prices do not cover both stress window endpoints.")
        if len(window_dates) < 2:
            raise MissingEvidence("A stress window needs at least two common observations.")
        if official_starter and (gap := starter_calendar_gap(start, end, window_dates)):
            raise MissingEvidence(gap)
        growth = {}
        for name in sorted(assets):
            closes = [prices[name][day] for day in window_dates]
            if any(not isinstance(close, (int, float)) or isinstance(close, bool) or
                   not isfinite(close) or close <= 0 for close in closes):
                raise ValueError("Frozen closing prices must be finite and positive.")
            growth[name] = [close / closes[0] for close in closes]
        windows[window_id] = (window_dates, growth)
    return windows


def _evaluate(windows, weights):
    computed = {}
    for window_id, (dates, growth) in windows.items():
        values = [
            fsum(weights[asset] * growth[asset][i] for asset in growth)
            for i in range(len(dates))
        ]
        peak = worst_peak = worst_trough = 0
        drawdown = 0.0
        for i, value in enumerate(values):
            if value > values[peak]:
                peak = i
            decline = 1 - value / values[peak]
            if decline > drawdown:
                drawdown = decline
                worst_peak, worst_trough = peak, i
        terminal_return = values[-1] - 1
        computed[window_id] = {
            "terminal_loss": max(0.0, -terminal_return),
            "terminal_return": terminal_return,
            "max_drawdown": drawdown,
            "peak_date": dates[worst_peak],
            "trough_date": dates[worst_trough],
            "observations": len(dates),
            "attribution": {ticker: weights[ticker] * (series[-1] - 1.0)
                            for ticker, series in growth.items()},
            "drawdown_attribution": {
                ticker: (weights[ticker] * series[worst_peak] - weights[ticker] * series[worst_trough])
                / values[worst_peak] for ticker, series in growth.items()
            },
        }
    return {**{key: max(window[key] for window in computed.values()) for key in METRICS},
            "windows": computed}


def _matches(expected, actual):
    if expected is None or isinstance(expected, (str, bool)):
        return expected == actual and type(expected) is type(actual)
    return (isinstance(actual, (int, float)) and not isinstance(actual, bool) and
            isfinite(actual) and abs(expected - actual) <= EPSILON)


def _compare_evaluation(role, expected, claimed, weights, add):
    if not isinstance(claimed, Mapping) or "windows" not in claimed:
        add(f"{role}.window_metrics", "insufficient_evidence", "Reported window metrics are missing.")
        return
    if set(expected["windows"]) != set(claimed["windows"]):
        add(f"{role}.window_metrics", "invalid", "Reported and verified stress windows differ.")
        return
    if "weights" in claimed and any(not _matches(weight, claimed["weights"].get(ticker))
                                    for ticker, weight in weights.items()):
        add(f"{role}.weights", "invalid", "Reported evaluation uses different portfolio weights.")
    for window_id, values in expected["windows"].items():
        reported = claimed["windows"][window_id]
        optional = ("terminal_return", "peak_date", "trough_date", "observations")
        for metric in (*METRICS, *(name for name in optional if name in reported)):
            if metric not in reported:
                add(f"{role}.{window_id}.{metric}", "insufficient_evidence", "Reported metric is missing.")
                continue
            matches = _matches(values[metric], reported.get(metric))
            status = "pass" if matches else "invalid"
            add(f"{role}.{window_id}.{metric}", status,
                "Recomputed from frozen CAD prices." if matches else "Reported metric differs from frozen CAD prices.",
                actual=values[metric], claimed=reported.get(metric))
        for metric in ("attribution", "drawdown_attribution"):
            if metric not in reported:
                continue
            expected_attribution = values[metric]
            reported_attribution = reported[metric]
            if (not isinstance(reported_attribution, Mapping)
                    or set(reported_attribution) != set(expected_attribution)
                    or any(not _matches(amount, reported_attribution[ticker])
                           for ticker, amount in expected_attribution.items())):
                add(f"{role}.{window_id}.{metric}", "invalid", "Reported attribution disagrees with the frozen series.")
    if "metrics" in claimed:
        for metric in METRICS:
            if metric in claimed["metrics"] and not _matches(expected[metric], claimed["metrics"][metric]):
                add(f"{role}.{metric}", "invalid", "Reported aggregate differs from the worst verified window.",
                    actual=expected[metric], claimed=claimed["metrics"][metric])


def review_portfolio_comparison(data, options, evaluations, *, windows):
    """Independently recompute two portfolios over their shared CAD observation dates."""
    tickers = set().union(*options.values())
    replays = _growth_windows(
        data.prices, tickers, _window_specs({"windows": windows}, None), data.fx,
        official_starter=data.official_starter,
    )

    def require_consistency(metric, status, message, **_):
        if status != "pass":
            raise ValueError(f"Independent review rejected {metric}. {message}")

    checked = {}
    for label, option in options.items():
        weights = _weights(dict.fromkeys(tickers, 0.0) | option, tickers)
        result = _evaluate(replays, weights)
        claims = evaluations[label]
        if set(claims.get("weights", {})) != tickers or any(
            not {"terminal_return", "terminal_loss", "max_drawdown", "peak_date", "trough_date", "observations"}
            <= row.keys() for row in claims.get("windows", {}).values()
        ):
            raise ValueError("The portfolio replay omitted required claims.")
        _compare_evaluation(label, result, claims, weights, require_consistency)
        checked[label] = result["windows"]
    return checked, {name: dates for name, (dates, _) in replays.items()}


def _funding(baseline, weights, allowed, target):
    funding = {ticker: baseline[ticker] - weights[ticker] for ticker in SOURCES}
    increase = weights[ISSUER] - baseline[ISSUER]
    if (any(abs(weights[ticker] - baseline[ticker]) > EPSILON
            for ticker in weights.keys() - {*SOURCES, ISSUER}) or
            any(sale < -EPSILON or (ticker not in allowed and sale > EPSILON)
                for ticker, sale in funding.items()) or
            abs(fsum(funding.values()) - increase) > EPSILON or
            not -EPSILON <= increase <= target + EPSILON):
        raise ValueError("The candidate changes positions outside the authorized funding policy.")
    return funding, increase


def _issuer_coefficients(policy, assets, evidence, issuer_context=None):
    coefficients = {ticker: 1.0 if ticker == ISSUER else None for ticker in assets}
    snapshot = evidence.get("issuer_snapshot")
    amounts = policy.get("issuer_exposure") or {}
    if issuer_context is not None:
        verified = validate_issuer_snapshot(snapshot, assets=sorted(assets), **issuer_context)
        coefficients = verified["issuer_weights"]
        if any(not _matches(coefficients[ticker], amounts[ticker]) for ticker in assets if ticker in amounts):
            raise ValueError("Claimed issuer exposure disagrees with independently validated disclosures.")
        return coefficients
    if not isinstance(snapshot, Mapping) or not snapshot.get("as_of"):
        return coefficients
    permitted = set(evidence.get("permitted_scope_assumptions", ()))
    for ticker in assets - {ISSUER}:
        row = snapshot.get("holdings", {}).get(ticker, {})
        if not row.get("url") or row.get("weight") is None:
            continue
        disclosed = row.get("status") == "disclosed"
        assumed = row.get("status") == "scope_assumption" and ticker in permitted
        if not (disclosed or assumed):
            continue
        if disclosed and not (row.get("published_on") and row["published_on"] >= snapshot["as_of"]):
            continue
        amount = _fraction(row["weight"])
        if amounts.get(ticker) is not None and not _matches(amount, amounts[ticker]):
            raise ValueError(f"Claimed issuer exposure for {ticker} disagrees with the snapshot.")
        coefficients[ticker] = amount
    return coefficients


def _issuer_bounds(weights, exposures):
    return (
        fsum(weights[ticker] * (amount or 0.0) for ticker, amount in exposures.items()),
        fsum(weights[ticker] * (amount if amount is not None else 1.0)
             for ticker, amount in exposures.items()),
    )


def _portfolio_verdict(weights, evaluation, policy, exposures, total):
    metric = policy["metric"]
    rules = {
        "reserve_weight": (weights[RESERVE], policy["reserve_floor"],
                           weights[RESERVE] + EPSILON >= policy["reserve_floor"]),
    }
    if policy["loss_limit"] is not None:
        rules[metric] = (evaluation[metric], policy["loss_limit"], evaluation[metric] <= policy["loss_limit"] + EPSILON)
    if not policy["allow_smaller"] and total is not None:
        target = policy["target"]
        rules["requested_size"] = (total, target, abs(total - target) <= BOUNDARY_EPSILON)
    if policy.get("direct_cap") is not None:
        cap = policy["direct_cap"]
        rules["direct_weight"] = (weights[ISSUER], cap, weights[ISSUER] <= cap + EPSILON)
    if policy.get("issuer_cap") is not None:
        cap = policy["issuer_cap"]
        lower, upper = _issuer_bounds(weights, exposures)
        if lower > cap + EPSILON:
            passed = False
        elif upper <= cap + EPSILON:
            passed = True
        else:
            passed = None
        rules["issuer_weight"] = ({"lower": lower, "upper": upper}, cap, passed)
    passes = [rule[2] for rule in rules.values()]
    status = "fail" if False in passes else "insufficient_evidence" if None in passes else "pass"
    return status, rules


def _linear_paths(windows, baseline, metric, retention):
    qqq, reserve = SOURCES
    for window_id, (dates, growth) in windows.items():
        levels = [
            (fsum(baseline[ticker] * growth[ticker][i] for ticker in growth),
             growth[ISSUER][i] - growth[qqq][i],
             growth[ISSUER][i] - growth[reserve][i])
            for i in range(len(dates))
        ]
        if metric == "terminal_loss":
            first, x, y = levels[-1]
            yield (window_id, dates[0], dates[-1]), (first - retention, x, y)
            continue
        for later, (end, end_x, end_y) in enumerate(levels[1:], start=1):
            for earlier in range(later):
                peak, peak_x, peak_y = levels[earlier]
                yield (window_id, dates[earlier], dates[later]), (
                    end - retention * peak, end_x - retention * peak_x, end_y - retention * peak_y,
                )


def _slack(rule, point):
    constant, x, y = rule
    return constant + x * point[0] + y * point[1]


def _clip(polygon, rule):
    if not polygon:
        return []
    clipped = []
    previous = polygon[-1]
    prev_slack = _slack(rule, previous)
    for point in polygon:
        slack = _slack(rule, point)
        if (slack >= -BOUNDARY_EPSILON) != (prev_slack >= -BOUNDARY_EPSILON):
            fraction = prev_slack / (prev_slack - slack)
            fraction = min(1.0, max(0.0, fraction))
            clipped.append(tuple(start + fraction * (end - start) for start, end in zip(previous, point)))
        if slack >= -BOUNDARY_EPSILON:
            clipped.append(point)
        previous, prev_slack = point, slack
    return list(dict.fromkeys(clipped))


def _domain(target):
    return [(0.0, 0.0), (target, 0.0), (0.0, target)]


def _ordered_rules(windows, baseline, policy, exposures, *, conservative):
    for index, (ticker, rule) in enumerate(zip(SOURCES, ("qqq_funding_limit", "zst_funding_limit"))):
        cap = baseline[ticker] if ticker in policy["allowed_sources"] else 0.0
        yield (rule, None, None, None), cap, (
            cap, -1.0 if index == 0 else 0.0, -1.0 if index == 1 else 0.0,
        )
    floor = policy["reserve_floor"]
    yield ("reserve_floor", None, None, None), floor, (baseline[RESERVE] - floor, 0.0, -1.0)
    if policy.get("direct_cap") is not None:
        cap = policy["direct_cap"]
        yield ("direct_cap", None, None, None), cap, (cap - baseline[ISSUER], -1.0, -1.0)
    limit = policy["loss_limit"]
    if limit is not None:
        for observed, stress_rule in _linear_paths(windows, baseline, policy["metric"], 1 - limit):
            yield (policy["metric"], *observed), limit, stress_rule
    if policy.get("issuer_cap") is not None:
        cap = policy["issuer_cap"]
        default = 1.0 if conservative else 0.0
        coefficients = {ticker: amount if amount is not None else default for ticker, amount in exposures.items()}
        exposure = fsum(baseline[ticker] * coefficients[ticker] for ticker in coefficients)
        yield ("issuer_cap", None, None, None), cap, (
            cap - exposure,
            coefficients[SOURCES[0]] - coefficients[ISSUER],
            coefficients[SOURCES[1]] - coefficients[ISSUER],
        )


def _frontier(windows, baseline, policy, exposures, *, conservative=True):
    target = policy["target"]
    polygon = _domain(target)
    for _, _, rule in _ordered_rules(windows, baseline, policy, exposures, conservative=conservative):
        polygon = _clip(polygon, rule)
        if not polygon:
            break
    max_total = max((sum(point) for point in polygon), default=None)
    full = [point for point in polygon if abs(sum(point) - target) <= BOUNDARY_EPSILON]
    best = min((point for point in polygon if abs(sum(point) - max_total) <= BOUNDARY_EPSILON),
               key=lambda point: point[1]) if polygon else None
    status = ("feasible_full" if full else "no_feasible" if max_total is None else
              "feasible_partial" if policy["allow_smaller"] else "requested_size_infeasible")
    eligible = best is not None and (bool(full) or policy["allow_smaller"])
    return {
        "requested_total": target, "max_total": max_total if eligible else None,
        "diagnostic_max_total": max_total, "full_possible": bool(full), "status": status,
        "full_zst_min": min((point[1] for point in full), default=None),
        "full_zst_max": max((point[1] for point in full), default=None),
        "best_funding": dict(zip(SOURCES, best)) if eligible else None,
    }


def _binding_matches(binding, point, rules):
    if binding == "funding_domain":
        return min(point) <= BOUNDARY_EPSILON
    return any(identifier[0] == binding and abs(_slack(rule, point)) <= EPSILON
               for identifier, _, rule in rules)


def _verify_certificate(certificate, windows, baseline, policy, exposures):
    if certificate is None:
        return None
    if not isinstance(certificate, Mapping):
        return False
    required = {"rule", "window_id", "observation_date", "peak_date", "bound",
                "affine_constant", "coefficients", "max_slack"}
    if not required.issubset(certificate):
        return False
    key = tuple(certificate[field] for field in ("rule", "window_id", "peak_date", "observation_date"))
    points = _domain(policy["target"])
    kind = certificate.get("type")
    if kind not in ("combined_constraints", "single_constraint"):
        return False
    for observed, bound, rule in _ordered_rules(windows, baseline, policy, exposures, conservative=False):
        if not points:
            return False
        if observed == key:
            slack = max(_slack(rule, point) for point in points)
            coefficients = certificate["coefficients"]
            return (slack < -BOUNDARY_EPSILON and _matches(slack, certificate["max_slack"]) and
                    _matches(bound, certificate["bound"]) and
                    _matches(rule[0], certificate["affine_constant"]) and
                    _matches(rule[1], coefficients.get(SOURCES[0])) and
                    _matches(rule[2], coefficients.get(SOURCES[1])))
        if kind == "combined_constraints":
            points = _clip(points, rule)
    return False


def audit_decision(*, prices_cad, baseline, proposal, policy, metrics, evidence, maximum=None, dates=None,
                   issuer_context=None, official_starter=False, search_alternatives=True):
    """Audit reported metrics, funding and the best feasible counterfactual from raw inputs."""
    findings = []
    verified = {}

    def add(metric_id, status, message, **details):
        findings.append({"metric_id": metric_id, "status": status, "message": message, **details})

    def output(status):
        if any(item["status"] == "invalid" for item in findings):
            status = "invalid"
        elif status == "pass" and any(item["status"] == "insufficient_evidence" for item in findings):
            status = "insufficient_evidence"
        solver_status = verified.get("solver_status")
        frontier = verified.get("frontier", {})
        if status == "invalid":
            reason = "review_blocked"
        elif any(item["metric_id"] == "input.evidence" for item in findings):
            reason = "market_evidence_insufficient"
        elif solver_status == "no_feasible" and verified["baseline"]["status"] == "fail":
            reason = "baseline_breaches_policy"
        elif solver_status == "requested_size_infeasible":
            reason = "requested_size_infeasible"
        elif frontier.get("status") == "insufficient_evidence" or (
            status == "insufficient_evidence" and
            any(item["metric_id"] == "proposal.issuer_weight.policy" and item["status"] == "insufficient_evidence"
                for item in findings)
        ):
            reason = "issuer_evidence_insufficient"
        elif status == "insufficient_evidence":
            reason = "review_evidence_insufficient"
        else:
            reason = solver_status or status
        return {"status": status, "decision_reason": reason, "findings": findings, "verified": verified}

    try:
        assets = set(baseline.get("weights", baseline))
        if not {*SOURCES, ISSUER}.issubset(assets):
            raise ValueError("The frozen baseline must include NVDA, QQQ and ZST.TO.")
        baseline = _weights(baseline, assets)
        proposal_weights = _weights(proposal, assets)
        if not search_alternatives and (maximum is not None or any(
            key in metrics for key in ("maximum", "frontier", "solver_status", "certificate")
        )):
            raise ValueError("Alternative analysis was submitted without authorization.")
        maximum_weights = _weights(maximum, assets) if maximum is not None else None
        policy = dict(policy)
        policy["allow_smaller"] = policy.get("allow_smaller", True)
        if not isinstance(policy["allow_smaller"], bool):
            raise ValueError("The purchase size policy must use a boolean allow_smaller.")
        if not search_alternatives:
            policy["allow_smaller"] = False
        if policy["metric"] not in METRICS:
            raise ValueError("Unknown loss metric.")
        for key in ("target", "loss_limit", "reserve_floor", "direct_cap", "issuer_cap"):
            if key in ("loss_limit", "direct_cap", "issuer_cap") and policy.get(key) is None:
                continue
            policy[key] = _fraction(policy[key])
        policy["loss_limit"] = policy.get("loss_limit")
        allowed = set(policy["allowed_sources"])
        if not allowed.issubset(SOURCES):
            raise ValueError("The funding policy references an unsupported asset.")
        proposal_funding, proposal_total = _funding(baseline, proposal_weights, allowed, policy["target"])
        if maximum_weights is not None:
            maximum_funding, maximum_total = _funding(baseline, maximum_weights, allowed, policy["target"])
        sources = (evidence.get("price_source"), evidence.get("fx_source"))
        if evidence.get("basis") != "CAD" or any(not isinstance(source, str) or not source.strip() for source in sources):
            raise MissingEvidence("Source identifiers and CAD conversion provenance are required.")
        if official_starter and dates is not None:
            raise ValueError("Use the archived window boundaries to review starter replay dates.")
        spec = _window_specs(policy, dates)
        windows = _growth_windows(prices_cad, assets, spec, evidence.get("fx_dates"), official_starter=official_starter)
        exposures = _issuer_coefficients(policy, assets, evidence, issuer_context) if policy.get("issuer_cap") is not None else {}
        portfolio_roles = {"baseline": (baseline, None, None, None),
                           "proposal": (proposal_weights, proposal, proposal_funding, proposal_total)}
        if maximum_weights is not None:
            portfolio_roles["maximum"] = (maximum_weights, maximum, maximum_funding, maximum_total)
        for role, (weights, candidate, funding, total) in portfolio_roles.items():
            evaluation = _evaluate(windows, weights)
            claimed = metrics.get(role, candidate)
            _compare_evaluation(role, evaluation, claimed, weights, add)
            status, rules = _portfolio_verdict(weights, evaluation, policy, exposures, total)
            verified[role] = {
                **evaluation, "weights": weights, "status": status, "passes": status == "pass",
                "funding": funding, "total": total,
            }
            for metric, (actual, limit, passes) in rules.items():
                rule_status = {None: "insufficient_evidence", True: "pass", False: "fail"}[passes]
                add(f"{role}.{metric}.policy", rule_status, "Checked against the investor policy.",
                    actual=actual, limit=limit)
                if metric == "issuer_weight":
                    findings[-1]["covered_portfolio_weight"] = fsum(
                        weights[ticker] for ticker, exposure in exposures.items() if exposure is not None
                    )
            for report in (claimed,) if candidate is claimed else (claimed, candidate):
                if not isinstance(report, Mapping):
                    continue
                if "passes" in report and report["passes"] is not (status == "pass"):
                    add(f"{role}.passes", "invalid", "Reported suitability disagrees with the verified policy.")
                if "total" in report and total is not None and not _matches(total, report["total"]):
                    add(f"{role}.total", "invalid", "Reported purchase amount disagrees with the changes in weights.")
                if funding is not None and "funding" in report:
                    reported_funding = report["funding"]
                    if (not set(reported_funding).issubset(SOURCES) or
                            any(not _matches(amount, reported_funding.get(ticker, 0.0))
                                for ticker, amount in funding.items())):
                        add(f"{role}.funding", "invalid", "Reported funding disagrees with the changes in weights.")
        if not search_alternatives:
            return output(verified["proposal"]["status"])
        frontier = _frontier(windows, baseline, policy, exposures)
        issuer_unknown = policy.get("issuer_cap") is not None and None in exposures.values()
        if issuer_unknown:
            optimistic = _frontier(windows, baseline, policy, exposures, conservative=False)
            agrees = all(_matches(frontier[key], optimistic[key]) for key in (
                "status", "max_total", "full_possible", "full_zst_min", "full_zst_max"))
            if agrees and frontier["best_funding"] is not None:
                agrees = all(_matches(amount, optimistic["best_funding"][ticker])
                             for ticker, amount in frontier["best_funding"].items())
            if optimistic["status"] == "requested_size_infeasible":
                diagnostic = frontier["diagnostic_max_total"]
                if not _matches(diagnostic, optimistic["diagnostic_max_total"]):
                    diagnostic = None
                frontier = {**optimistic, "diagnostic_max_total": diagnostic}
                agrees = True
            if not agrees:
                verified["frontier"] = {"status": "insufficient_evidence",
                                        "known_safe": frontier, "optimistic": optimistic}
                add("frontier.issuer_weight", "insufficient_evidence", "Unknown issuer exposure changes the feasible region.")
                solver_status = metrics.get("solver_status")
                if solver_status not in (None, "insufficient_issuer_evidence"):
                    add("frontier.solver_status", "invalid", "The feasible region was reported as known with unresolved issuer exposure.")
                if maximum_weights is not None:
                    add("maximum.optimality", "invalid", "A best funding mix was reported before the feasible region was verified.")
                return output(verified["proposal"]["status"])
        verified["frontier"] = frontier
        claimed_frontier = metrics.get("frontier")
        if claimed_frontier is not None:
            keys = ["requested_total", "max_total", "full_possible", "full_zst_min", "full_zst_max"]
            if not policy["allow_smaller"] or "diagnostic_max_total" in claimed_frontier:
                keys.append("diagnostic_max_total")
            for key in keys:
                if not _matches(frontier[key], claimed_frontier.get(key)):
                    add(f"frontier.{key}", "invalid", "Reported feasible region disagrees with the independent calculation.",
                        actual=frontier[key], claimed=claimed_frontier.get(key))
            for endpoint in ("full_zst_min", "full_zst_max"):
                binding = claimed_frontier.get(f"{endpoint}_binding")
                if binding is None:
                    continue
                amount = frontier[endpoint]
                rules = _ordered_rules(windows, baseline, policy, exposures, conservative=True)
                if amount is None or not _binding_matches(binding, (policy["target"] - amount, amount), rules):
                    add(f"frontier.{endpoint}_binding", "invalid",
                        "Reported binding constraint is not active at the verified endpoint.")
        expected_status = frontier["status"]
        verified["solver_status"] = expected_status
        if metrics.get("solver_status", expected_status) != expected_status:
            add("frontier.solver_status", "invalid", "Reported solver status disagrees with the independent calculation.",
                actual=expected_status, claimed=metrics["solver_status"])
        if maximum_weights is not None:
            best = frontier["best_funding"]
            if (best is None or verified["maximum"]["status"] != "pass" or
                    any(not _matches(amount, best[ticker]) for ticker, amount in maximum_funding.items())):
                add("maximum.optimality", "invalid", "Reported counterfactual is not the best authorized funding mix.")
        if expected_status == "no_feasible":
            certificate = _verify_certificate(metrics.get("certificate"), windows, baseline, policy, exposures)
            verified["no_feasible_confirmed"] = True
            if certificate is False:
                add("frontier.certificate", "invalid", "Reported certificate does not prove infeasibility.")
            elif certificate:
                add("frontier.certificate", "pass", "The independently computed inequality excludes every authorized mix.")
            else:
                add("frontier.no_feasible", "pass", "The independent constraints exclude every authorized mix.")
        elif expected_status == "requested_size_infeasible":
            verified["requested_size_infeasible_confirmed"] = True
            add("frontier.requested_size", "pass", "The independent constraints exclude the required purchase size.")
        return output(verified["proposal"]["status"])
    except MissingEvidence as exc:
        add("input.evidence", "insufficient_evidence", str(exc))
        return output("insufficient_evidence")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        add("input.validation", "invalid", str(exc))
        return output("invalid")
