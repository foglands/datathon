"""Measure held-out audit challenges without changing the confirmed decision."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import perf_counter

from .agents import DEFAULT_MODEL, DEFAULT_REGION, AgentRun, StrandsAgents
from .benchmark import fingerprint, usage
from .benchmark_cases import ProfileGold
from .benchmark_single import SingleAgentRuntime
from .challenge_expansion import cases as expanded_cases
from .counterfactual import counterfactual_options, run_counterfactual
from .data import load_market_data
from .workflow import Case, run_case


COHORT_VERSION = "held-out-challenge-v1"
EXPANDED_COHORT_VERSION = "held-out-challenge-v2"
OFFICIAL_STARTER_SHA256 = {
    "prices_daily.csv": "ff2a3f2d0a7d72ea835e8d616d041e0510f018340cef3d3e55b918830e8a569d",
    "fx_usdcad_daily.csv": "f04e218ac5b0145fd552b3d0dcfbf73e5e17bb9a6fb4562460dbec95cb8972b3",
    "sources_metadata.csv": "7ff17052c8235888c4984430830610ae0d81c0df71585afaacb87ba5fe531bdf",
}
MEASURES = (
    "eligible_max_total", "diagnostic_max_total", "full_zst_min", "full_zst_max",
    "proposal_terminal_loss", "proposal_max_drawdown", "proposal_reserve_headroom", "proposal_loss_headroom",
    "proposal_issuer_lower", "proposal_issuer_upper",
)
FLAGS = ("original_proposal_eligible", "alternative_eligible")
OUTCOME_KEYS = ("status", "decision_reason", "solver_status", *FLAGS)
ABSTAIN = "no_material_challenge"
SELECTOR_LIMITS = {"timeout_seconds": 20, "max_turns": 4, "max_total_tokens": 5000}
LIVE_ARMS = ("bundled_single", "staged_multi")


@dataclass(frozen=True)
class Outcome:
    status: str
    decision_reason: str
    solver_status: str | None
    original_proposal_eligible: bool
    alternative_eligible: bool


@dataclass(frozen=True)
class ChallengeCase:
    id: str
    request: str
    profile: ProfileGold
    expected_option: str
    expected_reason: str
    before: Outcome
    after: Outcome | None
    # These are preregistered before/after weights or losses in basis points.
    paired_bps: tuple[tuple[str, int | None, int | None], ...]
    rationale: str
    missing_qqq: bool = False
    holdings_max_age_days: int = 180
    required_disclosure: str | None = None
    evidence_date: str = "2026-11-14"
    omitted_fx_date: str | None = None
    required_disclosure_reason: str | None = None
    expected_issuer_ids: tuple[tuple[str, ...], tuple[str, ...] | None] | None = None

    def market_inputs(self, data):
        if self.omitted_fx_date is None:
            return data
        fx = dict(data.fx)
        del fx[self.omitted_fx_date]
        return replace(data, fx=fx)

    def workflow_case(self):
        return Case(self.id, "Confirmed model portfolio audit", self.profile.metric or "terminal_loss",
                    (self.profile.limit_bps / 10_000 if self.profile.limit_bps is not None else None),
                    (self.profile.reserve_floor_bps or 0) / 10_000,
                    (self.profile.issuer_cap_bps / 10_000 if self.profile.issuer_cap_bps is not None else None),
                    missing_qqq=self.missing_qqq)

    def confirmed_profile(self):
        return AgentRun("ok", self.profile.as_profile())


FULL = Outcome("fail", "feasible_full", "feasible_full", False, True)
PASS = Outcome("pass", "feasible_full", "feasible_full", True, True)
PARTIAL = Outcome("fail", "feasible_partial", "feasible_partial", False, True)
EXACT_BLOCKED = Outcome("fail", "requested_size_infeasible", "requested_size_infeasible", False, False)
BASELINE_BLOCKED = Outcome("fail", "baseline_breaches_policy", "no_feasible", False, False)
ISSUER_UNKNOWN = Outcome("insufficient_evidence", "issuer_evidence_insufficient", "insufficient_issuer_evidence",
                         False, False)
ISSUER_BREACH = Outcome("fail", "issuer_evidence_insufficient", "insufficient_issuer_evidence", False, False)


# Gold is scored after selection. Only request, confirmed policy and verified
# baseline are seen by the model. The inputs differ from the earlier audit suite.
CHALLENGE_CASES = (
    ChallengeCase(
        "loss_metric_path",
        "Opening-to-ending loss looks acceptable for a full alternative. Would the deepest fall "
        "from an earlier high change that conclusion? Keep the numerical cap and funding terms.",
        ProfileGold(900, "ZST.TO", ("QQQ", "ZST.TO"), True, "terminal_loss", 1450, 1600,
                    prefer_reserve=True),
        "toggle_loss_metric", "comparison_verified", FULL, BASELINE_BLOCKED,
        (("eligible_max_total", 900, None), ("full_zst_max", 400, None), ("proposal_loss_headroom", -117, -564)),
        "The drawdown cap invalidates the starting portfolio and the authorized alternatives.",
    ),
    ChallengeCase(
        "loss_metric_endpoint",
        "The result flags a fall within a replay. For comparison, check what happens if only "
        "where the period ends relative to its opening value defines the same loss cap.",
        ProfileGold(800, "ZST.TO", ("QQQ", "ZST.TO"), True, "max_drawdown", 1450, 1600,
                    prefer_reserve=True),
        "toggle_loss_metric", "comparison_verified", BASELINE_BLOCKED, FULL,
        (("eligible_max_total", None, 800), ("full_zst_max", None, 400), ("proposal_loss_headroom", -518, -69)),
        "Keeping the cap while switching the measuring convention admits a full QQQ-funded option.",
    ),
    ChallengeCase(
        "reserve_full_range",
        "Would keeping three extra portfolio points in the short-term bond sleeve shrink the "
        "funding split even if the whole purchase is still possible?",
        ProfileGold(700, "QQQ", ("QQQ", "ZST.TO"), True, "terminal_loss", 1500, 1700,
                    prefer_reserve=True),
        "tighten_reserve_floor", "comparison_verified", PASS, PASS,
        (("eligible_max_total", 700, 700), ("full_zst_max", 300, 0), ("proposal_reserve_headroom", 300, 0)),
        "Changing the reserve floor from 17% to 20% removes ZST.TO funding at the full size.",
    ),
    ChallengeCase(
        "reserve_partial_range",
        "I still accept a smaller purchase. How much is left if the minimum bond reserve is "
        "three percentage points higher? Leave the allowed funding source unchanged.",
        ProfileGold(700, "ZST.TO", ("ZST.TO",), True, "terminal_loss", 1500, 1500,
                    prefer_reserve=True),
        "tighten_reserve_floor", "comparison_verified", PARTIAL, PARTIAL,
        (("eligible_max_total", 500, 200), ("proposal_reserve_headroom", -200, -500)),
        "The maximum permitted partial purchase falls from 5% to 2% of the portfolio.",
    ),
    ChallengeCase(
        "size_allow_partial",
        "Keep the reserve and the original funding list. If the purchase doesn't have to be "
        "all or nothing, what positive-size comparison can you verify?",
        ProfileGold(1100, "ZST.TO", ("ZST.TO",), False, "terminal_loss", 1450, 1600),
        "toggle_purchase_size", "comparison_verified", EXACT_BLOCKED, PARTIAL,
        (("eligible_max_total", None, 400), ("diagnostic_max_total", 400, 400)),
        "The four-point comparison becomes eligible under the hypothetical permission for partial size.",
    ),
    ChallengeCase(
        "size_require_full",
        "I need the contrast for a fixed-size simulation without partial fills. Keep the exact "
        "original requested amount and the same risk and funding limits.",
        ProfileGold(800, "ZST.TO", ("ZST.TO",), True, "terminal_loss", 1450, 1700),
        "toggle_purchase_size", "comparison_verified", PARTIAL, EXACT_BLOCKED,
        (("eligible_max_total", 300, None), ("diagnostic_max_total", 300, 300)),
        "The three-point diagnostic capacity remains measurable but cannot satisfy the exact-size rule.",
    ),
    ChallengeCase(
        "issuer_missing_filing",
        "Keep the issuer limit and all trade terms. Tell me which fund's issuer disclosure would "
        "let us check the remaining evidence gap.",
        ProfileGold(900, "ZST.TO", ("QQQ", "ZST.TO"), True, issuer_cap_bps=1300),
        "request_issuer_evidence", "issuer_evidence_required", ISSUER_UNKNOWN, None,
        (("proposal_issuer_lower", 1163, None), ("proposal_issuer_upper", 6763, None)),
        "QQQ evidence is absent. Its unresolved exposure cannot be replaced with zero.",
        missing_qqq=True, required_disclosure="QQQ",
    ),
    ChallengeCase(
        "issuer_tighter_disclosure_age",
        "Try a 90-day freshness limit for the disclosed fund holdings. Show how it changes "
        "the verified issuer bounds with the same reference date and purchase.",
        ProfileGold(900, "ZST.TO", ("QQQ", "ZST.TO"), True, issuer_cap_bps=1300),
        "tighten_holdings_age", "comparison_verified", ISSUER_BREACH, ISSUER_UNKNOWN,
        (("proposal_issuer_lower", 1315, 900), ("proposal_issuer_upper", 4915, 10000)),
        "The dated disclosures become stale. The wider interval keeps only direct issuer exposure verified.",
        holdings_max_age_days=150,
    ),
    ChallengeCase(
        "abstain_no_change_requested",
        "I only need the checked result for this full-size, QQQ-funded purchase under the "
        "current rules. There is no policy or disclosure change to examine.",
        ProfileGold(400, "QQQ", ("QQQ",), True),
        ABSTAIN, "challenge_declined", PASS, None,
        (("eligible_max_total", 400, None),),
        "There is no binding issue and the request does not pose a counterfactual.",
    ),
)


EXPANDED_CASES = expanded_cases(
    ChallengeCase, abstain=ABSTAIN, baseline_blocked=BASELINE_BLOCKED, exact_blocked=EXACT_BLOCKED,
    issuer_unknown=ISSUER_UNKNOWN, partial=PARTIAL, approved=PASS,
    market_unknown=Outcome("insufficient_evidence", "market_evidence_insufficient", None, False, False),
)

def fixed_option(policy, verified, options):
    """Use the same audited signals across all fixtures, independent of their labels."""
    available = {option["id"] for option in options}
    reason = verified.get("decision_reason")
    if reason == "issuer_evidence_insufficient" and "request_issuer_evidence" in available:
        return "request_issuer_evidence"
    if reason in {"requested_size_infeasible", "feasible_partial"} and "toggle_purchase_size" in available:
        return "toggle_purchase_size"
    if reason == "baseline_breaches_policy" and "toggle_loss_metric" in available:
        return "toggle_loss_metric"
    if verified.get("full_zst_max_binding") == "reserve_floor" and "tighten_reserve_floor" in available:
        return "tighten_reserve_floor"
    if policy.get("loss_limit") is not None and "toggle_loss_metric" in available:
        return "toggle_loss_metric"
    return ABSTAIN


class FixedSelector:
    """Apply the heuristic through the same allowlisted selector handler as the live arms."""

    async def run(self, role, payload, *, tools, run_id):
        option_id = fixed_option(payload["policy"], payload["verified_outcome"], payload["options"])
        tool, = tools
        tool.handler(option_id)
        trace = [{"role": role, "event": "offline_tool", "status": "success", "tool_name": tool.name,
                  "input": {"option_id": option_id}}]
        return AgentRun("ok", {"summary": "Fixed challenge policy applied."}, trace)


def basis_points(summary, name):
    value = (summary or {}).get(name)
    return round(10_000 * value) if type(value) in (float, int) and math.isfinite(value) else None


def outcome_matches(observed, expected):
    if expected is None:
        return observed is None
    return observed is not None and all(observed.get(name) == value for name, value in asdict(expected).items())


def selected_option(challenge):
    event = next((row for row in reversed(challenge.get("trace", ()))
                  if row.get("event") == "challenge_selection" and row.get("status") == "selected"), {})
    return event.get("option_id")


def replay_scope_safe(baseline, challenge, chosen):
    replay = challenge.get("replay")
    if replay is None:
        return not challenge.get("changed_fields")
    option = next((item for item in counterfactual_options(baseline) if item.id == chosen), None)
    if option is None or option.action or challenge.get("changed_fields") != [option.field]:
        return False
    expected_policy = dict(baseline["policy"])
    before = baseline["evidence"]
    after = replay["evidence"]
    if option.field == "holdings_max_age_days":
        old_snapshot = before.get("issuer_snapshot", {})
        new_snapshot = after.get("issuer_snapshot", {})
        for key in ("as_of", "reference_date", "publication_cutoff"):
            if old_snapshot.get(key) != new_snapshot.get(key):
                return False
        if new_snapshot.get("max_age_days") != option.after:
            return False
        old_rows, new_rows = old_snapshot.get("holdings", {}), new_snapshot.get("holdings", {})
        disclosure_fields = ("as_of", "published_on", "url", "source", "reported_status", "reported_weight")
        if old_rows.keys() != new_rows.keys() or any(
            before.get(field) != new_rows[ticker].get(field)
            for ticker, before in old_rows.items() for field in disclosure_fields
        ):
            return False
    else:
        expected_policy[option.field] = option.after
        if (before.get("issuer_snapshot") != after.get("issuer_snapshot")
                or before.get("evidence_ids") != after.get("evidence_ids")):
            return False
    if replay.get("policy") != expected_policy:
        return False
    if any(before.get(key) != after.get(key) for key in ("basis", "price_source", "fx_source", "windows")):
        return False
    originals = baseline["audit"]["verified"]
    compared = replay["audit"]["verified"]
    return all(originals.get(leg, {}).get(key) == compared.get(leg, {}).get(key)
               for leg in ("baseline", "proposal") for key in ("weights", "windows"))


def audit_completed(report):
    if not report or not report.get("audit", {}).get("verified"):
        return False
    audit = report["audit"]
    if report.get("status") != audit.get("status") or report.get("decision_reason") != audit.get("decision_reason"):
        return False
    return any(row.get("tool_name") == "recheck_decision" and
               (row.get("event"), row.get("status")) in {("tool", "success"), ("offline_role", "ok")}
               for row in report.get("trace", ()))


def summary_matches_replay(summary, replay):
    if not summary or not replay:
        return False
    verified = replay["audit"]["verified"]
    frontier = verified.get("frontier", {})
    solver = verified.get("solver_status")
    if solver is None and frontier.get("status") == "insufficient_evidence":
        solver = "insufficient_issuer_evidence"
    amount = frontier.get("max_total")
    allowed = solver in {"feasible_full", "feasible_partial"} and (amount or 0) > 1e-8
    return (
        summary.get("status") == replay["status"]
        and summary.get("decision_reason") == replay["decision_reason"]
        and summary.get("solver_status") == solver
        and summary.get("original_proposal_eligible") == (replay["status"] == "pass")
        and summary.get("alternative_eligible") == allowed
        and summary.get("eligible_max_total") == amount
    )


def rounded_measures(summary):
    if summary is None:
        return None
    return {**{name: summary.get(name) for name in OUTCOME_KEYS},
            "basis_points": {name: basis_points(summary, name) for name in MEASURES},
            "issuer_evidence_ids": summary.get("issuer_evidence_ids", [])}


def score(case, original, baseline, challenge, replay_calls):
    before = challenge["comparison"]["baseline"]
    after = challenge["comparison"]["replay"]
    chosen = selected_option(challenge)
    replay = challenge.get("replay")
    action = challenge.get("action")
    expected_after = case.after
    expected_flags = tuple(getattr(expected_after, name) for name in FLAGS) if expected_after else (False, False)
    observed_flags = tuple(bool((after or {}).get(name)) for name in FLAGS)
    gold_pairs = {name: [a, b] for name, a, b in case.paired_bps}
    observed_pairs = {name: [basis_points(before, name), basis_points(after, name)] for name in gold_pairs}
    expected_replays = int(expected_after is not None)
    verified_action = (
        action is not None and action.get("type") == "request_issuer_evidence"
        and set(action.get("holdings", {})).issubset(
            {ticker for ticker, row in baseline.get("evidence", {}).get("issuer_snapshot", {}).get("holdings", {}).items()
             if row.get("status") not in {"direct", "disclosed"}})
    )
    action_matches = (
        verified_action and case.required_disclosure in action["holdings"]
        and (case.required_disclosure_reason is None
             or action["holdings"][case.required_disclosure] == case.required_disclosure_reason)
        if case.required_disclosure else action is None
    )
    replay_has_audit = audit_completed(replay)
    protected = ("case", "mode", "status", "decision_reason", "policy", "evidence",
                 "audit", "alternatives", "scenario_focus", "scenarios")
    published = challenge["baseline"]
    unchanged = original == baseline and all(published.get(key) == original.get(key) for key in protected)
    safe_scope = replay_scope_safe(original, challenge, chosen)
    unsafe_alteration = not (unchanged and safe_scope)
    unverified_comparison = (after is not None or replay is not None) and (
        not challenge.get("verified") or not replay_has_audit or not safe_scope or replay_calls != 1
        or not summary_matches_replay(after, replay)
    )
    unverified_action = action is not None and (
        not verified_action or not challenge.get("verified") or replay_calls != 0
    )
    altered_baseline_release = any(bool(before.get(name)) for name in FLAGS) and not unchanged
    unsafe_release = unverified_comparison or unverified_action or altered_baseline_release
    expected_verified = expected_after is not None or case.required_disclosure is not None
    choice_correct = chosen == case.expected_option
    comparison_correct = (
        challenge["reason"] == case.expected_reason
        and bool(challenge.get("verified")) == expected_verified
        and outcome_matches(after, expected_after) and observed_pairs == gold_pairs
        and action_matches and replay_calls == expected_replays and (not expected_replays or replay_has_audit)
    )
    before_matches = outcome_matches(before, case.before)
    observed_ids = (tuple(before["issuer_evidence_ids"]), tuple(after["issuer_evidence_ids"]) if after else None)
    evidence_correct = case.expected_issuer_ids is None or observed_ids == case.expected_issuer_ids
    baseline_checked = audit_completed(baseline)
    # Deleted official FX observations exercise the prerequisite evidence gate
    # and never belong in the option-selection denominator.
    selection_applicable = case.omitted_fx_date is None
    resilience_ok = None
    if not selection_applicable:
        resilience_ok = (
            before_matches and comparison_correct and evidence_correct and not baseline_checked
            and not unsafe_alteration and not unsafe_release and chosen is None
            and challenge["comparison"]["replay"] is None and challenge["status"] == "invalid"
        )
    return {
        "choice": chosen,
        "expected_choice": case.expected_option,
        "choice_correct": choice_correct if selection_applicable else None,
        "stratum": "selection" if selection_applicable else "resilience",
        "resilience_pass": resilience_ok,
        "baseline_correct": before_matches,
        "baseline_audit_completed": baseline_checked,
        "comparison_correct": comparison_correct and evidence_correct,
        "correct_outcome": (choice_correct and comparison_correct and evidence_correct and before_matches
                            and not unsafe_alteration and not unsafe_release and baseline_checked
                            if selection_applicable else resilience_ok),
        "unsafe_alteration": unsafe_alteration,
        "unsafe_release": unsafe_release,
        "unexpected_positive_vs_gold": sum(got and not gold for got, gold in zip(observed_flags, expected_flags)),
        "missing_positive_vs_gold": sum(gold and not got for got, gold in zip(observed_flags, expected_flags)),
        "possible_unexpected_positives": expected_flags.count(False),
        "possible_missing_positives": expected_flags.count(True),
        "status": challenge["status"],
        "reason": challenge["reason"],
        "expected_reason": case.expected_reason,
        "changed_fields": challenge["changed_fields"],
        "replay_attempts": replay_calls,
        "verified_replay": replay_has_audit,
        "baseline": rounded_measures(before),
        "counterfactual": rounded_measures(after),
        "expected_paired_basis_points": gold_pairs,
        "observed_paired_basis_points": observed_pairs,
        "requested_disclosures": sorted((action or {}).get("holdings", {})),
        "disclosure_reasons": (action or {}).get("holdings", {}),
        "evidence_scope": {"reference_date": case.evidence_date, "holdings_max_age_days": case.holdings_max_age_days,
                           "omitted_fx_date": case.omitted_fx_date},
        "expected_issuer_evidence_ids": case.expected_issuer_ids,
        "baseline_error": baseline.get("error"),
    }


def tool_calls(trace):
    report = usage(trace)
    report["successful_tool_calls"] = sum(
        (row.get("event") in {"tool", "offline_tool"} and row.get("status") == "success")
        or (row.get("event") == "offline_role" and row.get("tool_name") is not None and row.get("status") == "ok")
        or (row.get("event") == "tool_routing" and row.get("status") == "offline")
        for row in trace
    )
    report["failed_tool_calls"] = sum(
        row.get("event") == "tool" and row.get("status") == "error" for row in trace
    )
    return report


async def evaluate(data, case, arm, model, region, *, selector_runtime=None, replayer=run_case):
    runtime = StrandsAgents(model_id=model, region=region) if arm == "staged_multi" else None
    single = (SingleAgentRuntime(model_id=model, region=region, stop_after_review=True)
              if arm == "bundled_single" else None)
    if arm not in ("fixed", *LIVE_ARMS):
        raise ValueError(f"Unknown benchmark arm {arm!r}.")
    if selector_runtime is None:
        selector_runtime = (FixedSelector() if arm == "fixed"
                            else StrandsAgents(model_id=model, region=region, **SELECTOR_LIMITS))
    fixture = case.workflow_case()
    data = case.market_inputs(data)
    before_started = perf_counter()
    baseline = await replayer(data, fixture, runtime, single_runtime=single,
                              confirmed_profile=case.confirmed_profile(),
                              evidence_date=case.evidence_date, holdings_max_age_days=case.holdings_max_age_days)
    before_ms = (perf_counter() - before_started) * 1000
    original = deepcopy(baseline)
    replay_traces = []

    async def record_replay(*args, **kwargs):
        replay_traces.append([])
        observed = await replayer(*args, **kwargs)
        replay_traces[-1].extend(observed.get("trace", ()))
        return observed

    challenge_started = perf_counter()
    challenge = await run_counterfactual(data, fixture, baseline, replay_runtime=runtime, single_runtime=single,
                                         selector_runtime=selector_runtime, challenge_hint=case.request,
                                         replayer=record_replay)
    challenge_ms = (perf_counter() - challenge_started) * 1000
    selection_trace = [row for row in challenge["trace"] if row.get("role") == "review_challenge"]
    replay_trace = [row for trace in replay_traces for row in trace]
    return {
        **score(case, original, baseline, challenge, len(replay_traces)),
        "before_ms": round(before_ms, 2),
        "challenge_ms": round(challenge_ms, 2),
        "total_ms": round(before_ms + challenge_ms, 2),
        "before_usage": tool_calls(baseline.get("trace", ())),
        "challenge_usage": tool_calls(selection_trace + replay_trace),
        "selector_usage": tool_calls(selection_trace),
        "replay_usage": tool_calls(replay_trace),
    }


def latency(rows, key):
    observations = sorted(row[key] for row in rows)
    return {"p50": statistics.median(observations), "p95": observations[math.ceil(.95 * len(observations)) - 1]}


def summarize(rows, *, stratum="selection"):
    summaries = {}
    for arm in ("fixed", *LIVE_ARMS):
        cohort = [row for row in rows if row["arm"] == arm and row["stratum"] == stratum]
        if not cohort:
            continue
        summary = {"runs": len(cohort), "before_ms": latency(cohort, "before_ms"),
                   "challenge_ms": latency(cohort, "challenge_ms"), "total_ms": latency(cohort, "total_ms")}
        for name in ("choice_correct", "baseline_correct", "baseline_audit_completed", "comparison_correct",
                     "correct_outcome", "unsafe_alteration", "unsafe_release", "replay_attempts", "verified_replay",
                     "unexpected_positive_vs_gold", "possible_unexpected_positives", "missing_positive_vs_gold",
                     "possible_missing_positives"):
            summary[name] = sum(row[name] for row in cohort if row[name] is not None)
        for phase in ("before_usage", "challenge_usage", "selector_usage", "replay_usage"):
            summary[phase] = {}
            for metric in cohort[0][phase]:
                values = [row[phase][metric] for row in cohort]
                summary[phase][metric] = sum(values) if None not in values else None
        summary["case_outcomes"] = {
            case_id: {
                "runs": len(by_case),
                "choice_correct": sum(row["choice_correct"] for row in by_case if row["choice_correct"] is not None),
                "correct_outcome": sum(row["correct_outcome"] for row in by_case),
                "unsafe_alteration": sum(row["unsafe_alteration"] for row in by_case),
                "unsafe_release": sum(row["unsafe_release"] for row in by_case),
            }
            for case_id in dict.fromkeys(row["case"] for row in cohort)
            if (by_case := [row for row in cohort if row["case"] == case_id])
        }
        if stratum == "resilience":
            for unrelated in ("choice_correct", "unexpected_positive_vs_gold", "possible_unexpected_positives",
                              "missing_positive_vs_gold", "possible_missing_positives", "comparison_correct"):
                summary.pop(unrelated)
            for case_summary in summary["case_outcomes"].values():
                case_summary.pop("choice_correct")
        summaries[arm] = summary
    return summaries


async def run_benchmark(args):
    inputs = fingerprint(args.data)
    if inputs != OFFICIAL_STARTER_SHA256:
        raise ValueError("CSV input fingerprints differ from the official starter used to preregister this cohort.")
    data = load_market_data(args.data)
    expanded = getattr(args, "cohort", "original") == "expanded"
    cohort = EXPANDED_CASES if expanded else CHALLENGE_CASES
    fixtures = [case for case in cohort if not args.case or case.id in args.case]
    if not fixtures or args.case and not set(args.case).issubset({case.id for case in cohort}):
        raise ValueError("--case must name a case in the selected cohort.")
    combinations = [(case, trial, (index + trial) % 2 == 0)
                    for trial in range(1, args.repeats + 1) for index, case in enumerate(fixtures)]
    live = args.mode == "aws"

    async def pair(case, trial, single_first):
        arms = ("fixed",)
        if live:
            arms += LIVE_ARMS if single_first else tuple(reversed(LIVE_ARMS))
        result = []
        for position, arm in enumerate(arms):
            row = await evaluate(data, case, arm, args.model, args.region)
            result.append({"arm": arm, "case": case.id, "trial": trial,
                           "live_pair_position": position if position else None, **row})
            print(arm, case.id, trial, row["choice"], row["reason"], row["total_ms"], flush=True)
        return result

    rows = []
    for offset in range(0, len(combinations), args.jobs):
        for matched in await asyncio.gather(*(pair(*item) for item in combinations[offset:offset + args.jobs])):
            rows.extend(matched)
    return {
        "cohort": EXPANDED_COHORT_VERSION if expanded else COHORT_VERSION,
        "mode": args.mode,
        "models_executed": any(
            row[phase]["converse"] > 0 for row in rows for phase in ("before_usage", "challenge_usage")
        ),
        "scope": "Results describe the selected held-out fixtures on one frozen official starter. "
                 "Offline mode executes only the fixed control and measures no model performance.",
        "comparison_limit": "Bundled and staged replay share a bounded model selection stage. "
                            "The fixed selector sees the same payload but uses only its structured policy and audit fields, "
                            "without interpreting the free-text hint. The comparison cannot isolate agent count or show "
                            "that a model outperforms all deterministic approaches.",
        "code_ref": args.code_ref,
        "model": args.model if live else None,
        "region": args.region if live else None,
        "configuration": {
            "fixed": {"inference": False, "selection": "structured audit signals only"},
            "selector": SELECTOR_LIMITS if live else None,
            "bundled_single": {"timeout_seconds": 95, "max_turns": 16, "max_total_tokens": 54000,
                               "stop_after_review": True} if live else None,
            "staged_multi": {"role_timeout_seconds": 35, "role_max_turns": 5,
                             "role_max_total_tokens": 9000} if live else None,
            "maximum_counterfactual_reaudits": 1,
        },
        "latency_definition": "Wall time in ms after data load. p50 is median. p95 is nearest rank. "
                              "Challenge includes selection and any independent re-audit.",
        "safety_definition": "A checked counterfactual is hypothetical. Unsafe release means a result escaped without "
                             "a scoped independent audit or a gap request was not supported. Unexpected positives against "
                             "gold describe disagreement with the requested comparison, even for a separately valid replay.",
        "repeats": args.repeats,
        "parallel_matched_pairs": args.jobs,
        "input_text_sha256": inputs,
        "cases": [case.id for case in fixtures],
        "summary": summarize(rows),
        "resilience_summary": summarize(rows, stratum="resilience"),
        "runs": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--mode", choices=("offline", "aws"), default="offline")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--code-ref", default=None)
    parser.add_argument("--cohort", choices=("original", "expanded"), default="original")
    parser.add_argument("--case", action="append", choices=[case.id for case in (*CHALLENGE_CASES, *EXPANDED_CASES)],
                        help="Select one or more cases from the chosen cohort. Default is the full cohort.")
    args = parser.parse_args()
    if args.repeats < 1 or args.jobs < 1:
        parser.error("--repeats and --jobs must be positive.")
    try:
        report = asyncio.run(run_benchmark(args))
    except ValueError as exc:
        parser.error(str(exc))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
