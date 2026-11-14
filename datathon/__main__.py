"""Command-line entry point for the first prototype."""

import argparse
import asyncio
import json
from pathlib import Path

from .agents import StrandsAgents
from .data import load_market_data
from .workflow import examples, run_case


def validate_case(result):
    case = result["case"]
    expected = {
        "robert_terminal": ("feasible_full", {"pass", "fail"}),
        "robert_drawdown": ("no_feasible", {"fail"}),
        "robert_tampered": ("feasible_full", {"invalid"}),
        "robert_ambiguous": (None, {"needs_input"}),
        "amira_missing_qqq": (None, {"insufficient_evidence"}),
        "amira_concentration": (None, {"pass", "fail", "insufficient_evidence"}),
    }
    solver, statuses = expected[case]
    return result["status"] in statuses and (solver is None or result.get("alternatives", {}).get("status") == solver)


async def run_suite(args):
    data = load_market_data(args.data)
    runtime = StrandsAgents() if args.mode == "aws" else None
    results = []
    for case in examples(args.case, args.stress):
        result = await run_case(data, case, runtime)
        result["passed"] = validate_case(result)
        results.append(result)
        alternative = result.get("alternatives", {}).get("status", "-")
        completed = len(result.get("agent_outputs", {}))
        tag = "PASS" if result["passed"] else "FAIL"
        print(f"{tag} {case.id}: review={result['status']} solver={alternative} roles={completed} elapsed_ms={result['elapsed_ms']}", flush=True)
        if "error" in result:
            print(result["error"], flush=True)
        for window, values in result.get("scenarios", {}).get("baseline", {}).get("windows", {}).items():
            print(f"  {window} baseline: terminal={values['terminal_loss']:.2%} drawdown={values['max_drawdown']:.2%}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Official ZIP or extracted starter directory")
    parser.add_argument("--case", default="all", choices=("all", "robert", "amira"))
    parser.add_argument("--mode", default="offline", choices=("offline", "aws"))
    parser.add_argument("--stress", action="store_true", help="Add ambiguity, missing evidence and tampered-result cases")
    parser.add_argument("--report", type=Path, help="Write the test results and trace as JSON")
    args = parser.parse_args()
    results = asyncio.run(run_suite(args))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{sum(row['passed'] for row in results)}/{len(results)} scenarios passed ({args.mode})")
    return 0 if all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
