"""Render the verified parts of a portfolio audit in Streamlit."""

from __future__ import annotations

from typing import Any


_STATUS = {
    "pass": "Meets the tested rules",
    "fail": "Breaches a tested rule",
    "insufficient_evidence": "Evidence is incomplete",
    "invalid": "Review blocked the result",
    "execution_error": "Audit could not complete",
    "needs_input": "Clarification needed",
}
_OUTCOME = {
    "feasible_full": "Full purchase fits",
    "feasible_partial": "Smaller purchase fits",
    "requested_size_infeasible": "Required size is infeasible",
    "no_feasible": "No eligible funding mix",
    "insufficient_evidence": "Alternative remains unresolved",
}
_RULE = {
    "reserve_weight": "Minimum ZST.TO weight",
    "reserve_floor": "Minimum ZST.TO weight",
    "terminal_loss": "Terminal loss",
    "max_drawdown": "Maximum drawdown",
    "issuer_weight": "NVIDIA issuer exposure",
    "issuer_cap": "NVIDIA issuer exposure",
    "direct_weight": "Direct NVIDIA weight",
    "requested_size": "Exact purchase size",
    "qqq_funding_limit": "QQQ funding limit",
    "zst_funding_limit": "ZST.TO funding limit",
}
_ROLES = {
    "profile": "Profile",
    "evidence": "Evidence",
    "exposure": "Exposure",
    "scenario": "Scenario",
    "alternatives": "Alternatives",
    "review": "Review",
    "explanation": "Explanation",
    "sector": "Sector",
}
_HOLDING_REASONS = {
    "missing_holding_disclosure": "No eligible holding disclosure is available.",
    "scope_assumption_is_unverified": "The fund strategy alone does not verify its NVIDIA weight.",
    "invalid_publication_date": "The publication date is malformed or predates the snapshot.",
    "missing_publication_date": "The publication date is unavailable.",
    "publication_after_knowledge_cutoff": "The disclosure was published after the selected cutoff.",
    "holdings_after_reference_date": "The holdings date is after the selected reference date.",
    "holdings_older_than_max_age": "The holdings observation is older than the selected maximum age.",
    "invalid_or_inconsistent_holdings_date": "The holding date cannot be matched to the snapshot.",
    "incompatible_issuer_scope": "The disclosure does not match this audit's NVIDIA common-equity scope.",
}


def _percent(value: Any) -> str:
    return f"{value:.2%}" if value is not None else "Unavailable"


def _points(value: float) -> str:
    if 0 < value < .0001:
        return "less than 0.01 pp"
    return f"{value * 100:.2f} pp"


def _interval(bounds: dict) -> str:
    return f"{_percent(bounds.get('lower'))} to {_percent(bounds.get('upper'))}"


def _verified(report: dict) -> dict:
    return report.get("audit", {}).get("verified", {})


def _funding_range(frontier: dict) -> str | None:
    if not frontier.get("full_possible"):
        return None
    lower, upper = frontier.get("full_zst_min"), frontier.get("full_zst_max")
    if lower is None or upper is None:
        return None
    return _points(lower) if lower == upper else f"{_points(lower)} to {_points(upper)}"


def result_label(report: dict) -> str:
    """Return the independently verified funding outcome for a comparison."""
    status = report.get("status")
    if status in ("execution_error", "invalid", "needs_input", "insufficient_evidence"):
        return _STATUS[status]
    if report.get("unassessed_requirements"):
        return "Original proposal · limited assessment"
    if report.get("search_alternatives") is False:
        return _STATUS.get(status, "Awaiting independent review")
    verified = _verified(report)
    frontier = verified.get("frontier", {})
    outcome = verified.get("solver_status") or frontier.get("status")
    if outcome == "feasible_partial" and (frontier.get("max_total") or 0) <= 1e-9:
        return "Only the starting portfolio fits"
    if outcome == "feasible_full" and (funding_range := _funding_range(frontier)):
        return f"Full purchase fits · ZST.TO funding {funding_range}"
    return _OUTCOME.get(outcome, _STATUS.get(status, "Awaiting independent review"))


def _policy_findings(report: dict, portfolio: str) -> list[dict]:
    return [
        item for item in report.get("audit", {}).get("findings", ())
        if item["metric_id"].startswith(f"{portfolio}.") and item["metric_id"].endswith(".policy")
    ]


