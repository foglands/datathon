"""Run or reproduce an AlphaForge simulated trade audit."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from .agents import PROFILE_FIELDS, PROFILE_MODEL, AgentRun, StrandsAgents
from .data import load_market_data
from .publication import publish_report
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
        decision = publish_report(result)
        passed = validate_case(result) and result["status"] == decision["status"]
        results.append({**decision, "passed": passed})
        verified = decision.get("audit", {}).get("verified", {})
        alternative = verified.get("solver_status", "-")
        completed = len(result.get("agent_outputs", {}))
        tag = "PASS" if passed else "FAIL"
        print(f"{tag} {case.id}: review={decision['status']} solver={alternative} "
              f"roles={completed} elapsed_ms={decision['elapsed_ms']}", flush=True)
        if decision["status"] == "execution_error":
            print(decision["explanation"], flush=True)
        for window, values in verified.get("baseline", {}).get("windows", {}).items():
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


def print_policy(policy, *, search_alternatives=True):
    print("\nReview these simulation inputs")
    print(f"  Proposed trade: +{policy['target']:.2%} NVDA, funded from {policy['initial_source']}")
    if search_alternatives:
        print(f"  Permitted alternative funding: {', '.join(policy['allowed_sources'])}")
        size = {True: "yes", False: "no", None: "test the requested size first"}
        print(f"  Smaller purchase allowed: {size[policy['allow_smaller']]}")
    else:
        print("  Scope: original proposal only")
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
    if search_alternatives and policy['prefer_reserve'] is True:
        print("  Preference: preserve ZST.TO")


def print_audit(decision, heading):
    print(f"\n{heading}: {decision['status']}")
    print(decision.get("explanation", ""))
    verified = decision.get("audit", {}).get("verified", {})
    prefer_reserve = decision.get("policy", {}).get("prefer_reserve")
    example_label = "Verified alternative" if prefer_reserve is True else "Verified funding example"
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
    if decision["status"] not in ("execution_error", "invalid") and prefer_reserve is not True:
        frontier = verified.get("frontier", {})
        if frontier.get("full_possible"):
            bottom, top = frontier["full_zst_min"], frontier["full_zst_max"]
            print(f"  ZST.TO funding range: {bottom * 100:.2f} to {top * 100:.2f} percentage points.")
    verification = decision.get("publication", {}).get("section_verification", {})
    for section, label in (("exposure_change", "NVIDIA issuer exposure change"), ("sector_analysis", "Sector exposure")):
        if (status := verification.get(section)) in {"verified", "unavailable", "invalid"}:
            print(f"  {label} verification: {status}")
    for finding in decision.get("audit", {}).get("findings", []):
        if finding["metric_id"].startswith("proposal.") and finding["status"] in ("fail", "insufficient_evidence"):
            actual, limit = finding.get("actual"), finding.get("limit")
            fields = f" [{actual:.2%} vs {limit:.2%}]" if isinstance(actual, (int, float)) and isinstance(limit, (int, float)) else ""
            print(f"  {finding['metric_id']}: {finding['status']}{fields}")


async def run_request(args):
    intake_runtime = StrandsAgents(model_id=PROFILE_MODEL)
    runtime = StrandsAgents()
    request = args.request.strip()
    search_alternatives = getattr(args, "search_alternatives", False)
    include_sector = getattr(args, "include_sector", False)
    unassessed = []
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
                    interpret_request(request, intake_runtime, "interactive",
                                      search_alternatives=search_alternatives, defer_smaller_authorization=True),
                    PROFILE_LIMITS,
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
        field = draft.data.get("clarification_field")
        requirements = draft.data.get("unassessed_requirements") or (
            [{"code": "other_binding", "excerpt": draft.data.get("unsupported_excerpt")}]
            if field == "unsupported_constraint" else []
        )
        if requirements and field not in {"unsupported_scope", "multiple_loss_limits", "conflict"}:
            resolved = {**draft.data, "status": "ok"}
            try:
                scoped_policy = profile_policy(resolved, search_alternatives=False)
            except ValueError:
                scoped_policy = None
            if scoped_policy is not None:
                print("Some binding requirements cannot be assessed.")
                for requirement in requirements:
                    if excerpt := requirement.get("excerpt"):
                        print(f"  Not assessed: {excerpt}")
                print_policy(scoped_policy, search_alternatives=False)
                change = read_input("Type SCOPED to audit only supported rules, enter a correction, or press Enter to end: ")
                if change.casefold() == "scoped":
                    policy = scoped_policy
                    unassessed = [{"code": requirement["code"]} for requirement in requirements]
                    search_alternatives = False
                    break
                if not change:
                    return 0
                request += "\nNew user clarification or correction (takes precedence): " + change
                continue
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
                    manual_draft = (
                        replace(draft, status="ok", data=resolved),
                        profile_policy(resolved, search_alternatives=search_alternatives,
                                       defer_smaller_authorization=True),
                    )
                except ValueError:
                    request += f"\nThe historical loss limit applies to {metric.replace('_', ' ')}."
                    continue
                parsing_trace.append({"role": "profile", "event": "loss_metric_selected", "metric": metric})
                continue
        else:
            print_policy(policy, search_alternatives=search_alternatives)
            change = read_input("Type YES to run the audit, enter a correction, or press Enter to end: ")
            if change.casefold() == "yes":
                break
        if not change:
            return 0
        request += "\nNew user clarification or correction (takes precedence): " + change

    data = load_market_data(args.data)
    case = Case(
        f"interactive-{uuid4().hex[:12]}", "User-confirmed fictional request.", "terminal_loss", None, 0,
        include_sector=include_sector,
    )
    confirmed = {field: draft.data.get(field) for field in PROFILE_FIELDS}
    confirmed.update(status="ok", summary="User confirmed the simulated audit inputs.", evidence_ids=[])
    if unassessed:
        confirmed["unassessed_requirements"] = unassessed

    async def execute_audit(case):
        accepted = replace(draft, status="ok", data=confirmed, trace=tuple(parsing_trace))
        return await bound_audit(run_case(data, case, runtime, confirmed_profile=accepted), case.id, live=True)

    decision = publish_report(await execute_audit(case))
    print_audit(decision, "Audit of original proposal")
    if (search_alternatives and not decision.get("unassessed_requirements")
            and decision.get("publication", {}).get("independent_review_verified") is True):
        choice = read_input("Type SEARCH to authorize an alternative funding search, or press Enter to end: ")
        if choice.casefold() == "search":
            parsing_trace.append({"role": "profile", "event": "alternative_search_authorized"})
            search_case = replace(case, id=f"{case.id}-alternatives", search_alternatives=True)
            decision = publish_report(await execute_audit(search_case))
            if decision.get("needs_smaller_authorization"):
                print("The requested size is infeasible. A smaller purchase could be checked if you authorize it.")
                if read_input("Type YES to authorize a smaller purchase and re-audit, or press Enter to keep the size: ").casefold() == "yes":
                    confirmed = {**confirmed, "allow_smaller": True}
                    parsing_trace.append({"role": "profile", "event": "smaller_purchase_authorized"})
                    resized_case = replace(search_case, id=f"{case.id}-resize")
                    decision = publish_report(await execute_audit(resized_case))
            print_audit(decision, "Alternative funding search")
    if unassessed:
        print("  Not assessed: " + ", ".join(requirement["code"] for requirement in unassessed))
    if args.report:
        write_report(args.report, decision)
    return 1 if decision["status"] in ("execution_error", "invalid") else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Official ZIP or extracted starter directory")
    parser.add_argument("--case", default="all", choices=("all", "robert", "amira"))
    parser.add_argument("--mode", default="offline", choices=("offline", "aws"))
    parser.add_argument("--request", help="Audit a new simulated request interactively (AWS mode)")
    parser.add_argument("--search-alternatives", action="store_true",
                        help="Offer an alternative funding search after the original audit is shown")
    parser.add_argument("--include-sector", action="store_true",
                        help="Include descriptive equity sector analysis in an interactive audit")
    parser.add_argument("--stress", action="store_true", help="Add ambiguity, missing evidence and tampered-result cases")
    parser.add_argument("--report", type=Path, help="Write the publishable result and trace as JSON")
    args = parser.parse_args()
    if args.request is not None:
        if args.mode != "aws" or args.stress or args.case != "all":
            parser.error("--request requires --mode aws and runs independently of the preset stress suite")
        return run_sync_action(run_request(args))
    if args.search_alternatives or args.include_sector:
        parser.error("--search-alternatives and --include-sector apply to --request")
    results = run_sync_action(run_suite(args))
    if args.report:
        write_report(args.report, results)
    print(f"{sum(row['passed'] for row in results)}/{len(results)} scenarios passed ({args.mode})")
    return 0 if all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
