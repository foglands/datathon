"""Build the user-visible audit from independently checked facts."""

from __future__ import annotations

from copy import deepcopy

from .counterfactual import _comparison, _issuer_thresholds, _summary
from .finance import STRESS_WINDOWS
from .scope import EXTRA_WINDOW


_AUDITED = {"pass", "fail", "insufficient_evidence"}
_TRACE_FIELDS = {
    "role", "event", "status", "operation", "model_id", "region", "kind", "mode", "run_id",
    "tool_name", "tool_use_id", "request_id", "http_status", "retry_attempts", "throttled",
    "input_tokens", "output_tokens", "total_tokens", "cache_read_input_tokens", "cache_write_input_tokens",
    "duration_ms", "stop_reason", "agent_status", "threshold_value", "threshold_unit", "option_id", "field",
}
_EVIDENCE_FIELDS = {"basis", "windows", "evidence_ids", "price_source", "fx_source", "market_sources"}
_POLICY_FIELDS = {
    "initial_source", "target", "reserve_floor", "allowed_sources", "allow_smaller", "prefer_reserve",
    "loss_limit", "metric", "issuer_cap", "search_alternatives",
}
_FUNDING_FIELDS = {"maximum", "frontier", "solver_status", "no_feasible_confirmed", "requested_size_infeasible_confirmed"}
_WINDOWS = {window.id: window for window in (*STRESS_WINDOWS, EXTRA_WINDOW)}
_REQUEST_FIELDS = {"code", "label", "task_status", "verdict", "evidence_ids"}
_FINDING_FIELDS = {"metric_id", "status", "message", "actual", "limit", "covered_portfolio_weight", "evidence_ids"}


def _pick(row, fields):
    return {key: deepcopy(value) for key, value in row.items() if key in fields}


def _trace(rows):
    output = []
    for row in rows:
        event = _pick(row, _TRACE_FIELDS)
        if row.get("event") == "tool_routing":
            if row.get("status") in {"accepted", "deterministic_fallback"}:
                event["arguments"] = _pick(row.get("arguments", {}), {
                    "scope", "evidence_ids", "holdings_as_of", "metric", "window_ids",
                })
            if row.get("status") == "rejected":
                event["invalid_fields"] = [key for key in row.get("invalid_fields", ())
                                           if key in {"scope", "evidence_ids", "holdings_as_of", "metric", "window_ids"}]
        output.append(event)
    return output


def _explanation(report, verified):
    status = report["status"]
    if status == "needs_input":
        return "Confirm the missing inputs before releasing an audit."
    if status == "invalid":
        return "The publication check withheld the result after independent review could not verify the report."
    if status == "execution_error":
        return "The audit stopped before it reached a publishable independent review."
    if report.get("decision_reason") == "market_evidence_insufficient":
        return "A required historical price or FX window could not be verified."

    proposal = verified.get("proposal", {}).get("status")
    original = {
        "pass": "The original proposal meets the assessed rules.",
        "fail": "The original proposal breaches an assessed rule.",
        "insufficient_evidence": "The available evidence cannot settle every assessed rule for the proposal.",
    }.get(proposal, "The independently reviewed proposal is unavailable.")
    if report.get("unassessed_requirements") or report.get("assessment_scope") == "unavailable":
        return original + " The result covers only the requirements listed as assessed."
    frontier = verified.get("frontier", {})
    search_status = verified.get("solver_status") or frontier.get("status")
    funding = {
        "no_feasible": "The independent search found no eligible funding in the authorized range.",
        "requested_size_infeasible": "The confirmed purchase size has no eligible funding in the authorized range.",
        "feasible_full": "The search independently verified funding for the full purchase.",
        "feasible_partial": "An authorized smaller purchase has verified funding." if (frontier.get("max_total") or 0) > 1e-9
                            else "Only the starting portfolio fits the assessed rules.",
        "insufficient_evidence": "Missing issuer evidence leaves the alternative unresolved.",
    }.get(search_status)
    return f"{original} {funding}" if funding else original


def _scenarios(verified):
    # Window dates come from the application fixtures. All numeric values come from Review.
    result = {}
    for leg in ("baseline", "proposal", "maximum"):
        if leg not in verified:
            continue
        result[leg] = {
            "weights": deepcopy(verified[leg]["weights"]),
            "windows": {name: {**deepcopy(values), "start": _WINDOWS[name].start, "end": _WINDOWS[name].end}
                        for name, values in verified[leg]["windows"].items() if name in _WINDOWS},
        }
    return result


