"""Use bounded Bedrock clause selection to assist grounded comparison intake."""

import re
from collections.abc import Iterable

from .agents import StrandsAgents, ToolSpec
from .assistant_request import parse_comparison_request
from .runtime_budget import PROFILE_LIMITS, PROFILE_MAX_REQUEST_BYTES, RuntimeBudgetExceeded, run_bounded


_CLAUSE_SEPARATOR = re.compile(r"\n+|[;。；!?！？]+|\.(?=\s|$)")
_TRACE_FIELDS = {
    "event", "role", "status", "tool_name", "model_id", "region", "operation", "request_id",
    "http_status", "retry_attempts", "duration_ms", "throttled", "input_tokens", "output_tokens", "total_tokens",
}


def _record(result, *, trace=(), usage=None, review_required=False, method="local"):
    return {
        **result,
        "trace": [
            {key: value for key, value in event.items()
             if key in _TRACE_FIELDS and type(value) in (str, bool, int, float, type(None))}
            for event in trace
        ],
        "usage": usage or {},
        "scope_review_required": review_required,
        "interpretation": method,
    }


async def interpret_comparison_request(
    text: str, assets: Iterable[str], runtime: StrandsAgents | None,
) -> dict:
    """Interpret whole requests locally and ask Bedrock to locate uncertain clauses.

    Only deterministic parsing can assign values. Selecting excerpts does not
    establish that all the user's conditions have been represented.
    """
    if (not isinstance(text, str) or not text.strip() or len(text) > PROFILE_MAX_REQUEST_BYTES
            or len(text.encode("utf-8")) > PROFILE_MAX_REQUEST_BYTES):
        return _record({"status": "unrecognized", "fields": {}, "sources": {},
                        "message": "Enter a short historical comparison request."})
    symbols = tuple(assets)
    local = parse_comparison_request(text, symbols)
    if runtime is None or local["status"] in {"ready", "unsupported"}:
        return _record(local)

    clauses = tuple(dict.fromkeys(clause.strip() for clause in _CLAUSE_SEPARATOR.split(text) if clause.strip()))
    if not clauses:
        return _record(local)

    selection = None
    rejected = False

    def locate_comparison_clauses(
        options_clause: str = "", objective_clause: str = "", withdrawal_clause: str = "",
        risk_clause: str = "", priority_clause: str = "", drawdown_clause: str = "",
        window_clause: str = "", esg_clause: str = "", issue_clause: str = "",
    ) -> dict:
        """Select exact complete user clauses. Empty strings leave fields unresolved."""
        nonlocal selection, rejected
        requests = (
            (options_clause, ("first_asset", "second_asset", "options")),
            (objective_clause, ("objective",)), (withdrawal_clause, ("withdrawal_time",)),
            (risk_clause, ("risk_tolerance",)), (priority_clause, ("priority",)),
            (drawdown_clause, ("max_drawdown",)), (window_clause, ("include_2023",)),
            (esg_clause, ("require_esg",)),
        )
        if selection is not None or any(
            type(clause) is not str or (clause and clause not in clauses)
            for clause in (issue_clause, *(clause for clause, _ in requests))
        ):
            rejected = True
            raise ValueError("Select each field from the supplied complete clauses.")

        fields, sources = dict(local["fields"]), dict(local["sources"])
        for clause, allowed in requests:
            if not clause or issue_clause:
                continue
            parsed = parse_comparison_request(clause, symbols, extract_only=True)
            if parsed["status"] == "unsupported":
                issue_clause = clause
                continue
            for key in allowed:
                if key not in parsed["fields"]:
                    continue
                excerpt = parsed["sources"].get(key)
                if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in clause:
                    continue
                value = parsed["fields"][key]
                if key in fields and fields[key] != value:
                    rejected = True
                    raise ValueError("The selected clause conflicts with the original request.")
                fields[key], sources[key] = value, excerpt

        if issue_clause:
            selection = {**local, "status": "unsupported", "sources": {**local["sources"], "issue": issue_clause},
                         "message": "This condition needs clarification before the assistant can compare the choices."}
        elif fields != local["fields"]:
            message = local["message"] if local["status"] == "clarify" else (
                "Review the conditions extracted from your wording and confirm the full comparison scope."
            )
            selection = {"status": "clarify", "fields": fields, "sources": sources, "message": message}
        else:
            selection = local
        return {"status": "ok"}

    tool = ToolSpec("locate_comparison_clauses", locate_comparison_clauses.__doc__, locate_comparison_clauses,
                    trace_fields=(), completes_handoff=True)
    try:
        run, usage = await run_bounded(runtime.run(
            "comparison_request", {"user_request": text, "candidate_clauses": clauses, "required_tool": tool.name},
            tools=(tool,), stop_after_tool=tool.name,
        ), PROFILE_LIMITS)
    except RuntimeBudgetExceeded as exc:
        return _record(local, usage=exc.usage)

    if run.status != "ok" or rejected or selection is None or selection is local:
        return _record(local, trace=run.trace, usage=usage)
    proposed_fields = selection["fields"]
    has_options = "options" in proposed_fields or {"first_asset", "second_asset"} <= proposed_fields.keys()
    review_required = selection["status"] == "clarify" and local["status"] == "unrecognized" and has_options
    if review_required:
        full_scope = parse_comparison_request(text, symbols, extract_only=True)
        if full_scope["status"] in {"unsupported", "clarify"}:
            return _record(full_scope, trace=run.trace, usage=usage)
        selection = {
            **selection,
            "fields": {**selection["fields"], **full_scope["fields"]},
            "sources": {**selection["sources"], **full_scope["sources"]},
        }
    return _record(selection, trace=run.trace, usage=usage,
                   review_required=review_required, method="bedrock")