def _exposure_for(report: dict, label: str) -> dict:
    finding = next(
        (item for item in _policy_findings(report, label) if item["metric_id"].endswith(".issuer_weight.policy")), {}
    )
    return finding.get("actual", {})


def _render_portfolio(st: Any, report: dict, label: str, heading: str, data: dict) -> None:
    st.markdown(f"**{heading}**")
    status = data.get("status")
    if status == "pass":
        st.success(_STATUS[status], icon="✅")
    elif status == "fail":
        st.error(_STATUS[status], icon="⛔")
    else:
        st.warning(_STATUS.get(status, "Independent result unavailable"))

    policy = report.get("policy", {})
    metric = policy.get("metric")
    if policy.get("issuer_cap") is not None and (bounds := _exposure_for(report, label)):
        st.metric("NVIDIA exposure range", _interval(bounds))
        issuer_finding = next(item for item in _policy_findings(report, label)
                              if item["metric_id"].endswith(".issuer_weight.policy"))
        coverage = issuer_finding.get("covered_portfolio_weight")
        st.caption(f"Issuer cap {_percent(policy['issuer_cap'])} · exposure evidence covers {_percent(coverage)} of portfolio weight.")
    else:
        key = "max_drawdown" if metric == "max_drawdown" else "terminal_loss"
        st.metric(_RULE[key], _percent(data.get(key)))
        st.caption("Worst result across the selected historical windows.")

    weights = data.get("weights", {})
    st.write(f"NVIDIA weight **{_percent(weights.get('NVDA'))}** · ZST.TO weight **{_percent(weights.get('ZST.TO'))}**")
    if funding := data.get("funding"):
        sources = [f"{asset} **{_points(amount)}**" for asset, amount in funding.items() if amount > 1e-9]
        if sources:
            st.caption("Funding: " + " · ".join(sources))


def _render_frontier(st: Any, report: dict, verified: dict) -> None:
    frontier = verified.get("frontier", {})
    outcome = verified.get("solver_status") or frontier.get("status")
    st.markdown("**Verified alternatives**")

    if outcome == "insufficient_evidence" or report.get("status") == "insufficient_evidence":
        st.warning(_OUTCOME["insufficient_evidence"])
        if bounds := report.get("exposure", {}).get("qqq_only"):
            st.write(f"QQQ-funded proposal: **{_percent(bounds.get('lower'))}** documented NVIDIA exposure.")
            st.caption(
                f"Diagnostic range {_interval(bounds)}. The audit cannot establish that this "
                "illustrative allocation meets the issuer cap."
            )
    elif outcome == "feasible_full" and frontier.get("full_possible"):
        st.success(_OUTCOME[outcome], icon="✅")
    elif outcome == "requested_size_infeasible":
        st.error(_OUTCOME[outcome], icon="⛔")
    elif outcome == "feasible_partial" and (amount := frontier.get("max_total")) is not None:
        st.info(result_label(report))
        if amount > 1e-9:
            st.write(f"The allowed smaller purchase can reach **{_points(amount)}**.")
    elif outcome == "no_feasible":
        st.error(_OUTCOME[outcome], icon="⛔")
        st.caption("The independent search excluded every permitted size and funding mix.")
    else:
        st.info("Independent funding result unavailable.")