def publish_report(report):
    """Project a raw report for the UI and JSON download. Never publish model prose."""
    audit = report.get("audit", {})
    status = report.get("status")
    reason = report.get("decision_reason")
    search = report.get("search_alternatives", True) is True
    assessment = report.get("assessment_scope", "complete")
    unassessed = [_pick(row, {"code"}) for row in report.get("unassessed_requirements", ())]
    review_matches = status == audit.get("status") and reason == audit.get("decision_reason")
    found_invalid = any(row.get("status") == "invalid" for row in audit.get("findings", ()))
    reviewed = review_matches and not found_invalid and status in _AUDITED and all(
        audit.get("verified", {}).get(leg, {}).get("windows") and
        audit["verified"][leg].get("status") in _AUDITED
        for leg in ("baseline", "proposal")
    )
    if reviewed and status in {"pass", "fail"}:
        reviewed = audit["verified"]["proposal"]["status"] == status
    evidence_hold = (review_matches and status == "insufficient_evidence" and reason == "market_evidence_insufficient"
                     and not audit.get("verified"))
    out = _pick(report, {"case", "mode", "elapsed_ms", "runtime_usage", "confirmed_scope", "confirmed_to_reviewed_ms"})
    out["trace"] = _trace(report.get("trace", ()))
    out["search_alternatives"] = search
    out["assessment_scope"] = assessment if reviewed else "unavailable"
    if "requirements" in report:
        out["requirements"] = [_pick(row, _REQUEST_FIELDS) for row in report["requirements"]]
    if unassessed:
        out["unassessed_requirements"] = unassessed
    if "policy" in report:
        fields = _POLICY_FIELDS if search else _POLICY_FIELDS - {"allowed_sources", "allow_smaller", "prefer_reserve"}
        out["policy"] = _pick(report["policy"], fields)

    if reviewed or evidence_hold:
        out.update(status=status, decision_reason=reason)
    else:
        out.update(status=status if status in {"needs_input", "execution_error", "invalid"} else "invalid",
                   decision_reason=reason if status in {"needs_input", "execution_error", "invalid"} else "publication_failed")

    limited = evidence_hold or status == "insufficient_evidence" or reason == "issuer_evidence_insufficient" or (
        assessment != "complete" or bool(unassessed)
    )
    out["publication"] = {
        "status": "limited" if (reviewed or evidence_hold) and limited else "released" if reviewed else "blocked",
        "reason": out["decision_reason"],
        "independent_review_verified": bool(reviewed),
    }
    evidence = report.get("evidence", {})
    out["evidence"] = _pick(evidence, _EVIDENCE_FIELDS if not reviewed else _EVIDENCE_FIELDS | {"issuer_snapshot", "issuer_weights"})
    can_show_funding = reviewed and search and not unassessed and assessment != "unavailable"
    verified_fields = {"baseline", "proposal"} | (_FUNDING_FIELDS if can_show_funding else set())
    verified = _pick(audit.get("verified", {}), verified_fields) if reviewed else {}
    if frontier := verified.get("frontier"):
        if frontier.get("status") == "insufficient_evidence":
            verified["frontier"] = {"status": "insufficient_evidence"}
        if out.get("policy", {}).get("allow_smaller") is not True:
            verified["frontier"].pop("diagnostic_max_total", None)
            if (verified.get("maximum", {}).get("total", 0)
                    < out["policy"].get("target", 0) - 1e-9):
                verified.pop("maximum", None)
    if reviewed:
        out["scenarios"] = _scenarios(verified)
        out.update(_pick(report, {"sector_analysis", "exposure_change"}))
        if can_show_funding and report.get("needs_smaller_authorization") is True:
            out["needs_smaller_authorization"] = True
        if can_show_funding and reason == "issuer_evidence_insufficient":
            example = _issuer_thresholds(report).get("qqq_only")
            if example is not None:
                out["exposure"] = {"qqq_only": {"lower": example["known_lower"], "upper": example["potential_upper"]}}

    findings = audit.get("findings", ())
    if not can_show_funding:
        findings = [row for row in findings if not row["metric_id"].startswith(("frontier.", "maximum."))]
    fields = _FINDING_FIELDS if reviewed else {"metric_id", "status"}
    out["audit"] = {"status": out["status"], "decision_reason": out["decision_reason"], "verified": verified,
                    "findings": [_pick(row, fields) for row in findings]}
    out["explanation"] = _explanation(out, verified)
    return out


def publish_check(check):
    """Apply the same boundary to a challenge and its audited replays."""
    out = _pick(check, {"status", "reason", "verified", "statement", "selection_mode", "option",
                        "confirmed_threshold", "elapsed_ms", "changed_fields", "runtime_usage"})
    out["trace"] = _trace(check.get("trace", ()))
    out["baseline"] = publish_report(check["baseline"]) if check.get("baseline") else None
    out["replay"] = publish_report(check["replay"]) if check.get("replay") and check.get("verified") is True else None
    baseline = out["baseline"] or {}
    audit_only = not baseline.get("search_alternatives", True)
    hide_funding = audit_only or bool(baseline.get("unassessed_requirements"))
    hidden = {"diagnostic_max_total"}
    if hide_funding:
        hidden |= {"solver_status", "alternative_eligible", "eligible_max_total", "full_zst_min", "full_zst_max",
                   "full_zst_max_binding"}
    out["action"] = None
    if check.get("verified") is True and baseline.get("publication", {}).get("independent_review_verified"):
        if action := check.get("action"):
            out["action"] = _pick(action, {"type", "holdings", "required_fields", "reference_date", "thresholds",
                                           "reviewed_disclosures", "remaining_holding_gaps"})
            if hide_funding:
                out["action"].get("thresholds", {}).pop("qqq_only", None)
    out["comparison"] = {"baseline": None, "replay": None, "differences": {}, "material_differences": []}
    for leg in ("baseline", "replay"):
        if (report := out[leg]) and report["publication"]["independent_review_verified"]:
            summary = _summary(report)
            out["comparison"][leg] = _pick(summary, summary.keys() - hidden)
    if out["comparison"]["baseline"] and out["comparison"]["replay"]:
        out["comparison"] = _comparison(out["comparison"]["baseline"], out["comparison"]["replay"])
    return out
