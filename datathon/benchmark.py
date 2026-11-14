"""Compare AlphaForge decision workflows on frozen competition fixtures."""

import argparse
import asyncio
import hashlib
import json
import math
import statistics
from pathlib import Path
from time import perf_counter

from .agents import DEFAULT_MODEL, DEFAULT_REGION, StrandsAgents
from .benchmark_cases import NATURAL_LANGUAGE_CASES, STRUCTURED_CASES
from .benchmark_single import SingleAgentRuntime
from .data import DATA_CSVS, _csv_texts, load_market_data
from .workflow import interpret_request, profile_policy, run_case


def fingerprint(data_path):
    files = _csv_texts(Path(data_path))
    return {name: hashlib.sha256(files[name].encode("utf-8")).hexdigest() for name in DATA_CSVS}


def usage(trace):
    received = [event for event in trace
                if event.get("event") == "bedrock" and event.get("status") == "success"]
    counted = [event for event in received if "input_tokens" in event and "output_tokens" in event]
    return {
        "converse": len(received),
        "failed_converse": sum(event.get("event") == "bedrock" and event.get("status") == "error" for event in trace),
        "token_responses": len(counted),
        "input_tokens": sum(event["input_tokens"] for event in counted) if len(counted) == len(received) else None,
        "output_tokens": sum(event["output_tokens"] for event in counted) if len(counted) == len(received) else None,
        "routing_fallbacks": sum(event.get("status") == "deterministic_fallback" for event in trace),
        "agent_sessions": sum(event.get("event") == "agent_start" for event in trace),
    }


def release_flags(status, verified):
    if status not in {"pass", "fail"}:
        return [False, False]
    return [status == "pass", verified.get("solver_status") in {"feasible_full", "feasible_partial"}
            and (verified.get("frontier", {}).get("max_total") or 0) > 1e-9]


def score_decision(case, report, reference):
    verified = report.get("audit", {}).get("verified", {})
    frontier = verified.get("frontier", {})
    required = {
        name: number for name, number in (
            ("max_total", case.expected_frontier_max),
            ("diagnostic_max_total", case.expected_diagnostic_max),
            ("full_zst_max", case.expected_max_zst),
        ) if number is not None
    }
    expected = [case.expected_status == "pass",
                case.expected_status in {"pass", "fail"} and case.expected_solver_status in {"feasible_full", "feasible_partial"}]
    actual = release_flags(report["status"], verified)
    trace = report.get("trace", [])
    needed_sources = {"starter:prices_daily.csv", "starter:fx_usdcad_daily.csv"}
    source_ids = report.get("evidence", {}).get("evidence_ids", ())
    needed_windows = {"2022", "2025"}
    audit_present = bool(verified.get("proposal")) and bool(report.get("audit", {}).get("findings"))
    if report.get("mode") == "aws":
        review_provenance = any(row.get("event") == "tool" and row.get("tool_name") == "recheck_decision"
                                and row.get("status") == "success" for row in trace)
    else:
        review_provenance = audit_present
    return {
        "status": report["status"],
        "reason": report.get("decision_reason"),
        "solver_status": report.get("alternatives", {}).get("status"),
        "status_match": report["status"] == case.expected_status,
        "reason_match": report.get("decision_reason") == case.expected_reason,
        "solver_match": report.get("alternatives", {}).get("status") == case.expected_solver_status,
        "baseline_match": verified.get("baseline", {}).get("status") == case.expected_baseline,
        "false_releases": sum(observed and not gold for observed, gold in zip(actual, expected)),
        "unnecessary_holds": sum(gold and not observed for observed, gold in zip(actual, expected)),
        "possible_false_releases": expected.count(False),
        "possible_unnecessary_holds": expected.count(True),
        "independent_audit_match": bool(reference) and report.get("audit") == reference,
        "gold_boundaries_match": all(isinstance(frontier.get(name), (int, float))
                                     and math.isclose(frontier[name], number, rel_tol=0, abs_tol=1e-8)
                                     for name, number in required.items()),
        "trace_complete": audit_present and needed_sources.issubset(source_ids)
                          and set(verified["proposal"]["windows"]) == needed_windows and review_provenance,
        "tool_errors": [row["tool_name"] for row in trace if row.get("event") == "tool" and row.get("status") == "error"],
        "error": report.get("error"),
        **usage(trace),
    }


async def evaluate_decision(data, case, arm, model, region, reference=None, *, optimized_single=False):
    multiple = StrandsAgents(model_id=model, region=region) if arm == "multi" else None
    single = SingleAgentRuntime(model_id=model, region=region, stop_after_review=optimized_single) if arm == "single" else None
    started = perf_counter()
    report = await run_case(data, case.workflow_case(), multiple, single_runtime=single,
                            confirmed_profile=case.confirmed_profile(), evidence_date=case.evidence_date,
                            holdings_max_age_days=case.holdings_max_age_days)
    elapsed = round((perf_counter() - started) * 1000, 2)
    return score_decision(case, report, report.get("audit") if arm == "deterministic" else reference) | {
        "elapsed_ms": elapsed, "confirmed_to_reviewed_ms": report.get("confirmed_to_reviewed_ms"),
    }, report.get("audit")


