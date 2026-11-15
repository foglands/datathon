"""Review hypothetical allocations over common historical sessions."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from math import fsum, isclose
import re

from .data import verify_cad_conversion
from .finance import STRESS_WINDOWS, evaluate_portfolio
from .fund_benchmarks import apply_proxies, benchmark_proxies
from .governance import BOUNDARY_EPSILON, review_portfolio_comparison
from .market_calendar import STARTER_CALENDAR_ID, starter_replay_sessions
from .review_snapshot import FORMULA_VERSIONS, fingerprint
from .scope import EXTRA_WINDOW


_PRIORITY_BASIS = {
    "terminal_return": "highest_worst_window_return",
    "max_drawdown": "lowest_worst_window_drawdown",
    "terminal_loss": "lowest_worst_window_loss",
}
_WINDOW_FIELDS = (
    "terminal_return", "terminal_loss", "max_drawdown", "peak_date", "trough_date", "observations",
)
_SINGLE_KIND = "single_allocation"
_TICKER = re.compile(r"[A-Z][A-Z0-9_.-]{0,23}")


class _ReviewedAllocation(dict):
    def __init__(self, fields):
        super().__init__(fields)
        self._review_digest = fingerprint(self)


def _windows(include_2023):
    return (STRESS_WINDOWS[0], EXTRA_WINDOW, STRESS_WINDOWS[1]) if include_2023 else STRESS_WINDOWS


def comparison_assets(data, *, include_2023=False):
    """List symbols with prices on every pinned session of the selected windows."""
    required = frozenset().union(*(starter_replay_sessions(w.start, w.end) for w in _windows(include_2023)))
    if not required <= data.fx.keys():
        return ()
    return tuple(sorted(ticker for ticker, series in data.prices.items() if required <= series.keys()))


def _fraction(value, label):
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be a finite fraction between zero and one.")
    return float(value)


def _validated_options(options, market):
    result = {}
    for label, allocation in options.items():
        if not isinstance(label, str) or not label.strip() or len(label) > 80:
            raise ValueError("Each allocation needs a name of up to 80 characters.")
        if not isinstance(allocation, Mapping) or not allocation:
            raise ValueError("Each allocation needs at least one asset weight.")
        if not allocation.keys() <= market.prices.keys():
            raise ValueError("Select symbols present in the frozen market snapshot.")
        weights = {ticker: _fraction(weight, f"{ticker} weight") for ticker, weight in allocation.items()}
        if not isclose(fsum(weights.values()), 1.0, rel_tol=0, abs_tol=BOUNDARY_EPSILON):
            raise ValueError("The weights in each allocation must total 100%.")
        result[label] = {ticker: weight for ticker, weight in weights.items() if weight}
    return result


def _finding(priority, options, *, hold=None):
    eligible = [] if hold else [label for label, row in options.items() if row["max_drawdown_test"] != "fail"]
    finding = {"status": "unavailable", "option": None, "metric": priority,
               "basis": hold or "all_breach_cap", "eligible_options": eligible}
    if len(eligible) == 1:
        finding.update(status="difference", option=eligible[0], basis="cap_pass")
    elif len(eligible) == 2:
        if priority is None:
            finding.update(status="neutral", basis="no_priority")
            return finding
        left, right = eligible
        values = {label: options[label]["priority_value"] for label in eligible}
        if isclose(values[left], values[right], rel_tol=0, abs_tol=BOUNDARY_EPSILON):
            finding.update(status="tie", basis=_PRIORITY_BASIS[priority])
        else:
            select = max if priority == "terminal_return" else min
            finding.update(status="difference", option=select(eligible, key=values.__getitem__),
                           basis=_PRIORITY_BASIS[priority])
    return finding


def _withheld(priority, requirements, reason, *, single=False):
    report = {"status": "withheld", "priority": priority, "reason": reason,
              "requirements": requirements, "options": {}, "verification": {},
              "finding": _finding(priority, {}, hold="verification_unavailable")}
    if single:
        report["kind"] = _SINGLE_KIND
    return report


def _validated_proxy_context(record, context):
    if not isinstance(context, Mapping) or set(context) != {"requested_weights", "proxy_substitutions"}:
        raise ValueError("A proxy replay requires the original weights and explicit ticker substitutions.")
    if record.get("kind") != _SINGLE_KIND or len(record["options"]) != 1:
        raise ValueError("Proxy input provenance requires a reviewed single-allocation replay.")
    requested, substitutions = context["requested_weights"], context["proxy_substitutions"]
    if not isinstance(requested, Mapping) or not requested or not isinstance(substitutions, Mapping) or not substitutions:
        raise ValueError("The original weights and proxy substitutions must be nonempty mappings.")
    symbols = (*requested, *substitutions, *substitutions.values())
    if any(not isinstance(ticker, str) or not _TICKER.fullmatch(ticker) for ticker in symbols):
        raise ValueError("Proxy input provenance must use explicit ticker symbols.")
    if not substitutions.keys() <= requested.keys() or substitutions.keys() & substitutions.values():
        raise ValueError("Every substitution must map a requested ticker to a distinct replay ticker.")
    weights = {ticker: _fraction(weight, f"{ticker} weight") for ticker, weight in requested.items()}
    if not all(weights.values()) or not isclose(fsum(weights.values()), 1.0, rel_tol=0, abs_tol=BOUNDARY_EPSILON):
        raise ValueError("Requested weights must be positive and total 100%.")
    replay_weights = next(iter(record["options"].values()))["weights"]
    if dict(substitutions) != benchmark_proxies(weights, replay_weights):
        raise ValueError("The substitute tickers do not match the documented fund benchmark objectives.")
    aggregated_weights = apply_proxies(weights, substitutions)
    if aggregated_weights.keys() != replay_weights.keys() or any(
        not isclose(weight, replay_weights[ticker], rel_tol=0, abs_tol=BOUNDARY_EPSILON)
        for ticker, weight in aggregated_weights.items()
    ):
        raise ValueError("The substitutions and original weights differ from the independently reviewed replay.")
    return {"requested_weights": weights, "proxy_substitutions": dict(substitutions)}


def publish_allocation_comparison(report, *, replay_context=None):
    """Copy a reviewed replay for display and export, rejecting altered results."""
    single = isinstance(report, _ReviewedAllocation) and report.get("kind") == _SINGLE_KIND
    if isinstance(report, _ReviewedAllocation):
        try:
            snapshot = deepcopy(dict(report))
            if fingerprint(snapshot) == report._review_digest:
                if replay_context is not None and snapshot["options"]:
                    try:
                        snapshot["replay_context"] = _validated_proxy_context(snapshot, replay_context)
                    except ValueError as exc:
                        return _withheld(None, {}, str(exc), single=single)
                return snapshot
        except (TypeError, ValueError):
            pass
    subject = "allocation replay" if single else "comparison"
    return _withheld(None, {}, f"The {subject} changed after independent review. Confirm the inputs and rerun it.",
                     single=single)


def compare_allocations(data, options, *, priority=None, max_drawdown=None, include_2023=False, require_esg=False):
    """Compare two confirmed allocations using independently verified CAD replay results.

    Return only findings derived from the common replay windows. A requested
    but unassessed screen precludes an overall eligibility finding.
    """
    if priority is not None and (not isinstance(priority, str) or priority not in _PRIORITY_BASIS):
        raise ValueError("Select a supported historical comparison priority.")
    if not isinstance(options, Mapping) or len(options) != 2:
        raise ValueError("Enter exactly two allocations to compare.")
    return _replay_allocations(data, options, priority=priority, max_drawdown=max_drawdown,
                               include_2023=include_2023, require_esg=require_esg)


def analyze_allocation(data, weights, *, max_drawdown=None, include_2023=False, require_esg=False):
    """Independently verify historical CAD metrics for one confirmed allocation."""
    return _replay_allocations(data, {"Proposed allocation": weights}, priority=None, max_drawdown=max_drawdown,
                               include_2023=include_2023, require_esg=require_esg)


def _replay_allocations(data, options, *, priority, max_drawdown, include_2023, require_esg):
    single = len(options) == 1
    if type(include_2023) is not bool or type(require_esg) is not bool:
        raise ValueError("The additional replay and ESG controls must be explicit choices.")
    if max_drawdown is not None:
        max_drawdown = _fraction(max_drawdown, "Historical drawdown limit")
    confirmed = _validated_options(options, data)
    assets = frozenset().union(*(option.keys() for option in confirmed.values()))
    windows = _windows(include_2023)
    reference = frozenset().union(*(starter_replay_sessions(w.start, w.end) for w in windows))
    requirements = {
        "max_drawdown": {"status": "assessed" if max_drawdown is not None else "not_requested", "limit": max_drawdown},
        "esg": {"status": "unassessed" if require_esg else "not_requested"},
    }
    try:
        conversion = verify_cad_conversion(data, tickers=assets, windows=windows)
        if conversion["status"] != "verified":
            raise ValueError("Frozen price and exchange-rate sources are required for independent review.")
        # The archive defines the same joint Canadian and US dates for every allocation,
        # including assets with different exchange calendars.
        replay_data = replace(data, official_starter=True, fx={day: data.fx[day] for day in reference if day in data.fx})
        candidates = {
            label: evaluate_portfolio(replay_data, dict.fromkeys(sorted(assets), 0.0) | weights,
                                      windows=windows, aligned_tickers=())
            for label, weights in confirmed.items()
        }
        checked, dates = review_portfolio_comparison(replay_data, confirmed, candidates, windows=windows)
    except (ValueError, OverflowError) as exc:
        if max_drawdown is not None:
            requirements["max_drawdown"]["status"] = "unassessed"
        subject = "allocation replay" if single else "comparison"
        return _ReviewedAllocation(_withheld(priority, requirements, f"Historical {subject} withheld. {exc}", single=single))

    published = {}
    for label, weights in confirmed.items():
        rows = checked[label]
        worst_drawdown = max(row["max_drawdown"] for row in rows.values())
        cap_result = "not_requested"
        if max_drawdown is not None:
            cap_result = "pass" if worst_drawdown <= max_drawdown + BOUNDARY_EPSILON else "fail"
        worst = min if priority == "terminal_return" else max
        published[label] = {
            "weights": weights,
            "windows": {window.id: {"label": window.label, "start": window.start, "end": window.end,
                                    **{field: rows[window.id][field] for field in _WINDOW_FIELDS}}
                        for window in windows},
            "max_drawdown_test": cap_result,
            "priority_value": worst(row[priority] for row in rows.values()) if priority is not None else None,
        }
    verification = {
        "method": "Independent CAD price and buy-and-hold replay recomputation",
        "method_version": FORMULA_VERSIONS["portfolio_replay"],
        "basis": "CAD",
        "sources": [row.copy() for row in data.metadata if row["file"] in ("prices_daily.csv", "fx_usdcad_daily.csv")],
        "cad_conversion": conversion,
        "windows": {window.id: {"start": window.start, "end": window.end, "observations": len(dates[window.id]),
                                "calendar_id": STARTER_CALENDAR_ID, "aligned_dates": dates[window.id]}
                    for window in windows},
    }
    report = {
        "status": "limited" if require_esg else "verified",
        "priority": priority,
        "reason": "Independent review verified the financial replay. Dated evidence for the required ESG screen is unavailable."
                  if require_esg else "",
        "requirements": requirements,
        "options": published,
        "finding": _finding(priority, published, hold="esg_unassessed" if require_esg else None),
        "verification": verification,
    }
    if single:
        report["kind"] = _SINGLE_KIND
        report["finding"].update(option=None, status="unavailable" if require_esg else "neutral",
                                 basis="esg_unassessed" if require_esg else "single_allocation")
    verification["review_id"] = fingerprint(report)
    return _ReviewedAllocation(report)
