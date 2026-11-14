"""Run or reproduce an AlphaForge simulated trade audit."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .agents import PROFILE_FIELDS, PROFILE_MODEL, AgentRun, StrandsAgents
from .data import load_market_data
from .runtime_budget import PROFILE_LIMITS, RuntimeBudgetExceeded, bound_audit, run_bounded, run_sync_action
from .workflow import Case, examples, interpret_request, preset_profile, profile_policy, run_case


def validate_case(result):
    expected = {
        "robert_terminal": ("fail", "feasible_full"),
        "robert_drawdown": ("fail", "no_feasible"),
        "robert_tampered": ("invalid", "feasible_full"),
        "robert_ambiguous": ("needs_input", None),
        "amira_missing_qqq": ("insufficient_evidence", "insufficient_issuer_evidence"),
        "amira_concentration": ("fail", "insufficient_issuer_evidence"),
    }
    observed = (result["status"], result.get("alternatives", {}).get("status"))
    if observed != expected[result["case"]]:
        return False
    verified = result.get("audit", {}).get("verified", {})
    if result["case"] == "robert_terminal":
        upper = verified.get("frontier", {}).get("full_zst_max")
        return (upper is not None and abs(upper - .02631671476152258) < 1e-8
                and verified.get("maximum", {}).get("passes") is True)
    if result["case"] == "robert_drawdown":
        return verified.get("no_feasible_confirmed") is True
    if result["case"] in ("amira_concentration", "amira_missing_qqq"):
        return len(result.get("scenarios", {}).get("proposal", {}).get("windows", {})) == 2
    return True


async def run_suite(args):
    data = load_market_data(args.data)
    runtime = StrandsAgents() if args.mode == "aws" else None
    results = []
    for case in examples(args.case, args.stress):
        if case.ambiguous:
            intake = StrandsAgents(model_id=PROFILE_MODEL) if runtime is not None else None
            result = await bound_audit(run_case(data, case, intake), case.id, live=intake is not None)
        else:
            preset = AgentRun("ok", preset_profile(case), ({"role": "profile", "event": "preset_inputs_selected"},))
            result = await bound_audit(
                run_case(data, case, runtime, confirmed_profile=preset), case.id, live=runtime is not None,
            )
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


def write_report(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_input(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def print_policy(policy):
    print("\nReview these simulation inputs")
    print(f"  Proposed trade: +{policy['target']:.2%} NVDA, funded from {policy['initial_source']}")
    print(f"  Permitted funding: {', '.join(policy['allowed_sources'])}")
    print(f"  Smaller purchase allowed: {'yes' if policy['allow_smaller'] else 'no'}")
    print(f"  Minimum ZST.TO weight: {policy['reserve_floor']:.2%}")
    if policy['loss_limit'] is not None:
        metric = policy['metric'].replace('_', ' ')
        print(f"  {metric.capitalize()} limit in both historical windows: {policy['loss_limit']:.2%}")
    else:
        print("  Historical loss limit: none specified")
    if policy['issuer_cap'] is not None:
        print(f"  NVIDIA issuer exposure cap: {policy['issuer_cap']:.2%}")
    else:
        print("  NVIDIA issuer exposure cap: none specified")
    if policy['prefer_reserve'] is True:
        print("  Preference: preserve ZST.TO")


async def run_request(args):
    intake_runtime = StrandsAgents(model_id=PROFILE_MODEL)
    runtime = StrandsAgents()
    request = args.request.strip()
    print("Simulation only. Use fictional portfolio information.")
    parsing_trace = []
    manual_draft = None
    if not request:
        print("Provide a simulated trade request.")
        return 2
    while True:
        if manual_draft is not None:
            draft, policy = manual_draft
            manual_draft = None
            question = None
        else:
            try:
                (draft, policy, question), profile_usage = await run_bounded(
                    interpret_request(request, intake_runtime, "interactive"), PROFILE_LIMITS,
                )
            except RuntimeBudgetExceeded as exc:
                print("Profile interpretation reached its execution budget.")
                if args.report:
                    write_report(args.report, {"status": "execution_error", "trace": parsing_trace,
                                               "runtime_usage": exc.usage})
                return 1
            parsing_trace.extend(draft.trace)
            parsing_trace.append({"role": "profile", "event": "runtime_usage", **profile_usage})
        if draft.status == "error":
            print(question)
            if args.report:
                write_report(args.report, {"status": "execution_error", "trace": parsing_trace})
            return 1
        if question:
            print(question)
            if draft.data.get("clarification_field") == "loss_metric" and draft.data.get("limit_bps") is not None:
                print("  1. Terminal loss (start to finish)")
                print("  2. Maximum drawdown (peak to trough)")
            change = read_input("Clarify the request, or press Enter to end: ")
            while change.casefold() == "yes":
                print(question)
                change = read_input("Provide the missing detail, or press Enter to end: ")
            if (draft.data.get("clarification_field") == "loss_metric" and draft.data.get("limit_bps") is not None
                    and change in ("1", "2")):
                metric = "terminal_loss" if change == "1" else "max_drawdown"
                resolved = {**draft.data, "status": "ok", "metric": metric, "clarification_field": None}
                try:
                    manual_draft = (replace(draft, status="ok", data=resolved), profile_policy(resolved))
                except ValueError:
                    request += f"\nThe historical loss limit applies to {metric.replace('_', ' ')}."
                    continue
                parsing_trace.append({"role": "profile", "event": "loss_metric_selected", "metric": metric})
                continue
        else:
            print_policy(policy)
            change = read_input("Type YES to run the audit, enter a correction, or press Enter to end: ")
            if change.casefold() == "yes":
                break
        if not change:
            return 0
        request += "\nNew user clarification or correction (takes precedence): " + change

    data = load_market_data(args.data)
    case = Case("interactive", "User-confirmed fictional request.", "terminal_loss", None, 0)
    confirmed = {field: draft.data.get(field) for field in PROFILE_FIELDS}
    confirmed.update(status="ok", summary="User confirmed the simulated audit inputs.", evidence_ids=[])
    decision = await bound_audit(
        run_case(data, case, runtime, confirmed_profile=replace(draft, data=confirmed, trace=tuple(parsing_trace))),
        case.id, live=True,
    )
    print(f"\nAudit of original proposal: {decision['status']}")
    print(decision.get("explanation", decision.get("error", "")))
    verified = decision.get("audit", {}).get("verified", {})
    example_label = "Verified alternative" if policy["prefer_reserve"] is True else "Verified funding example"
    for label, description in (("baseline", "Starting portfolio"), ("proposal", "Original proposal"),
                               ("maximum", example_label)):
        outcome = verified.get(label)
        if label == "maximum" and (decision["status"] in ("execution_error", "invalid", "insufficient_evidence")
                                   or not outcome or not outcome["passes"] or (outcome.get("total") or 0) <= 1e-9):
            continue
        if outcome:
            print(f"  {description}: {outcome['status']}")
            if label == "maximum":
                mix = outcome["funding"]
                print(f"    Funding: QQQ {mix['QQQ'] * 100:.2f} pp, ZST.TO {mix['ZST.TO'] * 100:.2f} pp")
    if decision["status"] not in ("execution_error", "invalid") and policy["prefer_reserve"] is not True:
        frontier = verified.get("frontier", {})
        if frontier.get("full_possible"):
            bottom, top = frontier["full_zst_min"], frontier["full_zst_max"]
            print(f"  ZST.TO funding range: {bottom * 100:.2f} to {top * 100:.2f} percentage points.")
    for finding in decision.get("audit", {}).get("findings", []):
        if finding["metric_id"].startswith("proposal.") and finding["status"] in ("fail", "insufficient_evidence"):
            actual, limit = finding.get("actual"), finding.get("limit")
            fields = f" [{actual:.2%} vs {limit:.2%}]" if isinstance(actual, (int, float)) and isinstance(limit, (int, float)) else ""
            print(f"  {finding['metric_id']}: {finding['status']}{fields}")
    if args.report:
        write_report(args.report, decision)
    return 1 if decision["status"] in ("execution_error", "invalid") else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Official ZIP or extracted starter directory")
    parser.add_argument("--case", default="all", choices=("all", "robert", "amira"))
    parser.add_argument("--mode", default="offline", choices=("offline", "aws"))
    parser.add_argument("--request", help="Audit a new simulated request interactively (AWS mode)")
    parser.add_argument("--stress", action="store_true", help="Add ambiguity, missing evidence and tampered-result cases")
    parser.add_argument("--report", type=Path, help="Write the test results and trace as JSON")
    args = parser.parse_args()
    if args.request is not None:
        if args.mode != "aws" or args.stress or args.case != "all":
            parser.error("--request requires --mode aws and runs independently of the preset stress suite")
        return run_sync_action(run_request(args))
    results = run_sync_action(run_suite(args))
    if args.report:
        write_report(args.report, results)
    print(f"{sum(row['passed'] for row in results)}/{len(results)} scenarios passed ({args.mode})")
    return 0 if all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