async def evaluate_intake(case, model, region, run_id):
    started = perf_counter()
    draft, policy, question = await interpret_request(case.request, StrandsAgents(model_id=model, region=region), run_id)
    elapsed = round((perf_counter() - started) * 1000, 2)
    field = draft.data.get("clarification_field")
    if question and field is None and "excluded from the permitted funding sources" in question:
        field = "conflict"
    expected = profile_policy(case.expected_policy.as_profile()) if case.expected_policy else None
    return {
        "status": draft.status,
        "classification": "clarify" if question and draft.status != "error" else "accepted" if policy else "error",
        "question_field": field,
        "correct": (policy is None and draft.status != "error" and field == case.clarification_field)
                   if expected is None else bool(policy == expected),
        "premature_policy": expected is None and policy is not None,
        "unnecessary_clarification": expected is not None and bool(question) and draft.status != "error",
        "policy": policy, "question": question,
        "elapsed_ms": elapsed,
        **usage(draft.trace),
    }


def summarize(rows, arms):
    summaries = {}
    for arm in arms:
        observations = [row for row in rows if row["arm"] == arm]
        if not observations:
            continue
        summary = {"runs": len(observations), "median_ms": statistics.median(x["elapsed_ms"] for x in observations),
                   "min_ms": min(x["elapsed_ms"] for x in observations), "max_ms": max(x["elapsed_ms"] for x in observations)}
        reviewed = [row["confirmed_to_reviewed_ms"] for row in observations if row.get("confirmed_to_reviewed_ms") is not None]
        if "confirmed_to_reviewed_ms" in observations[0]:
            summary["reviewed_runs"] = len(reviewed)
            summary["median_confirmed_to_reviewed_ms"] = statistics.median(reviewed) if reviewed else None
        for key in ("status_match", "reason_match", "solver_match", "baseline_match", "false_releases",
                    "unnecessary_holds", "possible_false_releases", "possible_unnecessary_holds",
                    "independent_audit_match", "gold_boundaries_match", "trace_complete", "correct",
                    "premature_policy", "unnecessary_clarification", "converse", "failed_converse",
                    "token_responses", "input_tokens", "output_tokens", "routing_fallbacks", "agent_sessions"):
            if key in observations[0]:
                values = [row[key] for row in observations]
                summary[key] = sum(values) if None not in values else None
        summaries[arm] = summary
    return summaries


async def run_benchmark(args):
    data = load_market_data(args.data)
    live = args.mode == "aws"
    optimized_single = getattr(args, "optimized_single", False)
    rows = []
    references = {}
    for case in STRUCTURED_CASES:
        for trial in range(args.repeats):
            row, audit = await evaluate_decision(data, case, "deterministic", args.model, args.region)
            rows.append({"arm": "deterministic", "case": case.id, "trial": trial + 1, **row})
            if not (row["status_match"] and row["reason_match"] and row["solver_match"]
                    and row["baseline_match"] and row["gold_boundaries_match"]):
                raise ValueError(f"Structured reference disagrees with preregistered expectations: {case.id}: {row}")
            references[case.id] = audit

    async def paired(case, trial, first):
        observed = []
        for position, arm in enumerate(("single", "multi") if first else ("multi", "single"), start=1):
            row, _ = await evaluate_decision(data, case, arm, args.model, args.region, references[case.id],
                                             optimized_single=optimized_single)
            observed.append({"arm": arm, "case": case.id, "trial": trial + 1, "pair_position": position, **row})
        return observed

    async def intake(case, trial):
        row = await evaluate_intake(case, args.model, args.region, f"intake-{case.id}-{trial + 1}")
        return [{"arm": "shared_profile_intake", "case": case.id, "trial": trial + 1, **row}]

    if live:
        # Sequential within each matched pair, with the first arm counterbalanced.
        combinations = [(case, trial, (index + trial) % 2 == 0)
                        for trial in range(args.repeats) for index, case in enumerate(STRUCTURED_CASES)]
        for offset in range(0, len(combinations), args.jobs):
            batch = combinations[offset:offset + args.jobs]
            for observed in await asyncio.gather(*(paired(*entry) for entry in batch)):
                rows.extend(observed)
                for row in observed:
                    print(row["arm"], row["case"], row["trial"], row["status"], row["elapsed_ms"],
                          row["error"] or "", flush=True)
        language_inputs = [(case, trial) for trial in range(args.repeats) for case in NATURAL_LANGUAGE_CASES]
        for offset in range(0, len(language_inputs), args.jobs):
            for observed in await asyncio.gather(*(intake(*entry) for entry in language_inputs[offset:offset + args.jobs])):
                rows.extend(observed)
    return {
        "mode": args.mode, "model": args.model if live else None, "region": args.region if live else None,
        "code_ref": args.code_ref, "repeats": args.repeats, "live_parallel_pairs": args.jobs if live else 0,
        "configuration": {
            "multi": {"per_role_timeout_seconds": 35, "per_role_turns": 5, "per_role_token_budget": 9000},
            "single": {"timeout_seconds": 95, "turns": 16, "token_budget": 54000,
                       "stop_after_checked_review": optimized_single},
            "both": {"max_output_tokens_per_response": 700, "session_state": "fresh per run"},
            "intake": "Shared production Profile parser; no financial result is released in this cohort.",
        },
        "input_text_sha256": fingerprint(args.data),
        "structured_cases": [case.id for case in STRUCTURED_CASES],
        "natural_language_cases": [case.id for case in NATURAL_LANGUAGE_CASES] if live else [],
        "summary": summarize(rows, ("deterministic", "single", "multi", "shared_profile_intake")),
        "runs": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--mode", choices=("offline", "aws"), default="offline")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--code-ref", default=None, help="Commit whose code is being measured.")
    parser.add_argument("--optimized-single", action="store_true", help="Stop the bundled arm after checked review.")
    args = parser.parse_args()
    if args.repeats < 1 or args.jobs < 1:
        parser.error("--repeats and --jobs must be positive.")
    report = asyncio.run(run_benchmark(args))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
