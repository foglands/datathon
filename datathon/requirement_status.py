"""Cross-reference checked portfolio results and any unassessed binding terms."""

from collections.abc import Mapping


UNASSESSED_LABELS = {
    "esg": "Environmental or social screening",
    "liquidity": "Liquidity or withdrawal requirement",
    "sector": "Sector exposure limit",
    "direct_issuer_cap": "Direct-only issuer limit",
    "return_floor": "Minimum return requirement",
    "other_binding": "Additional binding requirement",
}


def unassessed_codes(records):
    """Keep vetted labels while dropping verbatim user input from published records."""
    if not isinstance(records, (list, tuple)):
        return ()
    codes = []
    for item in records:
        code = item.get("code") if isinstance(item, Mapping) else None
        codes.append(code if isinstance(code, str) and code in UNASSESSED_LABELS else "other_binding")
    return tuple(dict.fromkeys(codes))


def apply_requirement_status(report, unassessed=()):
    """Report task completion separately from each checked rule and verdict."""
    audit = report.get("audit", {})
    verified = audit.get("verified", {})
    failed_execution = report.get("status") in {"execution_error", "invalid"}
    proposal = {} if failed_execution else verified.get("proposal", {})
    policy = report.get("policy", {})
    evidence = report.get("evidence", {})
    facts = {row["metric_id"]: row["status"] for row in audit.get("findings", ())
             if "metric_id" in row and "status" in row}
    market_ids = [evidence[key] for key in ("price_source", "fx_source") if evidence.get(key)]
    issuer_ids = [ref for ref in evidence.get("evidence_ids", ()) if ref.startswith("issuer:")]
    entries = []

    def add(code, label, task_status, verdict=None, evidence_ids=()):
        entries.append({"code": code, "label": label, "task_status": task_status,
                        "verdict": verdict, "evidence_ids": list(evidence_ids)})

    def rule(code, label, metric, evidence_ids=()):
        status = facts.get(f"proposal.{metric}.policy") if not failed_execution else None
        if status in {"pass", "fail"}:
            add(code, label, "completed", status, evidence_ids)
        elif failed_execution:
            add(code, label, "review_unavailable", evidence_ids=evidence_ids)
        else:
            add(code, label, "insufficient_evidence", "unknown", evidence_ids)

    if policy:
        add("historical_replay", "Historical price and FX replay",
            "completed" if proposal.get("windows") else
            "review_unavailable" if failed_execution else "insufficient_evidence",
            evidence_ids=market_ids)
        if policy.get("loss_limit") is not None:
            metric = policy["metric"]
            rule("loss_limit", "Maximum drawdown limit" if metric == "max_drawdown" else
                 "Terminal loss limit", metric, market_ids)
        if policy.get("reserve_floor"):
            rule("reserve_floor", "Minimum reserve weight", "reserve_weight")
        if policy.get("issuer_cap") is not None:
            rule("issuer_cap", "Total issuer exposure limit", "issuer_weight", issuer_ids)
    if report.get("search_alternatives"):
        frontier = verified.get("frontier", {})
        add("alternatives", "Authorized funding search",
            "review_unavailable" if failed_execution else
            "insufficient_evidence" if not frontier or frontier.get("status") == "insufficient_evidence" else
            "needs_authorization" if report.get("needs_smaller_authorization") else "completed",
            evidence_ids=market_ids + issuer_ids)
    else:
        add("alternatives", "Alternative funding search",
            "skipped_outside_scope" if unassessed else "skipped_not_requested")
    if sector := report.get("sector_analysis"):
        add("sector_analysis", "Descriptive equity sector analysis",
            "completed" if sector.get("status") == "complete" else "insufficient_evidence",
            evidence_ids=[f"sector:{ticker}:{row['as_of']}" for ticker, row in sector.get("evidence", {}).items()])
    for code in unassessed:
        add(code, UNASSESSED_LABELS[code], "unsupported", "unknown")

    assessment_scope = (
        "unavailable" if not proposal else
        "limited" if any(row["task_status"] in {"unsupported", "insufficient_evidence", "needs_authorization"}
                         for row in entries) else
        "complete"
    )
    report.update(requirements=entries, assessment_scope=assessment_scope)
    if unassessed:
        report["unassessed_requirements"] = [{"code": code} for code in unassessed]