def _render_constraints(st: Any, report: dict, verified: dict, has_alternative: bool) -> None:
    show_boundary = report.get("search_alternatives", True) and not report.get("unassessed_requirements")
    left, right = st.columns(2) if show_boundary else (st.container(), None)
    with left:
        st.markdown("**What drove the decision**")
        flagged = [
            (heading, finding)
            for label, heading in (("baseline", "Starting portfolio"), ("proposal", "Original proposal"))
            for finding in _policy_findings(report, label)
            if finding["status"] != "pass"
        ]
        for label, finding in flagged:
            rule = finding["metric_id"].split(".")[-2]
            actual = finding.get("actual")
            actual_text = _interval(actual) if isinstance(actual, dict) else _percent(actual)
            verdict = "breach" if finding["status"] == "fail" else "unresolved"
            limit = finding.get("limit")
            matching_actual = actual.get("lower") if isinstance(actual, dict) else actual
            delta = 0
            if matching_actual is not None and limit is not None:
                delta = limit - matching_actual if rule == "reserve_weight" else abs(matching_actual - limit)
            margin = f" Breach size: {_points(delta)}." if verdict == "breach" and delta > 0 else ""
            st.write(f"{label} · **{_RULE.get(rule, rule)}**: {actual_text} vs. {_percent(limit)} ({verdict}).{margin}")
        if not flagged:
            st.caption("The independent review found no breach in the displayed proposal rules.")
    if right is None:
        return
    with right:
        st.markdown("**Funding boundary and headroom**")
        frontier = verified.get("frontier", {})
        if report.get("status") != "insufficient_evidence" and (funding_range := _funding_range(frontier)):
            st.write(f"ZST.TO can fund **{funding_range}** of the portfolio, with the remainder from QQQ.")
        if any(row["metric_id"] == "frontier.certificate" and row["status"] == "pass"
               for row in report.get("audit", {}).get("findings", ())):
            st.write("Independent review verified an infeasibility certificate.")
        if has_alternative:
            for finding in _policy_findings(report, "maximum"):
                rule = finding["metric_id"].split(".")[-2]
                value, bound = finding.get("actual"), finding.get("limit")
                if isinstance(value, dict):
                    value = value.get("upper")
                if rule == "requested_size":
                    continue
                if finding["status"] == "pass" and isinstance(value, (int, float)) and isinstance(bound, (int, float)):
                    headroom = value - bound if rule == "reserve_weight" else bound - value
                    st.write(f"{_RULE.get(rule, rule)} headroom: **{_points(max(headroom, 0.0))}**.")
        elif frontier.get("status") == "insufficient_evidence":
            st.caption("Unresolved holdings can change the feasible funding range.")


def render_comparison(report: dict) -> None:
    """Compare verified portfolios, withhold blocked results and show eligible alternatives."""
    import streamlit as st

    status = report.get("status")
    if status in ("execution_error", "invalid"):
        st.error(_STATUS[status])
        st.write(report.get("explanation") or "The independent review did not release a result.")
        return
    if status == "needs_input":
        st.warning(report.get("explanation") or _STATUS[status])
        return

    verified = _verified(report)
    if not (verified.get("baseline") and verified.get("proposal")):
        st.warning(report.get("explanation") or "The independent portfolio comparison is unavailable.")
        return

    if report.get("explanation"):
        st.write(report["explanation"])
    if report.get("unassessed_requirements"):
        st.warning("Assessment limited · Some stated requirements remain unevaluated.")
    search = report.get("search_alternatives", True)
    show_alternative = search and not report.get("unassessed_requirements")
    baseline, proposal, *alternatives = st.columns(3 if show_alternative else 2)
    with baseline.container(border=True):
        _render_portfolio(st, report, "baseline", "Starting portfolio", verified["baseline"])
    with proposal.container(border=True):
        _render_portfolio(st, report, "proposal", "Original proposal", verified["proposal"])
    maximum = verified.get("maximum") or {}
    has_alternative = bool(show_alternative and status != "insufficient_evidence" and
                           maximum.get("passes") is True and (maximum.get("total") or 0) > 1e-9)
    if alternatives:
        with alternatives[0].container(border=True):
            if has_alternative:
                prefers_reserve = report.get("policy", {}).get("prefer_reserve") is True
                heading = "Verified alternative" if prefers_reserve else "Verified funding example"
                _render_portfolio(st, report, "maximum", heading, maximum)
                if not prefers_reserve:
                    st.caption("This example uses the largest eligible purchase. If several mixes reach that size, "
                               "the calculation shows the one that sells the least ZST.TO.")
            else:
                _render_frontier(st, report, verified)
    elif not search:
        st.caption("Alternative funding search · skipped by request.")
    _render_constraints(st, report, verified, has_alternative)


def _render_requirements(st: Any, report: dict) -> None:
    if rows := report.get("requirements"):
        with st.expander("Requirements and coverage", expanded=bool(report.get("unassessed_requirements"))):
            def label(value):
                return value.replace("_", " ").capitalize() if value else "—"

            st.table([
                {"Requirement": row.get("label") or label(row.get("code")),
                 "Assessment": label(row.get("task_status")), "Rule verdict": label(row.get("verdict")),
                 "Evidence": ", ".join(row.get("evidence_ids", ())) or "—"}
                for row in rows
            ])


