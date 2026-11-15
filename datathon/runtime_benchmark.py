"""Measure controller latency and compute under bounded audit workloads."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from math import ceil
from statistics import median
from time import perf_counter

from .__main__ import validate_case, write_report
from .agents import AgentRun
from .data import load_market_data
from .model_settings import configured_bedrock_runtime
from .runtime_budget import PROFILE_LIMITS, RuntimeBudgetExceeded, bound_audit, run_bounded, run_sync_action
from .workflow import examples, interpret_request, preset_profile, profile_policy, run_case


async def measure_case(args, case, *, warm_data=None):
    started = perf_counter()
    profile_usage = None
    profile_data = preset_profile(case)
    profile = AgentRun("ok", profile_data)
    if args.profile:
        try:
            model = configured_bedrock_runtime(profile=True)
            (parsed, policy, _), profile_usage = await run_bounded(
                interpret_request(case.user_request, model, f"benchmark-{case.id}"), PROFILE_LIMITS,
            )
        except RuntimeBudgetExceeded as exc:
            return {"case": case.id, "status": "profile_budget_exhausted", "passed": False,
                    "profile": exc.usage, "elapsed_ms": (perf_counter() - started) * 1000}
        # This fixed benchmark compares the draft against its predeclared
        # fixture. Interactive calls still pause for a human confirmation.
        if policy != profile_policy(profile_data):
            return {"case": case.id, "status": f"profile_{parsed.status}_mismatch", "passed": False,
                    "profile": profile_usage, "elapsed_ms": (perf_counter() - started) * 1000}

    live = args.mode == "aws"
    runtime = configured_bedrock_runtime() if live else None
    load_ms = None

    async def evaluate():
        nonlocal load_ms
        start_load = perf_counter()
        data = warm_data if warm_data is not None else load_market_data(args.data)
        load_ms = round((perf_counter() - start_load) * 1000, 2)
        return await run_case(data, case, runtime, confirmed_profile=profile)

    result = await bound_audit(evaluate(), case.id, live=live)
    return {
        "case": case.id,
        "status": result["status"],
        "decision_reason": result.get("decision_reason"),
        "passed": validate_case(result),
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "load_ms": load_ms,
        "profile": profile_usage,
        "audit": result["runtime_usage"],
        "routing_fallbacks": sum(event.get("status") == "deterministic_fallback" for event in result["trace"]),
    }


def summarize(rows):
    times = sorted(row["elapsed_ms"] for row in rows)
    usage = [row[stage] for row in rows for stage in ("profile", "audit") if row.get(stage)]
    return {
        "requests": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "p50_ms": round(median(times), 2),
        "p95_ms": round(times[ceil(.95 * len(times)) - 1], 2),
        "http_attempts_started": sum(row["http_attempts_started"] for row in usage),
        "responses_with_usage": sum(row["responses_with_usage"] for row in usage),
        "reported_response_retries": sum(row["reported_response_retries"] for row in usage),
        "reported_total_tokens": sum(row["reported_total_tokens"] for row in usage),
        "routing_fallbacks": sum(row.get("routing_fallbacks", 0) for row in rows),
    }


async def run_benchmark(args):
    cases = [examples("robert")[0], *examples("amira")]
    modes = ("cold", "warm") if args.cache == "both" else (args.cache,)
    data = load_market_data(args.data) if "warm" in modes else None
    measurements = []
    for jobs in args.jobs:
        for mode in modes:
            trials = [(trial, case) for trial in range(1, args.repeats + 1) for case in cases]
            rows = []
            for start in range(0, len(trials), jobs):
                batch = trials[start:start + jobs]
                observations = await asyncio.gather(*(
                    measure_case(args, case, warm_data=data if mode == "warm" else None) for _, case in batch
                ))
                rows.extend({**row, "trial": trial} for (trial, _), row in zip(batch, observations))
            summary = summarize(rows)
            measurements.append({"cache": mode, "max_concurrent_audits": jobs, "summary": summary, "rows": rows})
            print(f"{args.mode} {mode}, up to {jobs} simultaneous: {json.dumps(summary)}", flush=True)
    return {
        "execution": args.mode,
        "measurement_scope": "controller only, excluding human and browser rendering time",
        "cache_scope": "cold reloads market data in process; warm reuses one loaded snapshot",
        "includes_profile": args.profile,
        "measurements": measurements,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--mode", choices=("offline", "aws"), default="offline")
    parser.add_argument("--profile", action="store_true", help="Also run real Bedrock text interpretation; AWS only")
    parser.add_argument("--cache", choices=("cold", "warm", "both"), default="both")
    parser.add_argument("--jobs", nargs="+", type=int, default=[1, 3])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.profile and args.mode != "aws":
        parser.error("--profile requires --mode aws")
    if args.repeats < 1 or min(args.jobs) < 1:
        parser.error("--repeats and --jobs must be positive")

    report = run_sync_action(run_benchmark(args))
    if args.report:
        write_report(args.report, report)
    return 0 if all(row["passed"] for group in report["measurements"] for row in group["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
