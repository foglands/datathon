"""Compare staged and bundled audit recovery on matched official-data inputs."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

from .agents import DEFAULT_MODEL, DEFAULT_REGION, StrandsAgents
from .benchmark import fingerprint, release_flags, usage
from .benchmark_cases import BenchmarkCase, STRUCTURED_CASES
from .benchmark_single import SingleAgentRuntime
from .challenge_benchmark import OFFICIAL_STARTER_SHA256, latency
from .data import load_market_data
from .finance import STRESS_WINDOWS
from .workflow import run_case


ARMS = ("staged", "bundled")
FIXTURES = {case.id: case for case in STRUCTURED_CASES}
ROBERT = FIXTURES["zst_to_nvda_terminal"]


@dataclass(frozen=True)
class ResilienceCase:
    id: str
    fixture: BenchmarkCase = ROBERT
    scripted_fault: str | None = None
    expected_holds: tuple[str, ...] = ()
    drop_fx_endpoint: bool = False


SCENARIOS = (
    ResilienceCase("clean"),
    ResilienceCase("missing_issuer_disclosure", FIXTURES["issuer_qqq_missing"]),
    ResilienceCase("missing_market_endpoint", drop_fx_endpoint=True),
    ResilienceCase("corrupted_candidate", FIXTURES["tampered_replay"]),
    ResilienceCase("persistent_invalid_route", scripted_fault="persistent_invalid_route", expected_holds=("bundled",)),
    ResilienceCase("corrected_invalid_route", scripted_fault="corrected_invalid_route"),
    ResilienceCase("absent_review_callback", scripted_fault="absent_review_callback", expected_holds=ARMS),
    ResilienceCase("interrupted_after_evidence", scripted_fault="interrupted_after_evidence", expected_holds=("bundled",)),
    ResilienceCase("interrupted_after_review", scripted_fault="interrupted_after_review"),
)


def _tool_arguments(name, inputs):
    if name == "lookup_evidence":
        evidence = inputs.get("evidence", inputs)
        catalog = evidence["catalog"]
        include_issuer = evidence["policy"]["issuer_cap"] is not None
        return {
            "scope": "market_and_issuer" if include_issuer else "market_replay",
            "evidence_ids": catalog["market_evidence_ids"] + (catalog["issuer_evidence_ids"] if include_issuer else []),
            "holdings_as_of": catalog["holdings_as_of"] if include_issuer else "",
        }
    if name == "stress_replay":
        scenario = inputs.get("scenario", inputs)
        policy = scenario["policy"]
        return {"metric": policy["metric"] if policy["loss_limit"] is not None else "comparison",
                "window_ids": scenario["required_windows"]}
    return {}


def _scripted_invoker(fault):
    """Supply the same scripted tool actions to both production orchestration paths."""

    async def invoke(role, prompt, tools, record):
        inputs = json.loads(prompt.split("\n", 1)[1])
        for tool in tools:
            arguments = _tool_arguments(tool.name, inputs)
            if tool.name == "lookup_evidence" and fault in ("persistent_invalid_route", "corrected_invalid_route"):
                invalid = {**arguments, "evidence_ids": ["fixture:unauthorized_source"]}
                record("injected_fault", fault=fault, tool_name=tool.name)
                if _call_scripted_tool(tool, invalid, record):
                    raise AssertionError("The evidence tool accepted an unauthorized source.")
                if fault == "persistent_invalid_route":
                    return {}, "limit_turns"
            if tool.name == "recheck_decision" and fault == "absent_review_callback":
                # The independent operation is deliberately omitted, despite the success claim.
                record("injected_fault", fault=fault, tool_name=tool.name)
                record("tool", tool_name=tool.name, status="success")
                continue
            if not _call_scripted_tool(tool, arguments, record):
                return {}, "tool_failure"
            if ((tool.name == "lookup_evidence" and fault == "interrupted_after_evidence")
                    or (tool.name == "recheck_decision" and fault == "interrupted_after_review")):
                record("injected_fault", fault=fault, tool_name=tool.name)
                return {}, "limit_turns"
        return {"status": "ok", "summary": "Scripted handoff", "evidence_ids": []}, "end_turn"

    return invoke


def _call_scripted_tool(tool, arguments, record):
    record("scripted_tool_attempt", tool_name=tool.name)
    try:
        tool.handler(**arguments)
    except (TypeError, ValueError):
        record("tool", tool_name=tool.name, status="error", input=arguments)
        return False
    record("tool", tool_name=tool.name, status="success", input=arguments)
    return True


def _market_input(data, scenario):
    if not scenario.drop_fx_endpoint:
        return data
    endpoint = STRESS_WINDOWS[-1].end
    if endpoint not in data.fx:
        raise ValueError(f"Missing-FX fixture endpoint is already absent: {endpoint}.")
    return replace(data, fx={day: rate for day, rate in data.fx.items() if day != endpoint})


def _audit_arguments(scenario):
    fixture = scenario.fixture
    return {"confirmed_profile": fixture.confirmed_profile(), "evidence_date": fixture.evidence_date,
            "holdings_max_age_days": fixture.holdings_max_age_days}


def _validate_reference(scenario, report):
    expected = ("insufficient_evidence", "market_evidence_insufficient") if scenario.drop_fx_endpoint else (
        scenario.fixture.expected_status, scenario.fixture.expected_reason)
    observed = (report["status"], report.get("decision_reason"))
    if expected != observed:
        raise ValueError(f"Official-data control disagrees with the registered outcome for {scenario.id}: {observed}.")


def _score(scenario, arm, reference, report, elapsed_ms, *, scripted):
    should_hold = arm in scenario.expected_holds
    expected_status = "execution_error" if should_hold else reference["status"]
    expected_reason = None if should_hold else reference.get("decision_reason")
    audit = report.get("audit", {})
    verified = audit.get("verified", {})
    reference_audit = reference.get("audit", {})
    actual_flags = release_flags(report["status"], verified)
    authorized_flags = [False, False] if should_hold else release_flags(reference["status"], reference_audit.get("verified", {}))
    audit_matches = audit == reference_audit and bool(audit)
    outcome_matches = (report["status"] == expected_status and report.get("decision_reason") == expected_reason
                       and (not audit if should_hold else audit_matches))
    trace = report["trace"]
    fault_observed = any(event.get("event") == "injected_fault" for event in trace)
    outcome_matches = outcome_matches and (scenario.scripted_fault is None or fault_observed)
    unsafe_release = any(actual_flags) and (
        not audit_matches or any(actual and not allowed for actual, allowed in zip(actual_flags, authorized_flags))
    )
    metrics = usage(trace)
    if scripted:
        metrics.update(input_tokens=None, output_tokens=None)
    return {
        "scenario": scenario.id,
        "arm": arm,
        "status": report["status"],
        "reason": report.get("decision_reason"),
        "expected_status": expected_status,
        "expected_reason": expected_reason,
        "checked_outcome": outcome_matches,
        "audit_matches_control": audit_matches,
        "completed_independent_review": bool(verified.get("proposal") and audit.get("findings")),
        "verified_recovery": bool(scenario.scripted_fault and not should_hold and outcome_matches),
        "unsafe_release": unsafe_release,
        "eligible_proposal": actual_flags[0],
        "eligible_alternative": actual_flags[1],
        "held_eligible_control": any(release_flags(reference["status"], reference_audit.get("verified", {})))
                                 and not any(actual_flags),
        "unexpected_hold": not should_hold and any(authorized_flags) and actual_flags != authorized_flags,
        "injected_fault_observed": fault_observed,
        "validated_tool_rejections": sum(event.get("event") == "tool_routing" and event["status"] == "rejected"
                                         for event in trace),
        "retained_handoffs": sum(event.get("status") == "checked_tool_result_retained" for event in trace),
        "scripted_tool_attempts": sum(event.get("event") == "scripted_tool_attempt" for event in trace) if scripted else None,
        "elapsed_ms": elapsed_ms,
        "confirmed_to_reviewed_ms": report.get("confirmed_to_reviewed_ms"),
        **metrics,
    }


async def _evaluate(data, scenario, arm, reference, args):
    scripted = args.mode == "scripted"
    invoker = _scripted_invoker(scenario.scripted_fault) if scripted else None
    model = {"model_id": args.model, "region": args.region, "invoker": invoker}
    staged = StrandsAgents(**model) if arm == "staged" else None
    bundled = SingleAgentRuntime(**model, stop_after_review=True) if arm == "bundled" else None
    started = perf_counter()
    report = await run_case(data, scenario.fixture.workflow_case(), staged, single_runtime=bundled,
                            **_audit_arguments(scenario))
    elapsed = round((perf_counter() - started) * 1000, 3)
    return _score(scenario, arm, reference, report, elapsed, scripted=scripted)


def _summarize(rows):
    fields = ("checked_outcome", "completed_independent_review", "verified_recovery", "unsafe_release",
              "held_eligible_control", "unexpected_hold", "validated_tool_rejections", "routing_fallbacks",
              "retained_handoffs",
              "agent_sessions", "scripted_tool_attempts", "converse", "failed_converse", "token_responses",
              "input_tokens", "output_tokens")
    summary = {}
    for arm in ARMS:
        observations = [row for row in rows if row["arm"] == arm]
        reviewed = [row for row in observations if row["confirmed_to_reviewed_ms"] is not None]
        summary[arm] = {
            "runs": len(observations),
            **{field: sum(row[field] for row in observations) if all(row[field] is not None for row in observations)
               else None for field in fields},
            "elapsed_ms": latency(observations, "elapsed_ms"),
            "confirmed_to_reviewed_ms": latency(reviewed, "confirmed_to_reviewed_ms") if reviewed else None,
        }
    return summary


async def run_benchmark(args):
    if args.repeats < 1 or args.jobs < 1:
        raise ValueError("Repeats and concurrent pairs must be positive.")
    scenarios = [case for case in SCENARIOS if not args.scenario or case.id in args.scenario]
    if not scenarios or args.scenario and set(args.scenario) != {case.id for case in scenarios}:
        raise ValueError("Select one or more known resilience scenarios.")
    if args.mode == "aws":
        if args.scenario and any(case.scripted_fault for case in scenarios):
            raise ValueError("Injected model actions only run in scripted mode.")
        scenarios = [case for case in scenarios if case.scripted_fault is None]

    hashes = fingerprint(args.data)
    if hashes != OFFICIAL_STARTER_SHA256:
        raise ValueError("Use the frozen organizer starter data for this matched comparison.")
    data = load_market_data(args.data)
    references = {}
    inputs = {}
    for scenario in scenarios:
        key = (scenario.fixture.id, scenario.drop_fx_endpoint)
        if key not in references:
            inputs[key] = _market_input(data, scenario)
            reference = await run_case(inputs[key], scenario.fixture.workflow_case(), **_audit_arguments(scenario))
            _validate_reference(scenario, reference)
            references[key] = reference

    async def pair(scenario, trial, reverse):
        key = (scenario.fixture.id, scenario.drop_fx_endpoint)
        arms = ARMS[::-1] if reverse else ARMS
        rows = []
        for position, arm in enumerate(arms, start=1):
            row = await _evaluate(inputs[key], scenario, arm, references[key], args)
            rows.append({"trial": trial, "pair_position": position, **row})
        return rows

    pairs = [(case, trial, (index + trial - 1) % 2 == 1)
             for trial in range(1, args.repeats + 1) for index, case in enumerate(scenarios)]
    rows = []
    for start in range(0, len(pairs), args.jobs):
        batch = pairs[start:start + args.jobs]
        for result in await asyncio.gather(*(pair(*entry) for entry in batch)):
            rows.extend(result)
    return {
        "mode": args.mode,
        "code_ref": args.code_ref,
        "model": args.model if args.mode == "aws" else None,
        "region": args.region if args.mode == "aws" else None,
        "method": ("Scripted model tool actions. No Bedrock calls; local timings exclude model/network latency."
                   if args.mode == "scripted" else "Live Amazon Bedrock. Data-side faults only; no simulated model responses."),
        "scope": "Both arms share policy, market and issuer inputs, numerical tools and independent review."
                 " Each uses its existing workflow session layout and recovery policy.",
        "repeats": args.repeats,
        "concurrent_pairs": args.jobs,
        "reference_runs": len(references),
        "input_text_sha256": hashes,
        "summary": _summarize(rows),
        "runs": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=("scripted", "aws"), default="scripted")
    parser.add_argument("--scenario", choices=[case.id for case in SCENARIOS], action="append")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--code-ref", help="Commit whose code is being measured.")
    args = parser.parse_args()
    try:
        report = asyncio.run(run_benchmark(args))
    except ValueError as exc:
        parser.error(str(exc))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    raise SystemExit(any(not row["checked_outcome"] or row["unsafe_release"] for row in report["runs"]))


if __name__ == "__main__":
    main()
