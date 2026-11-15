"""Index independently published metrics without storing a second numeric result."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .review_snapshot import fingerprint


@dataclass(frozen=True)
class _Measure:
    formula_id: str
    source: str
    unit: str
    denominator: str | None


_PORTFOLIO = "portfolio_nav"
_START = "portfolio_nav_at_window_start"
_PEAK = "portfolio_nav_at_drawdown_peak"
_HISTORICAL = "historical_risk_and_contributions"
_REPLAY = "portfolio_replay"
_RETURN = _Measure("terminal_return", _HISTORICAL, "percent", _START)
_LOSS = _Measure("terminal_loss", _HISTORICAL, "percent", _START)
_DRAWDOWN = _Measure("max_drawdown", _HISTORICAL, "percent", _PEAK)
_OBSERVATIONS = _Measure("aligned_observation_count", _REPLAY, "observations", None)
_PORTFOLIO_WEIGHT = _Measure("portfolio_weights", _REPLAY, "percent", _PORTFOLIO)
_FUNDING_WEIGHT = _Measure("authorized_funding_portfolio_weight", "funding", "percent", _PORTFOLIO)
_FUNDING = _Measure("authorized_funding", "funding", "percentage_points", _PORTFOLIO)
_ISSUER = _Measure("issuer_exposure", "issuer", "percent", _PORTFOLIO)
_ISSUER_CHANGE = _Measure("issuer_exposure_change", "issuer", "percentage_points", _PORTFOLIO)
_SECTOR = _Measure("sector_exposure", "sector", "percent", _PORTFOLIO)
_SECTOR_CHANGE = _Measure("sector_exposure_change", "sector", "percentage_points", _PORTFOLIO)
_POLICY_WEIGHT = _Measure("confirmed_portfolio_threshold", "policy", "percent", _PORTFOLIO)
_POLICY_PURCHASE = _Measure("confirmed_purchase_size", "policy", "percentage_points", _PORTFOLIO)
_AGE = _Measure("disclosure_age", "issuer", "days", None)
_WINDOW_MEASURES = {
    "terminal_return": _RETURN, "terminal_loss": _LOSS, "max_drawdown": _DRAWDOWN, "observations": _OBSERVATIONS,
}
_CONTRIBUTIONS = {
    "attribution": _Measure("terminal_return_contribution", _HISTORICAL, "percentage_points", _START),
    "drawdown_attribution": _Measure("drawdown_contribution", _HISTORICAL, "percentage_points", _PEAK),
}
_RULE_MEASURES = {
    "terminal_loss": _LOSS, "max_drawdown": _DRAWDOWN, "reserve_weight": _PORTFOLIO_WEIGHT,
    "issuer_weight": _ISSUER, "requested_size": _FUNDING,
}
_COMPARISON_MEASURES = {
    "proposal_terminal_loss": _LOSS, "proposal_max_drawdown": _DRAWDOWN,
    "proposal_issuer_lower": _ISSUER, "proposal_issuer_upper": _ISSUER,
    "eligible_max_total": _FUNDING, "diagnostic_max_total": _FUNDING,
    "full_zst_min": _FUNDING, "full_zst_max": _FUNDING,
    "proposal_reserve_headroom": _Measure("policy_headroom", _REPLAY, "percentage_points", _PORTFOLIO),
}
_FUNDING_FIELDS = ("requested_total", "max_total", "diagnostic_max_total", "full_zst_min", "full_zst_max")
_HISTORICAL_ASSUMPTIONS = ("cad_adjusted_closes", "buy_and_hold", "excluding_fees_taxes_and_intraday_prices")
_ASSUMPTIONS = {
    _HISTORICAL: _HISTORICAL_ASSUMPTIONS,
    _REPLAY: _HISTORICAL_ASSUMPTIONS,
    "funding": (*_HISTORICAL_ASSUMPTIONS, "authorized_sources_and_constraints"),
    "issuer": ("qualified_disclosures_only", "unknown_holdings_remain_bounded"),
    "sector": ("qualified_sector_evidence_only", "unknown_classifications_remain_bounded"),
    "policy": ("user_confirmed_inputs",),
}


def metric_id(*path):
    """Use dotted IDs with escaped dots and tildes in individual keys."""
    return ".".join(str(key).replace("~", "~0").replace(".", "~1") for key in path)


def _at(container, path):
    for key in path:
        if isinstance(container, dict) and isinstance(key, str):
            container = container.get(key)
        elif isinstance(container, list) and type(key) is int and 0 <= key < len(container):
            container = container[key]
        else:
            return None
    return container


def _is_number(value):
    return type(value) is int or type(value) is float and isfinite(value)


def resolve_metric(published, identifier):
    """Resolve a metric ID in a published report. Unknown IDs have no value."""
    if not isinstance(identifier, str):
        return None
    record = published.get("metric_records", {}).get(identifier)
    if not isinstance(record, dict) or record.get("metric_id") != identifier:
        return None
    path = record.get("value_ref")
    if not isinstance(path, list) or not path or path[0] == "metric_records":
        return None
    value = _at(published, path)
    return value if _is_number(value) else None


def _window(value, identifier):
    return {"id": identifier, "start": value.get("start"), "end": value.get("end")}


def _worst_window(values, field):
    windows = (row for row in values.get("windows", {}) if _is_number(values["windows"][row].get(field)))
    return max(windows, key=lambda row: values["windows"][row][field], default=None)


class _Context:
    def __init__(self, report):
        publication = report["publication"]
        self.review_id = publication["review_id"]
        versions = publication["versions"]
        self.versions = versions["formula_versions"]
        self.policy_version = versions["policy_version"]
        self.policy = report.get("policy", {})
        evidence = report.get("evidence", {})
        market = [evidence.get(key) for key in ("price_source", "fx_source") if evidence.get(key)]
        issuer = sorted(source for source in evidence.get("evidence_ids", ()) if source.startswith("issuer:"))
        sector = report.get("sector_analysis", {})
        sector_sources = [f"sector:{ticker}:{row['as_of']}" for ticker, row in sorted(sector.get("evidence", {}).items())]
        self.sources = {
            _HISTORICAL: market, _REPLAY: market, "funding": market + issuer,
            "issuer": issuer, "sector": sector_sources, "policy": [],
        }
        self.as_of = {
            "issuer": evidence.get("issuer_snapshot", {}).get("reference_date"),
            "sector": sector.get("reference_date"),
        }
        scenarios = report.get("scenarios", {})
        market_data = versions["inputs"].get("market_data", {})
        source_windows = market_data.get("windows") or scenarios.get("baseline", {}).get("windows", {})
        self.windows = {identifier: _window(row, identifier)
                        for identifier, row in source_windows.items()}
        portfolios = report["audit"]["verified"]
        common = {
            "weights": {key: portfolios[key]["weights"] for key in ("baseline", "proposal") if key in portfolios},
            "policy": self.policy, "versions": versions,
        }
        issuer_inputs = evidence.get("issuer_snapshot", {})
        market_inputs = {
            **common, "data": market_data,
            "source_ids": market, "windows": self.windows,
        }
        history_hash = fingerprint(market_inputs)
        self.hashes = {
            _HISTORICAL: history_hash, _REPLAY: history_hash,
            "funding": fingerprint({"history": history_hash, "issuer_inputs": issuer_inputs}),
            "issuer": fingerprint({**common, "issuer_inputs": issuer_inputs}),
            "sector": fingerprint({**common, "catalog_sha256": sector.get("catalog_sha256"),
                                   "evidence": sector.get("evidence", {}), "taxonomy": sector.get("taxonomy")}),
            "policy": fingerprint(common),
        }

    def formula_version(self, source):
        if source == "policy":
            return self.policy_version
        if source in {"issuer", "sector"}:
            source = "exposure"
        return self.versions[source]


class _Index:
    def __init__(self, published):
        self.published = published
        self.records = {}

    def add(self, context, path, measure, *, identifier=None, window_id=None, as_of=None, sources=None,
            assumptions=None, origin="reviewed_calculation"):
        if not _is_number(_at(self.published, path)):
            return
        identifier = identifier or metric_id(*path)
        source = measure.source
        windows = [context.windows[window_id]] if window_id in context.windows else []
        if window_id is None and source in {_HISTORICAL, "funding"}:
            windows = list(context.windows.values())
        self.records[identifier] = {
            "metric_id": identifier, "value_ref": list(path),
            "formula_id": measure.formula_id, "formula_version": context.formula_version(source),
            "unit": measure.unit, "denominator": measure.denominator,
            "stored_as": "fraction" if measure.unit in {"percent", "percentage_points"} else "count",
            "windows": windows, "as_of": as_of or context.as_of.get(source),
            "source_ids": context.sources[source] if sources is None else sources,
            "input_hash": context.hashes[source], "policy_version": context.policy_version,
            "assumptions": list(_ASSUMPTIONS[source] if assumptions is None else assumptions),
            "origin": origin, "verification_status": "verified",
            "review_id": context.review_id,
        }


def verified_rule_margins(findings):
    """Compute displayed breaches and headroom once from the reviewed rule inputs."""
    margins = {}
    for finding in findings:
        identifier = finding["metric_id"]
        status = finding["status"]
        if not identifier.endswith(".policy") or status not in {"pass", "fail"}:
            continue
        rule = identifier.split(".")[-2]
        if rule not in _RULE_MEASURES:
            continue
        actual, limit = finding.get("actual"), finding.get("limit")
        if isinstance(actual, dict):
            actual = actual.get("upper" if status == "pass" else "lower")
        if _is_number(actual) and _is_number(limit):
            difference = actual - limit if rule == "reserve_weight" else limit - actual
            key = "headroom" if status == "pass" else "breach"
            margins[identifier] = {key: max(0.0, difference if key == "headroom" else -difference)}
    return margins


def _policy_measure(context, key):
    if key == "target":
        return _POLICY_PURCHASE
    if key == "loss_limit":
        measure = _WINDOW_MEASURES[context.policy["metric"]]
        return _Measure("confirmed_historical_limit", "policy", measure.unit, measure.denominator)
    return _POLICY_WEIGHT


def _audit_records(index, context, published):
    verified = published["audit"]["verified"]
    for leg in ("baseline", "proposal", "maximum"):
        if (values := verified.get(leg)) is None:
            continue
        path = ("audit", "verified", leg)
        for field in ("terminal_loss", "max_drawdown"):
            index.add(context, (*path, field), _WINDOW_MEASURES[field], window_id=_worst_window(values, field))
        for identifier, row in values.get("windows", {}).items():
            window_path = (*path, "windows", identifier)
            for metric, measure in _WINDOW_MEASURES.items():
                index.add(context, (*window_path, metric), measure, window_id=identifier)
            for metric, measure in _CONTRIBUTIONS.items():
                for ticker in row.get(metric, {}):
                    index.add(context, (*window_path, metric, ticker), measure, window_id=identifier)
        for ticker in values.get("weights", {}):
            weight = _FUNDING_WEIGHT if leg == "maximum" else _PORTFOLIO_WEIGHT
            index.add(context, (*path, "weights", ticker), weight)
        for ticker in values.get("funding") or {}:
            index.add(context, (*path, "funding", ticker), _FUNDING)
        index.add(context, (*path, "total"), _FUNDING)
    frontier_path = ("audit", "verified", "frontier")
    for field in _FUNDING_FIELDS:
        index.add(context, (*frontier_path, field), _FUNDING)
    for ticker in (verified.get("frontier", {}).get("best_funding") or {}):
        index.add(context, (*frontier_path, "best_funding", ticker), _FUNDING)

    for key in ("target", "reserve_floor", "loss_limit", "issuer_cap"):
        if _is_number(context.policy.get(key)):
            index.add(context, ("policy", key), _policy_measure(context, key), origin="confirmed_input")
    for ticker in published.get("confirmed_scope", {}).get("starting_weights", {}):
        index.add(context, ("confirmed_scope", "starting_weights", ticker), _POLICY_WEIGHT,
                  origin="confirmed_input")


def _coverage_records(index, context, published):
    path = ("publication", "versions", "inputs", "market_data", "windows")
    for identifier, window in (_at(published, path) or {}).items():
        row = (*path, identifier)
        index.add(context, (*row, "observations"), _OBSERVATIONS, window_id=identifier)
        price_rows = _Measure("aligned_price_observation_count", _REPLAY, "observations", None)
        index.add(context, (*row, "price_observations"), price_rows, window_id=identifier)
        market_calendar = _Measure("reference_calendar_session_count", _REPLAY, "observations", None)
        calendar = window.get("coverage", {}).get("calendar_id")
        if calendar:
            index.add(context, (*row, "coverage", "expected_observations"), market_calendar,
                      window_id=identifier, sources=[calendar])


def _finding_records(index, context, published):
    audit = published["audit"]
    for row_number, finding in enumerate(audit["findings"]):
        name = finding["metric_id"]
        leg, *parts = name.split(".")
        if len(parts) != 2:
            continue
        identified = ("audit", "findings", name)
        path = ("audit", "findings", row_number)
        field, scope = parts
        if scope != "policy":
            measure = _WINDOW_MEASURES.get(scope)
            if measure:
                index.add(context, (*path, "actual"), measure,
                          identifier=metric_id(*identified, "actual"), window_id=field)
            continue
        if (measure := _RULE_MEASURES.get(field)) is None:
            continue
        window_id = _worst_window(audit["verified"].get(leg, {}), field)
        if isinstance(finding.get("actual"), dict):
            for bound in ("lower", "upper"):
                index.add(context, (*path, "actual", bound), measure,
                          identifier=metric_id(*identified, "actual", bound))
        else:
            index.add(context, (*path, "actual"), measure,
                      identifier=metric_id(*identified, "actual"), window_id=window_id)
        limit_measure = _Measure("confirmed_rule_limit", "policy", measure.unit, measure.denominator)
        index.add(context, (*path, "limit"), limit_measure, identifier=metric_id(*identified, "limit"),
                  origin="confirmed_input")
        coverage = _Measure("issuer_evidence_coverage", "issuer", "percent", _PORTFOLIO)
        index.add(context, (*path, "covered_portfolio_weight"), coverage,
                  identifier=metric_id(*identified, "covered_portfolio_weight"))
        for category in audit.get("rule_margins", {}).get(name, {}):
            margin = _Measure(f"policy_{category}", measure.source, "percentage_points", measure.denominator)
            index.add(context, ("audit", "rule_margins", name, category), margin, window_id=window_id)


def _exposure_records(index, context, published):
    for bound in ("lower", "upper"):
        index.add(context, ("exposure", "qqq_only", bound), _ISSUER)
        index.add(context, ("exposure_change", bound), _ISSUER_CHANGE,
                  assumptions=("qualified_disclosures_only", "shared_unknown_holdings_before_and_after"))

    sector = published.get("sector_analysis", {})
    for name in sector.get("sectors", {}):
        for key, measure in (("before", _SECTOR), ("after", _SECTOR), ("change", _SECTOR_CHANGE)):
            for bound in ("lower", "upper"):
                index.add(context, ("sector_analysis", "sectors", name, key, bound), measure)
    for key in ("unmapped", "known_non_equity_min"):
        for leg in ("before", "after"):
            index.add(context, ("sector_analysis", key, leg), _SECTOR)
    for ticker, evidence in sector.get("evidence", {}).items():
        path = ("sector_analysis", "evidence", ticker)
        source = [f"sector:{ticker}:{evidence['as_of']}"]
        measure = _Measure("sector_component_nav_share", "sector", "percent", "holding_nav")
        for name in evidence.get("sector_nav_lower", {}):
            index.add(context, (*path, "sector_nav_lower", name), measure, as_of=evidence["as_of"], sources=source)
        index.add(context, (*path, "non_equity_nav_lower"), measure, as_of=evidence["as_of"], sources=source)

    snapshot = published.get("evidence", {}).get("issuer_snapshot", {})
    scope_age = _Measure("disclosure_freshness_limit", "policy", "days", None)
    index.add(context, ("evidence", "issuer_snapshot", "max_age_days"), scope_age, origin="confirmed_input")
    for ticker, holding in snapshot.get("holdings", {}).items():
        as_of = holding.get("as_of")
        source = [f"issuer:{ticker}:{as_of}"] if as_of else []
        index.add(context, ("evidence", "issuer_snapshot", "holdings", ticker, "age_days"), _AGE,
                  as_of=snapshot.get("reference_date"), sources=source)
        qualified = _Measure("qualified_issuer_holding_fraction", "issuer", "percent", "holding_nav")
        index.add(context, ("evidence", "issuer_weights", ticker), qualified, as_of=as_of,
                  sources=source, origin="qualified_evidence")


def audit_metric_records(published):
    """Return stable IDs for the calculations and verified inputs in an audit report."""
    if not published["publication"]["independent_review_verified"]:
        return {}
    context = _Context(published)
    index = _Index(published)
    _audit_records(index, context, published)
    _finding_records(index, context, published)
    _exposure_records(index, context, published)
    _coverage_records(index, context, published)
    return index.records


def _challenge_comparison_records(index, context, leg, published, values):
    proposal = published[leg]["audit"]["verified"].get("proposal", {})
    selected = published[leg].get("policy", {}).get("metric")
    for field in values:
        measure = _COMPARISON_MEASURES.get(field)
        metric = {"proposal_terminal_loss": "terminal_loss", "proposal_max_drawdown": "max_drawdown"}.get(field)
        if field == "proposal_loss_headroom" and selected in _WINDOW_MEASURES:
            metric = selected
            measure = _Measure("policy_headroom", _HISTORICAL, "percentage_points",
                               _WINDOW_MEASURES[selected].denominator)
        if measure is None:
            continue
        window_id = _worst_window(proposal, metric)
        index.add(context, ("comparison", leg, field), measure, window_id=window_id)
        index.add(context, ("comparison", "differences", field, "before" if leg == "baseline" else "after"),
                  measure, window_id=window_id)


def challenge_metric_records(published):
    """Index the additional comparison and thresholds without copying leg-level records."""
    index = _Index(published)
    comparison = published["comparison"]
    for leg in ("baseline", "replay"):
        if (values := comparison.get(leg)) is not None:
            _challenge_comparison_records(index, _Context(published[leg]), leg, published, values)
    if not published["verified"]:
        return index.records

    context = _Context(published["baseline"])
    option = published.get("option") or {}
    threshold_source = option.get("value_unit")
    if threshold_source in {"days", "basis_points"}:
        denominator = _PORTFOLIO if threshold_source == "basis_points" else None
        threshold = _Measure("counterfactual_threshold", "policy", threshold_source, denominator)
        before_after = _POLICY_WEIGHT if threshold_source == "basis_points" else threshold
        for field in ("before", "after"):
            index.add(context, ("option", field), before_after, origin="counterfactual_input")
        for field in ("minimum_value", "maximum_value", "preset_value"):
            index.add(context, ("option", field), threshold, origin="counterfactual_input")
        index.add(context, ("confirmed_threshold", "value"), threshold, origin="confirmed_input")

    action = published.get("action") or {}
    for name, values in action.get("thresholds", {}).items():
        path = ("action", "thresholds", name)
        for field in ("known_lower", "potential_upper"):
            index.add(context, (*path, field), _ISSUER)
        allowance = _Measure("additional_issuer_exposure_allowance", "issuer", "percentage_points", _PORTFOLIO)
        index.add(context, (*path, "maximum_combined_additional_exposure"), allowance)
        index.add(context, (*path, "issuer_cap"), _POLICY_WEIGHT, origin="confirmed_input")
        for ticker in values.get("unknown_holdings", {}):
            index.add(context, (*path, "unknown_holdings", ticker), _ISSUER)
    return index.records
