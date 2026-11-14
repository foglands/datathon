"""Deterministic CAD portfolio replay and two-source funding frontier."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping

from .data import MarketData


BASE_WEIGHTS = {"SPY": 0.35, "XIU.TO": 0.25, "QQQ": 0.20, "ZST.TO": 0.20, "NVDA": 0.0}
FUNDING_SOURCES = ("QQQ", "ZST.TO")
TARGET_TICKER = "NVDA"
EPS = 1e-10


class MarketEvidenceError(ValueError):
    """The market inputs cannot support a complete historical replay."""


@dataclass(frozen=True)
class StressWindow:
    id: str
    label: str
    start: str
    end: str


STRESS_WINDOWS = (
    StressWindow("2022", "2022 stress replay", "2021-12-31", "2022-12-30"),
    StressWindow("2025", "Early 2025 stress replay", "2024-12-31", "2025-04-08"),
)

Point = tuple[float, float]


@dataclass(frozen=True)
class _Constraint:
    # Nonnegative slack is feasible. The coordinates are funding from QQQ and ZST.TO.
    rule: str
    constant: float
    a: float
    b: float
    window_id: str | None = None
    observation_date: str | None = None
    peak_date: str | None = None
    bound: float | None = None

    def slack(self, point: Point) -> float:
        return self.constant + self.a * point[0] + self.b * point[1]


def _fraction(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite fraction from 0 to 1")
    return float(value)


def _weights(weights: Mapping[str, float]) -> dict[str, float]:
    result = {ticker: _fraction(weight, f"{ticker} weight") for ticker, weight in weights.items()}
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0, abs_tol=EPS):
        raise ValueError("Portfolio weights must sum to 1")
    return result


def _prepare(data: MarketData, windows: Iterable[StressWindow], tickers: Iterable[str]):
    tickers = tuple(dict.fromkeys(tickers))
    common = set(data.fx)
    for ticker in tickers:
        if ticker not in data.prices:
            raise MarketEvidenceError(f"Starter prices do not include {ticker}.")
        common.intersection_update(data.prices[ticker])

    prepared = {}
    for window in windows:
        if window.id in prepared or window.start >= window.end:
            raise ValueError(f"Invalid or duplicate stress window: {window.id}")
        dates = sorted(day for day in common if window.start <= day <= window.end)
        if len(dates) < 2 or dates[0] != window.start or dates[-1] != window.end:
            raise MarketEvidenceError(f"Missing aligned price or FX endpoint for {window.label} "
                                      f"({window.start} to {window.end}).")
        for ticker, series in (("USD/CAD", data.fx), *((ticker, data.prices[ticker]) for ticker in tickers)):
            if any(isinstance(series[day], bool) or not isinstance(series[day], (int, float))
                   or not math.isfinite(series[day]) or series[day] <= 0 for day in dates):
                raise MarketEvidenceError(f"{ticker} contains an invalid observation in {window.label}.")
        prices = {ticker: tuple(data.prices[ticker][day] / data.prices[ticker][dates[0]] for day in dates)
                  for ticker in tickers}
        prepared[window.id] = (window, dates, prices)
    if not prepared:
        raise ValueError("At least one stress window is required")
    return prepared


def _evaluate(prepared, weights: Mapping[str, float]) -> dict:
    results = {}
    for window_id, (window, dates, prices) in prepared.items():
        values = [math.fsum(weight * prices[ticker][i] for ticker, weight in weights.items()) for i in range(len(dates))]
        peak_value, peak_index = values[0], 0
        mdd, worst_peak, worst_trough = 0.0, 0, 0
        for i, value in enumerate(values):
            if value > peak_value:
                peak_value, peak_index = value, i
            drawdown = 1.0 - value / peak_value
            if drawdown > mdd:
                mdd, worst_peak, worst_trough = drawdown, peak_index, i
        end_return = values[-1] - 1.0
        attribution = {ticker: weight * (prices[ticker][-1] - 1.0) for ticker, weight in weights.items()}
        results[window_id] = {
            "label": window.label, "start": window.start, "end": window.end,
            "terminal_return": end_return, "terminal_loss": max(0.0, -end_return),
            "max_drawdown": mdd, "peak_date": dates[worst_peak], "trough_date": dates[worst_trough],
            "observations": len(dates), "dates": list(dates), "values": values, "attribution": attribution,
            "drawdown_attribution": {
                ticker: weight * (prices[ticker][worst_peak] - prices[ticker][worst_trough]) / values[worst_peak]
                for ticker, weight in weights.items()
            },
        }
    return {"weights": dict(weights), "windows": results}


def evaluate_portfolio(data: MarketData, weights: Mapping[str, float], *, windows=STRESS_WINDOWS) -> dict:
    """Buy and hold at each window start, then report period loss and peak-to-trough drawdown."""
    portfolio = _weights(weights)
    prepared = _prepare(data, windows, (*BASE_WEIGHTS, *portfolio))
    return _evaluate(prepared, portfolio)


def _clip(points: list[Point], constraint: _Constraint) -> list[Point]:
    if not points:
        return []
    result = []
    previous, prev_slack = points[-1], constraint.slack(points[-1])
    for current in points:
        slack = constraint.slack(current)
        if (prev_slack < -EPS) != (slack < -EPS):
            portion = min(1.0, max(0.0, prev_slack / (prev_slack - slack)))
            result.append(tuple(old + portion * (new - old) for old, new in zip(previous, current)))
        if slack >= -EPS:
            result.append(current)
        previous, prev_slack = current, slack
    return list(dict.fromkeys(result))


def _risk_constraints(prepared, baseline: Mapping[str, float], metric: str, limit: float, target: float):
    for window_id, (_, dates, prices) in prepared.items():
        affine = []
        for i in range(len(dates)):
            value = math.fsum(weight * prices[ticker][i] for ticker, weight in baseline.items())
            a, b = (prices[TARGET_TICKER][i] - prices[source][i] for source in FUNDING_SOURCES)
            affine.append((value, a, b))

        if metric == "terminal_loss":
            value, a, b = affine[-1]
            yield _Constraint(metric, value - (1.0 - limit), a, b, window_id, dates[-1], dates[0], limit)
            continue

        # V_t / max_{s<=t}(V_s) >= 1 - L is equivalent to V_t >= (1 - L) * V_s
        # for every earlier s. Each portfolio value is affine in the two funding amounts.
        fraction_remaining = 1.0 - limit
        # A constraint strictly satisfied at every corner holds throughout the
        # purchase triangle. Running peaks let us screen all earlier dates at
        # once for a given trough. Keep a margin for rounding and binding checks.
        corners = [(value, value + a * target, value + b * target) for value, a, b in affine]
        scale = max(1.0, max(abs(component) for level in affine for component in level))
        margin = max(1e-8, 64 * math.ulp(scale))
        peak_zero, peak_qqq, peak_zst = corners[0]
        for low_index in range(1, len(affine)):
            zero, qqq, zst = corners[low_index]
            if (zero - fraction_remaining * peak_zero <= margin
                    or qqq - fraction_remaining * peak_qqq <= margin
                    or zst - fraction_remaining * peak_zst <= margin):
                value, a, b = affine[low_index]
                for high_index in range(low_index):
                    old_zero, old_qqq, old_zst = corners[high_index]
                    if (zero - fraction_remaining * old_zero > margin
                            and qqq - fraction_remaining * old_qqq > margin
                            and zst - fraction_remaining * old_zst > margin):
                        continue
                    old, old_a, old_b = affine[high_index]
                    yield _Constraint(metric, value - fraction_remaining * old,
                                      a - fraction_remaining * old_a, b - fraction_remaining * old_b,
                                      window_id, dates[low_index], dates[high_index], limit)
            peak_zero = max(peak_zero, zero)
            peak_qqq = max(peak_qqq, qqq)
            peak_zst = max(peak_zst, zst)


def _frontier_on_target(target: float, constraints: Iterable[_Constraint]):
    lower, upper, lower_rule, upper_rule = 0.0, target, "funding_domain", "funding_domain"
    for constraint in constraints:
        intercept = constraint.constant + constraint.a * target
        slope = constraint.b - constraint.a
        if abs(slope) < EPS:
            if intercept < -EPS:
                return None
            continue
        boundary = -intercept / slope
        if slope > 0 and boundary > lower:
            lower, lower_rule = boundary, constraint.rule
        if slope < 0 and boundary < upper:
            upper, upper_rule = boundary, constraint.rule
        if lower > upper + EPS:
            return None
    return max(0.0, lower), min(target, upper), lower_rule, upper_rule


def _certificate(constraint: _Constraint, points: list[Point], kind: str) -> dict:
    return {
        "type": kind, "rule": constraint.rule, "window_id": constraint.window_id,
        "observation_date": constraint.observation_date, "peak_date": constraint.peak_date,
        "bound": constraint.bound, "affine_constant": constraint.constant,
        "coefficients": dict(zip(FUNDING_SOURCES, (constraint.a, constraint.b))),
        "max_slack": max(constraint.slack(point) for point in points),
    }


def _best_point(polygon: list[Point], target: float, full) -> Point | None:
    if full is not None:
        return max(0.0, target - full[0]), max(0.0, full[0])
    if not polygon:
        return None
    maximum = max(sum(point) for point in polygon)
    return min((point for point in polygon if sum(point) >= maximum - EPS), key=lambda point: point[1])


def _same_point(first: Point | None, second: Point | None) -> bool:
    if first is None or second is None:
        return first is second
    return all(abs(a - b) <= EPS for a, b in zip(first, second))


def _candidate(prepared, baseline, point, candidate_id, policy) -> dict:
    x, y = point
    funding = dict(zip(FUNDING_SOURCES, (x, y)))
    weights = dict(baseline)
    for ticker, amount in funding.items():
        weights[ticker] = max(0.0, weights[ticker] - amount)
    weights[TARGET_TICKER] += x + y
    result = _evaluate(prepared, weights)
    metrics = {key: max(window[key] for window in result["windows"].values()) for key in ("terminal_loss", "max_drawdown")}
    metrics.update(reserve_weight=weights["ZST.TO"], direct_weight=weights[TARGET_TICKER])
    exposure = policy["issuer_exposure"]
    known_weight = math.fsum(weight for ticker, weight in weights.items() if exposure.get(ticker) is not None)
    known_issuer = math.fsum(weight * exposure[ticker] for ticker, weight in weights.items() if exposure.get(ticker) is not None)
    unknown_weight = math.fsum(weight for ticker, weight in weights.items() if exposure.get(ticker) is None)
    issuer_upper = min(1.0, known_issuer + unknown_weight)
    metrics.update(issuer_weight=known_issuer if known_weight >= 1.0 - EPS else None,
                   known_issuer_weight=known_issuer, issuer_upper_bound=issuer_upper, issuer_coverage=known_weight)

    cap = policy["loss_limit"]
    metric = policy["metric"]
    reserve = policy["reserve_floor"]
    checks = []
    if not policy["allow_smaller"] and candidate_id != "baseline":
        target = policy["target"]
        checks.append({"rule": "requested_size", "passed": abs(x + y - target) <= EPS,
                       "actual": x + y, "limit": target})
    if cap is not None:
        checks.extend(
            {"rule": metric, "passed": results[metric] <= cap + EPS, "actual": results[metric], "limit": cap,
             "window_id": name} for name, results in result["windows"].items()
        )
    checks.append({"rule": "reserve_floor", "passed": weights["ZST.TO"] >= reserve - EPS,
                   "actual": weights["ZST.TO"], "limit": reserve})
    for ticker, amount in funding.items():
        source_limit = baseline[ticker] if ticker in policy["allowed_sources"] else 0.0
        checks.append({"rule": "funding_limit", "ticker": ticker, "passed": amount <= source_limit + EPS,
                       "actual": amount, "limit": source_limit})
    if policy["direct_cap"] is not None:
        bound = policy["direct_cap"]
        checks.append({"rule": "direct_cap", "passed": weights[TARGET_TICKER] <= bound + EPS,
                       "actual": weights[TARGET_TICKER], "limit": bound})
    if policy["issuer_cap"] is not None:
        bound = policy["issuer_cap"]
        passed = False if known_issuer > bound + EPS else (True if issuer_upper <= bound + EPS else None)
        checks.append({"rule": "issuer_cap", "passed": passed,
                       "actual": metrics["issuer_weight"], "known_lower_bound": known_issuer,
                       "upper_bound": issuer_upper, "limit": bound})
    passed = all(check["passed"] is True for check in checks)
    result.update(id=candidate_id, funding=funding, total=x + y, metrics=metrics, checks=checks, passes=passed, feasible=passed)
    return result


def solve_funding(
    data: MarketData, *, target: float = 0.10, loss_limit: float | None = 0.14,
    metric: str = "terminal_loss", reserve_floor: float = 0.15,
    allowed_sources=FUNDING_SOURCES, direct_cap: float | None = None,
    issuer_cap: float | None = None, issuer_exposure: Mapping[str, float | None] | None = None,
    windows=STRESS_WINDOWS, baseline: Mapping[str, float] = BASE_WEIGHTS, allow_smaller: bool = True,
) -> dict:
    """Find eligible funding mixes while preserving ZST among equal purchase sizes."""
    target = _fraction(target, "target")
    if not isinstance(allow_smaller, bool):
        raise ValueError("allow_smaller must be a boolean")
    if loss_limit is not None:
        loss_limit = _fraction(loss_limit, "loss_limit")
    reserve_floor = _fraction(reserve_floor, "reserve_floor")
    if metric not in ("terminal_loss", "max_drawdown"):
        raise ValueError("metric must be terminal_loss or max_drawdown")
    if direct_cap is not None:
        direct_cap = _fraction(direct_cap, "direct_cap")
    if issuer_cap is not None:
        issuer_cap = _fraction(issuer_cap, "issuer_cap")
    sources = tuple(dict.fromkeys(allowed_sources))
    if set(sources) - set(FUNDING_SOURCES):
        raise ValueError("Only QQQ and ZST.TO can fund an NVDA purchase")
    exposure = {ticker: _fraction(weight, f"{ticker} issuer exposure") if weight is not None else None
                for ticker, weight in (issuer_exposure or {}).items()}
    exposure.setdefault(TARGET_TICKER, 1.0)
    base = _weights({**dict.fromkeys(BASE_WEIGHTS, 0.0), **baseline})
    prepared = _prepare(data, windows, base)
    policy = {
        "target": target, "loss_limit": loss_limit, "metric": metric, "reserve_floor": reserve_floor,
        "allow_smaller": allow_smaller,
        "allowed_sources": list(sources), "direct_cap": direct_cap, "issuer_cap": issuer_cap,
        "issuer_exposure": exposure, "windows": list(prepared),
    }

    x_cap, y_cap = (base[ticker] if ticker in sources else 0.0 for ticker in FUNDING_SOURCES)
    rules = [_Constraint("qqq_funding_limit", x_cap, -1.0, 0.0, bound=x_cap),
             _Constraint("zst_funding_limit", y_cap, 0.0, -1.0, bound=y_cap),
             _Constraint("reserve_floor", base["ZST.TO"] - reserve_floor, 0.0, -1.0, bound=reserve_floor)]
    if direct_cap is not None:
        rules.append(_Constraint("direct_cap", direct_cap - base[TARGET_TICKER], -1.0, -1.0, bound=direct_cap))
    if loss_limit is not None:
        rules.extend(_risk_constraints(prepared, base, metric, loss_limit, target))
    missing, pessimistic_issuer = [], None
    if issuer_cap is not None:
        missing = [ticker for ticker, weight in base.items() if weight > EPS and exposure.get(ticker) is None]
        if exposure[TARGET_TICKER] is None and TARGET_TICKER not in missing and target > EPS:
            missing.append(TARGET_TICKER)
        for assumption in ((0.0, 1.0) if missing else (0.0,)):
            amounts = {ticker: assumption if exposure.get(ticker) is None else exposure[ticker] for ticker in base}
            baseline_issuer = math.fsum(weight * amounts[ticker] for ticker, weight in base.items())
            a, b = (amounts[source] - amounts[TARGET_TICKER] for source in FUNDING_SOURCES)
            rule = _Constraint("issuer_cap", issuer_cap - baseline_issuer, a, b, bound=issuer_cap)
            if assumption == 0.0:
                rules.append(rule)
            else:
                pessimistic_issuer = rule

    start = [(0.0, 0.0), (target, 0.0), (0.0, target)] if target > 0 else [(0.0, 0.0)]
    polygon = start
    certificate = None
    for constraint in rules:
        clipped = _clip(polygon, constraint)
        if not clipped:
            strongest = min(rules, key=lambda rule: max(rule.slack(point) for point in start))
            if max(strongest.slack(point) for point in start) < -EPS:
                certificate = _certificate(strongest, start, "single_constraint")
            else:
                certificate = _certificate(constraint, polygon, "combined_constraints")
            polygon = []
            break
        polygon = clipped

    full = _frontier_on_target(target, rules) if polygon else None
    optimal = _best_point(polygon, target, full)
    diagnostic_max = sum(optimal) if optimal is not None else None
    smaller_possible = optimal is not None and full is None
    incomplete = False
    if pessimistic_issuer is not None and polygon:
        safe = _clip(polygon, pessimistic_issuer)
        safe_full = _frontier_on_target(target, (*rules, pessimistic_issuer)) if safe else None
        safe_optimal = _best_point(safe, target, safe_full)
        if not allow_smaller and smaller_possible:
            if safe_optimal is None or abs(diagnostic_max - sum(safe_optimal)) > EPS:
                diagnostic_max = None
        else:
            incomplete = not (_same_point(optimal, safe_optimal) and
                              _same_point(full[:2] if full else None, safe_full[:2] if safe_full else None))
        full, optimal = (None, None) if incomplete else (safe_full, safe_optimal)
    if not allow_smaller and full is None:
        optimal = None
    picks = {"baseline": (0.0, 0.0)}
    if x_cap >= target - EPS and "QQQ" in sources:
        picks["qqq_only"] = (target, 0.0)
    if y_cap >= target - EPS and "ZST.TO" in sources:
        picks["zst_only"] = (0.0, target)
    if full is not None:
        picks["max_zst_full"] = (max(0.0, target - full[1]), max(0.0, full[1]))
    if optimal is not None:
        picks["best"] = optimal

    candidates = {name: _candidate(prepared, base, point, name, policy) for name, point in picks.items()}
    best = candidates.get("best")
    if best is not None and not best["passes"]:
        raise ArithmeticError("Computed best funding fails its own checks")
    if incomplete:
        status = "insufficient_issuer_evidence"
    elif full is not None:
        status = "feasible_full"
    elif not allow_smaller and smaller_possible:
        status = "requested_size_infeasible"
    else:
        status = "feasible_partial" if best is not None else "no_feasible"
    frontier = {
        "requested_total": target, "max_total": best["total"] if best is not None else None,
        "diagnostic_max_total": diagnostic_max if not incomplete else None,
        "full_possible": full is not None,
        "full_zst_min": full[0] if full is not None else None,
        "full_zst_max": full[1] if full is not None else None,
        "full_zst_min_binding": full[2] if full is not None else None,
        "full_zst_max_binding": full[3] if full is not None else None,
        "missing_issuer_exposures": missing,
    }
    return {"status": status, "baseline": candidates["baseline"], "candidates": candidates,
            "best": best, "frontier": frontier, "certificate": certificate, "policy": policy}
