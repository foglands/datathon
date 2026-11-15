"""Compare two application revisions on the same generated audit and intake requests."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import isclose
import os
from pathlib import Path
from random import Random
from statistics import median
import subprocess
import sys
from time import perf_counter


COHORT_VERSION = "generated-revision-pairs-v1"
AUDIT_MODEL = "us.amazon.nova-2-lite-v1:0"
INTAKE_MODEL = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
KINDS = ("audit", "review", "profile")


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate_cases(seed):
    """Sample the supported scope, mixing structured policies and EN/FR wording."""
    rng = Random(seed)
    cases = []

    def profile():
        qqq, zst, xiu = (rng.randrange(lo, hi, 25) for lo, hi in ((1750, 2350), (1850, 2450), (2100, 2850)))
        scope = {"QQQ": qqq, "ZST.TO": zst, "XIU.TO": xiu, "SPY": 10000 - qqq - zst - xiu, "NVDA": 0}
        source = rng.choice(("QQQ", "ZST.TO"))
        fields = {
            "status": "ok", "summary": "Confirmed generated policy", "evidence_ids": [],
            "target_bps": rng.randrange(425, 1025, 25),
            "initial_source": source, "allowed_sources": ["QQQ", "ZST.TO"],
            "allow_smaller": rng.choice((True, False)), "metric": rng.choice(("terminal_loss", "max_drawdown")),
            "limit_bps": rng.randrange(1300, 1750, 25), "reserve_floor_bps": zst - rng.randrange(375, 1000, 25),
            "issuer_cap_bps": None, "prefer_reserve": rng.choice((True, None)),
        }
        return fields, scope

    for domain, authorized in (("audit_original", False), ("audit_authorized", True), ("audit_missing_issuer", True),
                               ("review_loss_definition", False)):
        fields, scope = profile()
        issuer = domain == "audit_missing_issuer"
        review = domain == "review_loss_definition"
        if issuer:
            fields.update(issuer_cap_bps=rng.randrange(1500, 2000, 25), metric=None, limit_bps=None)
        cases.append({
            "id": domain, "kind": "review" if review else "audit", "profile": fields,
            "weights_bps": scope, "include_2023": rng.choice((True, False)),
            "search": authorized, "missing_qqq": issuer, "include_sector": issuer,
            "expected_option": "toggle_loss_metric" if review else None,
            "hint": rng.choice((
                "Compare the same constraints using {metric}, keeping all other decisions fixed.",
                "How does defining the existing loss limit as {metric} affect the verified audit?",
            )).format(metric="maximum drawdown" if fields["metric"] == "terminal_loss" else "terminal loss")
            if review else None,
        })

    for domain, language in (("profile_en_exact", "en"), ("profile_fr_exact", "fr"),
                             ("profile_ambiguous_loss", "en"), ("profile_conflicting_quantity", "en")):
        fields, _ = profile()
        source, target = fields["initial_source"], fields["target_bps"]
        cap, floor = fields["limit_bps"], fields["reserve_floor_bps"]
        metric_name = "maximum drawdown" if fields["metric"] == "max_drawdown" else "terminal loss"
        grounding = ("target_bps", "limit_bps", "reserve_floor_bps")
        if language == "fr":
            metric_fr = "la baisse maximale" if fields["metric"] == "max_drawdown" else "la perte terminale"
            target_fr = f"{target / 100:g}".replace(".", ",")
            request = rng.choice((
                "Ajoutez exactement {qty} points de pourcentage à NVDA. "
                "Financez cet achat uniquement en vendant {source}.",
                "Achetez exactement {qty} points de pourcentage de NVDA. Vendez uniquement {source} pour financer cet achat.",
            )).format(qty=target_fr, source=source)
            floor_fr, cap_fr = (f"{value / 100:g}".replace(".", ",") for value in (floor, cap))
            request += f" Gardez au moins {floor_fr} % dans ZST.TO. Plafonnez {metric_fr} à {cap_fr} %."
        else:
            qualifier = " exactly" if domain == "profile_en_exact" else ""
            request = rng.choice((
                "Add{qualifier} {qty:g} percentage points of NVDA from {source}.",
                "Buy{qualifier} {qty:g} percentage points of NVDA by selling {source}.",
            )).format(qty=target / 100, source=source, qualifier=qualifier)
            request += f" Keep at least {floor / 100:g}% in ZST.TO."
            if domain == "profile_ambiguous_loss":
                request += f" I can lose at most {cap / 100:g}%."
            else:
                request += f" Limit {metric_name} to {cap / 100:g}%."
            if domain == "profile_conflicting_quantity":
                request += f" Add {(target + 125) / 100:g} percentage points of NVDA from the same source."
        fields = {key: fields[key] for key in (*grounding, "initial_source", "metric")}
        expectation = {
            "profile_ambiguous_loss": ["loss_metric"],
            "profile_conflicting_quantity": ["target", "conflict"],
        }.get(domain)
        cases.append({
            "id": domain, "kind": "profile", "request": request, "search": False,
            "expected_fields": None if expectation else fields, "expected_clarifications": expectation,
        })
    return cases


def _calls(trace):
    responses = [row for row in trace if row.get("event") == "bedrock"]
    successes = [row for row in responses if row.get("http_status") == 200 and row.get("status") == "success"]
    receipts = [
        sha256(row["request_id"].encode()).hexdigest()[:12]
        for row in successes if isinstance(row.get("request_id"), str)
    ]
    return {
        "successful_converse": len(successes), "failed_converse": len(responses) - len(successes),
        "request_id_hashes": receipts,
        "observed_tokens": sum((row.get("total_tokens") or 0) for row in successes),
        "token_responses": sum(type(row.get("total_tokens")) is int for row in successes),
        "routing_fallbacks": sum(row.get("status") == "deterministic_fallback" for row in trace),
    }


def _authorization_preserved(raw, published, authorized):
    if published.get("search_alternatives") is not authorized:
        return False
    if authorized:
        return "alternatives" in raw
    return not (
        "alternatives" in raw
        or any(event.get("tool_name") == "solve_funding_range" for event in raw.get("trace", ()))
        or {"frontier", "maximum", "solver_status"}.intersection(published.get("audit", {}).get("verified", {}))
    )


def _independent_invariants(published, case):
    verified = published.get("audit", {}).get("verified", {})
    baseline, proposal = (verified.get(leg, {}) for leg in ("baseline", "proposal"))
    opening = {ticker: value / 10000 for ticker, value in case["weights_bps"].items()}
    changed = dict(opening)
    quantity = case["profile"]["target_bps"] / 10000
    changed[case["profile"]["initial_source"]] -= quantity
    changed["NVDA"] += quantity
    window_ids = {"2022", "2023", "2025"} if case["include_2023"] else {"2022", "2025"}
    for leg, expected_weights in ((baseline, opening), (proposal, changed)):
        weights, windows = (leg.get(key, {}) for key in ("weights", "windows"))
        if weights.keys() != expected_weights.keys() or windows.keys() != window_ids:
            return False
        if any(not isclose(weights[key], number, rel_tol=0, abs_tol=1e-10) for key, number in expected_weights.items()):
            return False
        for window in windows.values():
            loss = window["terminal_loss"]
            if not isclose(loss, max(0, -window["terminal_return"]), rel_tol=0, abs_tol=1e-10):
                return False
            if not 0 <= loss <= window["max_drawdown"] + 1e-10 <= 1 + 1e-10:
                return False
    if case["missing_qqq"]:
        finding = next((row for row in published["audit"]["findings"]
                        if row["metric_id"] == "proposal.issuer_weight.policy"), {})
        return (finding.get("status") == "insufficient_evidence"
                and (not case["search"] or verified.get("frontier", {}).get("status") == "insufficient_evidence"))
    return True


def _verified_projection(published):
    return {
        key: published.get(key) for key in (
            "status", "decision_reason", "search_alternatives", "audit", "sector_analysis", "exposure_change",
        )
    }


def _profile_result(draft, policy, question, case):
    fields = case["expected_fields"]
    clarification = draft.data.get("clarification_field")
    if fields is None:
        passed = draft.status != "error" and policy is None and bool(question)
        passed = passed and clarification in case["expected_clarifications"]
    else:
        passed = draft.status == "ok" and policy is not None and question is None
        passed = passed and all(draft.data.get(name) == value for name, value in fields.items())
        passed = passed and all(
            isinstance(draft.data.get("source_excerpts", {}).get(name), str)
            and bool(draft.data["source_excerpts"][name])
            and draft.data["source_excerpts"][name] in case["request"]
            for name in fields if name.endswith("_bps")
        )
    return {
        "passed": passed, "status": draft.status, "clarification_field": clarification,
        "policy_available": policy is not None,
        "policy": {key: draft.data.get(key) for key in
                   ("target_bps", "initial_source", "metric", "limit_bps", "reserve_floor_bps", "issuer_cap_bps")},
    }


async def _evaluate(job):
    from datathon.agents import AgentRun, StrandsAgents
    from datathon.benchmark import fingerprint
    from datathon.counterfactual import run_counterfactual
    from datathon.data import load_market_data
    from datathon.publication import publish_check, publish_report
    from datathon.runtime_budget import (
        CHALLENGE_LIMITS, PROFILE_LIMITS, RuntimeBudgetExceeded, bound_audit, run_bounded,
    )
    from datathon.scope import ReplayScope
    from datathon.workflow import Case, interpret_request, run_case

    case = job["case"]
    live = job["mode"] == "aws"
    market = load_market_data(job["data"])
    dataset = fingerprint(job["data"])
    runtime = StrandsAgents(model_id=job["audit_model"], region=job["region"]) if live else None
    trace = []
    started = perf_counter()
    try:
        if case["kind"] == "profile":
            profile_runtime = StrandsAgents(model_id=job["intake_model"], region=job["region"])
            (draft, policy, question), _ = await run_bounded(
                interpret_request(case["request"], profile_runtime, case["id"],
                                  search_alternatives=case["search"], defer_smaller_authorization=True),
                PROFILE_LIMITS,
            )
            trace = draft.trace
            result = _profile_result(draft, policy, question, case)
        else:
            profile = case["profile"]
            as_fraction = lambda field: profile[field] / 10000 if profile[field] is not None else None
            workflow_case = Case(
                case["id"], "Confirmed generated simulated trade", profile["metric"] or "terminal_loss",
                as_fraction("limit_bps"), as_fraction("reserve_floor_bps") or 0, as_fraction("issuer_cap_bps"),
                missing_qqq=case["missing_qqq"], search_alternatives=case["search"],
                include_sector=case["include_sector"],
                scope=ReplayScope(case["weights_bps"], include_2023=case["include_2023"]),
            )
            raw = await bound_audit(run_case(market, workflow_case, runtime,
                                             confirmed_profile=AgentRun("ok", profile)), case["id"], live=live)
            output = publish_report(raw)
            trace = list(raw.get("trace", ()))
            invariants = _independent_invariants(output, case)
            result = {
                "passed": output["publication"]["independent_review_verified"]
                and _authorization_preserved(raw, output, case["search"]) and invariants,
                "status": output["status"], "reason": output.get("decision_reason"),
                "sector_verified": output["publication"].get("section_verification", {}).get("sector_analysis"),
                "verified_digest": _digest(_verified_projection(output)), "independent_invariants": invariants,
            }
            if case["include_sector"]:
                result["passed"] = result["passed"] and result["sector_verified"] == "verified"
            if case["kind"] == "review" and result["passed"]:
                review, _ = await run_bounded(
                    run_counterfactual(
                        market, workflow_case, raw, selector_runtime=runtime, replay_runtime=runtime,
                        option_id=case["expected_option"] if not live else None,
                        challenge_hint=case["hint"] if live else None,
                    ), CHALLENGE_LIMITS,
                )
                checked = publish_check(review)
                replay = checked.get("replay") or {}
                trace.extend(checked.get("trace", ()))
                trace.extend(replay.get("trace", ()))
                observed_option = (checked.get("option") or {}).get("id")
                result.update(
                    passed=observed_option == case["expected_option"] and checked.get("verified") is True
                    and replay.get("search_alternatives") is case["search"]
                    and (case["search"] or not
                         ({"frontier", "maximum", "solver_status"} & replay.get("audit", {}).get("verified", {}).keys())),
                    review_option=observed_option, review_status=checked.get("status"),
                    review_reason=checked.get("reason"),
                    replay_digest=_digest(_verified_projection(replay)),
                )
    except RuntimeBudgetExceeded as exc:
        result = {"passed": False, "status": "budget_exhausted", "reason": exc.reason}
    return {
        "case": case["id"], "kind": case["kind"], "data_sha256": dataset,
        "elapsed_ms": round((perf_counter() - started) * 1000, 2), **_calls(trace), **result,
    }


def _invoke(job, checkout):
    started = perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker"], cwd=checkout,
            input=json.dumps(job, ensure_ascii=False), text=True, capture_output=True, timeout=75,
            env={**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip().splitlines()[-1])
        reason = f"worker_exit_{result.returncode}"
    except subprocess.TimeoutExpired:
        reason = "worker_timeout"
    except (IndexError, json.JSONDecodeError):
        reason = "missing_worker_result"
    return {
        "case": job["case"]["id"], "kind": job["case"]["kind"], "status": "worker_error",
        "reason": reason, "passed": False, "elapsed_ms": round((perf_counter() - started) * 1000, 2), **_calls(()),
    }


def _revision(checkout):
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=checkout, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _run(args):
    manifest = json.loads(args.manifest.read_text()) if args.manifest else generate_cases(args.seed)
    if not manifest or len({case["id"] for case in manifest}) != len(manifest) or any(
        case["kind"] not in KINDS for case in manifest
    ):
        raise ValueError("The manifest must contain distinct IDs for supported case kinds.")
    if args.write_manifest:
        args.write_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    original_digest = _digest(manifest)
    if args.domains and set(args.domains) - {case["id"] for case in manifest}:
        raise ValueError("One or more requested domains are absent from the manifest.")
    manifest = [case for case in manifest
                if (not args.domains or case["id"] in args.domains)
                and (not args.scenario_kind or case["kind"] == args.scenario_kind)]
    checkouts = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    for checkout in checkouts.values():
        if not (checkout / "datathon" / "workflow.py").is_file():
            raise ValueError(f"Application source missing from {checkout}.")
    job = {key: getattr(args, key) for key in ("mode", "intake_model", "audit_model", "region")}
    job["data"] = str(args.data.resolve())
    rows, references, pairs = [], {}, []
    for trial in range(args.trials):
        for index, case in enumerate(manifest):
            if args.mode == "offline" and case["kind"] == "profile":
                continue
            if case["kind"] != "profile" and case["id"] not in references:
                reference = _invoke({**job, "case": case, "mode": "offline"}, checkouts["baseline"])
                references[case["id"]] = reference
            order = ("baseline", "candidate") if (index + trial) % 2 == 0 else ("candidate", "baseline")
            paired = {}
            for arm in order:
                row = _invoke({**job, "case": case}, checkouts[arm])
                if reference := references.get(case["id"]):
                    matches = reference["passed"] and all(row.get(key) == reference.get(key) for key in (
                        "data_sha256", "verified_digest", "replay_digest",
                    ))
                    row["matches_offline_reference"] = matches
                    row["passed"] = row["passed"] and matches
                rows.append({"arm": arm, "trial": trial + 1, "pair_order": order.index(arm) + 1, **row})
                paired[arm] = row
                print(f"{arm} {case['id']} {row['status']} {'PASS' if row['passed'] else 'FAIL'} "
                      f"{row['successful_converse']} Converse {row['elapsed_ms']} ms", flush=True)
            baseline, candidate = paired["baseline"], paired["candidate"]
            pairs.append({
                "case": case["id"], "trial": trial + 1,
                "both_passed": baseline["passed"] and candidate["passed"],
                "candidate_minus_baseline_ms": round(candidate["elapsed_ms"] - baseline["elapsed_ms"], 2),
                "candidate_minus_baseline_converse": candidate["successful_converse"] - baseline["successful_converse"],
            })
    summary = {}
    for arm in checkouts:
        measured = [row for row in rows if row["arm"] == arm]
        times = [row["elapsed_ms"] for row in measured]
        summary[arm] = {
            "checks": len(measured), "passed": sum(row["passed"] for row in measured),
            "median_ms": median(times) if times else None, "max_ms": max(times, default=None),
            "successful_converse": sum(row["successful_converse"] for row in measured),
            "failed_converse": sum(row["failed_converse"] for row in measured),
            "routing_fallbacks": sum(row["routing_fallbacks"] for row in measured),
        }
    result = {
        "cohort_version": COHORT_VERSION, "seed": None if args.manifest else args.seed,
        "manifest_sha256": original_digest, "cases": [case["id"] for case in manifest], "trials": args.trials,
        "configuration": {**job, "data": Path(job["data"]).name},
        "revisions": {arm: getattr(args, f"{arm}_ref") or _revision(checkout) for arm, checkout in checkouts.items()},
        "scope": "Supported asset scope. Warm market snapshot, sequential counterbalanced pairs. Offline skips Profile.",
        "summary": summary, "pairs": pairs, "runs": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return summary["candidate"]["checks"] > 0 and summary["candidate"]["passed"] == summary["candidate"]["checks"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-ref", help="Source revision label for an archived baseline.")
    parser.add_argument("--candidate-ref", help="Source revision label for an archived candidate.")
    parser.add_argument("--mode", choices=("offline", "aws"), default="offline")
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--write-manifest", type=Path)
    parser.add_argument("--domains", nargs="+", help="Run selected case IDs from the manifest.")
    parser.add_argument("--scenario-kind", choices=KINDS)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--intake-model", default=INTAKE_MODEL)
    parser.add_argument("--audit-model", default=AUDIT_MODEL)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive.")
    return 0 if _run(args) else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        sys.path.insert(0, str(Path.cwd()))
        from datathon.runtime_budget import run_sync_action

        print(json.dumps(run_sync_action(_evaluate(json.load(sys.stdin))), allow_nan=False))
    else:
        raise SystemExit(main())