def _render_exposure_changes(st: Any, report: dict) -> None:
    verification = report.get("publication", {}).get("section_verification", {})
    for section, label in (("exposure_change", "NVIDIA issuer exposure change"), ("sector_analysis", "Sector exposure")):
        status = verification.get(section)
        if status == "invalid":
            st.warning(f"{label} withheld because its verification failed.")
        elif status == "unavailable":
            st.caption(f"{label} is unavailable for independent verification.")

    if verification.get("exposure_change") == "verified" and (bounds := report.get("exposure_change")):
        st.caption(f"NVIDIA issuer exposure change · {_points(bounds['lower'])} to {_points(bounds['upper'])}."
                   " Independently verified using the same unknown holdings before and after the trade.")
    if verification.get("sector_analysis") == "verified" and (sector := report.get("sector_analysis")):
        sectors = sector.get("sectors", {})
        taxonomy = sector["taxonomy"]
        with st.expander("Sector exposure · descriptive"):
            st.caption(f"Independently verified · {sector['status'].capitalize()} evidence coverage.")
            st.caption(f"Classification · {taxonomy['name']} ({taxonomy['version']})")
            if sectors:
                st.table([
                    {"Sector": name, "Starting": _interval(row["before"]), "Original proposal": _interval(row["after"]),
                     "Change": f"{_points(row['change']['lower'])} to {_points(row['change']['upper'])}"}
                    for name, row in sectors.items()
                ])


def _render_risk_drivers(st: Any, report: dict, verified: dict) -> None:
    windows = verified.get("proposal", {}).get("windows", {})
    if not windows:
        return
    metric = report.get("policy", {}).get("metric")
    metric = "max_drawdown" if metric == "max_drawdown" else "terminal_loss"
    window_id, row = max(windows.items(), key=lambda item: item[1][metric])
    drawdown = metric == "max_drawdown"
    attribution = row.get("drawdown_attribution" if drawdown else "attribution")
    if not attribution:
        return
    impacts = sorted(attribution.items(), key=lambda item: (-abs(item[1]), item[0]))
    largest = [
        f"{ticker} {'added' if amount > 0 else 'offset'} {_points(abs(amount))}"
        for ticker, value in impacts[:2]
        if abs(amount := value if drawdown else -value) > 1e-9
    ]
    if not largest:
        return
    st.markdown("**Historical risk drivers · original proposal**")
    details = f"{window_id} replay · {_RULE[metric]} {_percent(row[metric])}"
    if drawdown:
        details += f" · Peak {row['peak_date']} · Trough {row['trough_date']}"
    elif row["terminal_loss"] == 0 and row.get("terminal_return", 0) > 0:
        details += f" · Net gain {_percent(row['terminal_return'])}"
    st.caption(details)
    st.write(" · ".join(largest))


def render_evidence(report: dict) -> None:
    """Show timelines, source records, independent findings and actual tool activity."""
    import streamlit as st

    evidence = report.get("evidence", {})
    _render_requirements(st, report)
    _render_exposure_changes(st, report)
    with st.expander("Evidence and calculation method"):
        windows = report.get("scenarios", {}).get("baseline", {}).get("windows", {})
        if windows:
            st.write("**Historical replay**")
            st.caption("CAD adjusted closes on common observation dates. Each replay starts with the displayed weights and holds them through the window. Fees, taxes and intraday moves are outside this calculation.")
            st.table([
                {"Window": label, "Start": row["start"], "End": row["end"], "Observations": row["observations"]}
                for label, row in windows.items()
            ])
            if report.get("status") not in {"invalid", "execution_error"}:
                verified = _verified(report)
                example = ("Verified alternative" if report.get("policy", {}).get("prefer_reserve") is True
                           else "Verified funding example")
                figures = [
                    {"Portfolio": heading, "Window": window, "Terminal return": _percent(row["terminal_return"]),
                     "Terminal loss": _percent(row["terminal_loss"]),
                     "Maximum drawdown": _percent(row["max_drawdown"])}
                    for key, heading in (("baseline", "Starting portfolio"), ("proposal", "Original proposal"),
                                         ("maximum", example))
                    for window, row in verified.get(key, {}).get("windows", {}).items()
                ]
                if figures:
                    st.caption(f"Original proposal replay: {len(verified.get('proposal', {}).get('windows', {}))} of "
                               f"{len(evidence.get('windows', windows))} required historical windows recomputed.")
                    st.table(figures)
                    _render_risk_drivers(st, report, verified)
        elif report.get("decision_reason") == "market_evidence_insufficient":
            st.warning("Historical replay evidence is unavailable for a required window.")
        for row in evidence.get("market_sources", {}).values():
            provider = f"[{row['source']}]({row['source_url']})"
            st.write(f"**{row['file']}** · {provider} · retrieved {row['retrieved_on']}")
            if row.get("limitations"):
                st.caption(row["limitations"])
        if snapshot := evidence.get("issuer_snapshot"):
            st.write("**Issuer holdings**")
            st.caption(
                f"Base snapshot observation date: {snapshot['as_of'] or 'Unknown'}. "
                f"Reference date: {snapshot['reference_date']}. Publication cutoff: {snapshot['publication_cutoff']}. "
                f"Prototype maximum age: {snapshot['max_age_days']} days. These dates apply to issuer "
                "disclosures separately from the historical price replays."
            )
            for ticker, row in snapshot.get("holdings", {}).items():
                status = row.get("status")
                if status == "direct":
                    st.markdown(f"**{ticker}** · Direct position, counted in full")
                    continue
                value = _percent(row.get("weight")) if status == "disclosed" else status.replace("_", " ").capitalize()
                observed = row.get("as_of")
                published = row.get("published_on")
                dates = f" · observed {observed}" if observed else ""
                if published:
                    dates += f" · published {published}"
                if row.get("age_days") is not None:
                    dates += f" · {row['age_days']} days since observation"
                url = row.get("url") or ""
                locator = f" · {row['source_locator']}" if row.get("source_locator") else ""
                source = f" · [Source]({url})" if url.startswith(("https://", "http://")) else ""
                st.markdown(f"**{ticker}** · {value}{dates}{source}{locator}")
                if status != "disclosed":
                    st.caption(_HOLDING_REASONS.get(row["reason"], "The disclosure cannot be used to verify this holding."))
        if evidence.get("evidence_ids"):
            st.caption("Source identifiers")
            st.code("\n".join(evidence["evidence_ids"]), language=None)
        if findings := report.get("audit", {}).get("findings"):
            st.json(findings, expanded=False)
        if not evidence and not windows:
            st.caption("No verified source snapshot is available for this run.")

    with st.expander("Agent activity and AWS trace"):
        trace = report.get("trace", ())
        aws = [event for event in trace if event.get("event") == "bedrock" and event.get("status") == "success"]
        if aws:
            st.caption(f"{len(aws)} successful Amazon Bedrock response(s) recorded in this run.")
        elif report.get("mode") == "offline":
            st.caption("Offline replay. Roles are simulated locally for this run.")
        else:
            st.caption("No successful Amazon Bedrock response was recorded in this run.")
        routing = [row for row in trace if row.get("event") in ("tool_routing", "role_skipped")]
        if routing:
            st.table([
                {"Role": _ROLES.get(row.get("role"), row.get("role", "")), "Action": row.get("tool_name") or "Skip",
                 "Result": row["status"].replace("_", " "),
                 "Policy inputs": ", ".join(f"{key}={value}" for key, value in row.get("arguments", {}).items()
                                            if value not in ("", [])),
                 "Reason": row.get("reason") or ", ".join(row.get("invalid_fields", ()))}
                for row in routing
            ])
            if any(row["status"] == "deterministic_fallback" for row in routing):
                st.caption("Python applied the confirmed policy when a routed agent did not supply a usable tool result.")
        rows = [
            {"Role": _ROLES.get(row.get("role"), row.get("role", "")),
             "Action": row.get("tool_name") or row.get("operation") or row.get("event", ""),
             "Status": row.get("status", ""), "Request ID": row.get("request_id") or ""}
            for row in trace
            if row.get("event") in ("tool", "bedrock", "offline_role", "agent_end", "policy_confirmed", "loss_metric_selected")
        ]
        if rows:
            st.table(rows)
        if trace:
            st.json(trace, expanded=False)
