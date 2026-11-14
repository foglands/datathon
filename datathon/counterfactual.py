"""Select a bounded one-rule challenge and independently replay the portfolio."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from math import fsum, isclose
from time import perf_counter
from typing import Literal
from uuid import uuid4

from .agents import AgentRun, ToolSpec
from .evidence import DEFAULT_HOLDINGS_MAX_AGE_DAYS
from .workflow import profile_policy, run_case


Choice = Literal[
    "toggle_loss_metric", "tighten_reserve_floor", "toggle_purchase_size",
    "tighten_holdings_age", "request_issuer_evidence", "no_material_challenge",
]
EPSILON = 1e-8
CONTEXT_ONLY = {"selected_loss_metric", "proposal_loss_headroom", "proposal_reserve_headroom"}


@dataclass(frozen=True)
class ChallengeOption:
    id: str
    label: str
    field: str | None
    before: float | int | str | bool | None
    after: float | int | str | bool | None
    trigger: str
    action: bool = False
    value_unit: Literal["basis_points", "days"] | None = None
    minimum_value: int | None = None
    maximum_value: int | None = None
    preset_value: int | None = None


def _threshold_label(field, after):
    if field == "reserve_floor":
        return f"Raise the ZST.TO floor to {after:.2%}"
    return f"Use a {after}-day holdings freshness limit"


def _checked(report):
    if report.get("status") not in {"pass", "fail", "insufficient_evidence"} or not report.get("policy"):
        return False
    audit = report.get("audit", {})
    verified = audit.get("verified", {})
    return (report.get("status") == audit.get("status") and
            report.get("decision_reason") == audit.get("decision_reason") and
            bool(verified.get("proposal", {}).get("windows")))


def _evidence_snapshot(report):
    return report.get("evidence", {}).get("issuer_snapshot", {})


def _missing_issuer_evidence(report):
    snapshot = _evidence_snapshot(report)
    unavailable = {}
    portfolios = report["audit"]["verified"]
    for ticker, row in snapshot.get("holdings", {}).items():
        if row.get("status") in {"disclosed", "direct"}:
            continue
        if any(leg.get("weights", {}).get(ticker, 0) > EPSILON
               for leg in (portfolios.get("baseline", {}), portfolios.get("proposal", {}))):
            unavailable[ticker] = row.get("reason") or "missing_holding_disclosure"
    return unavailable


def _bounds_for(weights, holdings):
    unknown = {ticker: weight for ticker, weight in weights.items()
               if weight > 0 and holdings.get(ticker, {}).get("status") not in {"disclosed", "direct"}}
    lower = fsum(
        weight * holdings[ticker]["weight"] for ticker, weight in weights.items()
        if holdings.get(ticker, {}).get("status") in {"disclosed", "direct"}
    )
    return {"lower": lower, "upper": min(1.0, lower + fsum(unknown.values()))}, unknown


def _issuer_thresholds(report):
    policy = report["policy"]
    cap = policy["issuer_cap"]
    holdings = _evidence_snapshot(report).get("holdings", {})
    verified = report["audit"]["verified"]
    findings = {item["metric_id"]: item for item in report["audit"]["findings"]}
    thresholds = {}

    def threshold(bounds, unknown, basis):
        headroom = cap - bounds["lower"]
        status = "breach" if headroom < -EPSILON else "within_cap" if bounds["upper"] <= cap + EPSILON else "unresolved"
        return {
            "known_lower": bounds["lower"], "potential_upper": bounds["upper"],
            "maximum_combined_additional_exposure": max(0.0, headroom) if status != "breach" else None,
            "unknown_holdings": unknown, "issuer_cap": cap, "status": status, "basis": basis,
        }

    for name in ("baseline", "proposal"):
        finding = findings.get(f"{name}.issuer_weight.policy")
        if not finding or not _same_value(cap, finding.get("limit")):
            return {}
        audited = finding.get("actual", {})
        bounds, unknown = _bounds_for(verified[name]["weights"], holdings)
        if not all(_same_value(value, audited.get(key)) for key, value in bounds.items()):
            return {}
        thresholds[name] = threshold(audited, unknown, "independent_audit")

    base = verified["baseline"]["weights"]
    target = policy["target"]
    if "QQQ" in policy["allowed_sources"] and target <= base["QQQ"]:
        weights = {**base, "QQQ": base["QQQ"] - target, "NVDA": base["NVDA"] + target}
        bounds, unknown = _bounds_for(weights, holdings)
        thresholds["qqq_only"] = threshold(bounds, unknown, "derived_from_verified_baseline_and_qualified_disclosures")
    return thresholds


def _holds_context(report):
    snapshot = _evidence_snapshot(report)
    return {
        "evidence_date": snapshot.get("reference_date", "2026-11-14"),
        "holdings_max_age_days": snapshot.get("max_age_days", DEFAULT_HOLDINGS_MAX_AGE_DAYS),
    }


def counterfactual_options(report):
    """Return the bounded actions applicable to an independently audited report."""
    if not _checked(report):
        return ()
    policy = report["policy"]
    options = []
    if policy.get("loss_limit") is not None:
        metric = policy["metric"]
        other = "max_drawdown" if metric == "terminal_loss" else "terminal_loss"
        label = "Maximum drawdown" if other == "max_drawdown" else "Terminal loss"
        options.append(ChallengeOption("toggle_loss_metric", f"Measure the loss cap as {label.lower()}",
                                       "metric", metric, other, "confirmed_historical_loss_cap"))
    floor = policy["reserve_floor"]
    if 0 < floor < 1:
        floor_bps = round(floor * 10000)
        preset_bps = min(10000, floor_bps + 300)
        tightened = preset_bps / 10000
        options.append(ChallengeOption(
            "tighten_reserve_floor", _threshold_label("reserve_floor", tightened),
            "reserve_floor", floor, tightened, "confirmed_positive_reserve_floor",
            value_unit="basis_points", minimum_value=floor_bps + 1, maximum_value=10000, preset_value=preset_bps,
        ))
    if policy["target"] > 0:
        smaller = policy["allow_smaller"]
        label = "Require the exact purchase size" if smaller else "Allow a smaller purchase"
        options.append(ChallengeOption("toggle_purchase_size", label, "allow_smaller", smaller, not smaller,
                                       "confirmed_purchase_size_policy"))
    if policy.get("issuer_cap") is not None:
        snapshot = _evidence_snapshot(report)
        age = snapshot.get("max_age_days")
        if type(age) is int and age > 0 and any(
            row.get("status") == "disclosed" for row in snapshot.get("holdings", {}).values()
        ):
            tightened = min(90, age - 1)
            options.append(ChallengeOption(
                "tighten_holdings_age", _threshold_label("holdings_max_age_days", tightened),
                "holdings_max_age_days", age, tightened, "current_dated_issuer_disclosures",
                value_unit="days", minimum_value=0, maximum_value=age - 1, preset_value=tightened,
            ))
        if _missing_issuer_evidence(report):
            options.append(ChallengeOption("request_issuer_evidence", "Identify required issuer disclosures", None,
                                           None, None, "unresolved_issuer_coverage", action=True))
    return tuple(options)


def _profile(policy):
    """Recreate the confirmed structured profile without running natural language intake."""
    metric = policy.get("metric") if policy.get("loss_limit") is not None else None

    def bps(name):
        value = policy.get(name)
        return round(value * 10000) if value is not None else None

    return {
        "status": "ok",
        "summary": "Confirmed one-rule counterfactual",
        "evidence_ids": [],
        "metric": metric,
        "limit_bps": bps("loss_limit"),
        "target_bps": bps("target"),
        "reserve_floor_bps": bps("reserve_floor"),
        "issuer_cap_bps": bps("issuer_cap"),
        "initial_source": policy["initial_source"],
        "allowed_sources": list(policy["allowed_sources"]),
        "allow_smaller": policy["allow_smaller"],
        "prefer_reserve": policy["prefer_reserve"],
    }


def _summary(report):
    audit = report.get("audit", {})
    verified = audit.get("verified", {})
    frontier = verified.get("frontier", {})
    alternative = report.get("alternatives", {})
    proposal = verified.get("proposal", {})
    baseline = verified.get("baseline", {})
    issuer = next((item.get("actual") for item in audit.get("findings", ())
                   if item["metric_id"] == "proposal.issuer_weight.policy"), None)
    solver_status = verified.get("solver_status")
    if solver_status is None and frontier.get("status") == "insufficient_evidence":
        solver_status = "insufficient_issuer_evidence"
    eligible_size = frontier.get("max_total")
    binding = alternative.get("frontier", {}).get("full_zst_max_binding")
    policy = report.get("policy", {})
    loss_limit = policy.get("loss_limit")
    selected_loss = proposal.get(policy.get("metric"))
    reserve = proposal.get("weights", {}).get("ZST.TO")
    return {
        "status": report.get("status"),
        "decision_reason": report.get("decision_reason"),
        "baseline_status": baseline.get("status"),
        "solver_status": solver_status,
        "original_proposal_eligible": report.get("status") == "pass",
        "alternative_eligible": solver_status in {"feasible_full", "feasible_partial"} and (eligible_size or 0) > EPSILON,
        "eligible_max_total": eligible_size,
        "diagnostic_max_total": frontier.get("diagnostic_max_total"),
        "full_zst_min": frontier.get("full_zst_min"),
        "full_zst_max": frontier.get("full_zst_max"),
        "full_zst_max_binding": binding if frontier.get("full_possible") else None,
        "selected_loss_metric": policy.get("metric") if loss_limit is not None else None,
        "proposal_loss_headroom": loss_limit - selected_loss if loss_limit is not None and selected_loss is not None else None,
        "proposal_reserve_headroom": reserve - policy["reserve_floor"] if reserve is not None else None,
        "proposal_terminal_loss": proposal.get("terminal_loss"),
        "proposal_max_drawdown": proposal.get("max_drawdown"),
        "proposal_issuer_lower": issuer.get("lower") if isinstance(issuer, Mapping) else None,
        "proposal_issuer_upper": issuer.get("upper") if isinstance(issuer, Mapping) else None,
        "issuer_evidence_ids": sorted(source for source in report.get("evidence", {}).get("evidence_ids", ())
                                      if source.startswith("issuer:")),
    }


def _same_value(before, after):
    if type(before) in {int, float} and type(after) in {int, float}:
        return isclose(before, after, rel_tol=0, abs_tol=EPSILON)
    return before == after


def _comparison(before, after):
    changed = {key: {"before": value, "after": after[key]} for key, value in before.items()
               if not _same_value(value, after[key])}
    return {
        "baseline": before, "replay": after,
        "differences": changed,
        "material_differences": [key for key in changed if key not in CONTEXT_ONLY],
    }


def _unchanged_replay_inputs(baseline, replay):
    first = baseline["audit"]["verified"]
    second = replay["audit"]["verified"]
    evidence = baseline.get("evidence", {})
    new_evidence = replay.get("evidence", {})
    if any(evidence.get(key) != new_evidence.get(key) for key in ("basis", "price_source", "fx_source", "windows")):
        return False
    # The two market paths and evaluations must stay identical under a policy-only change.
    return all(
        first[leg][key] == second[leg][key]
        for leg in ("baseline", "proposal") for key in ("weights", "windows")
    )


def _replay_matches(baseline, replay, option, expected_policy, expected_context):
    if not _checked(replay) or replay.get("policy") != expected_policy:
        return False
    if not _unchanged_replay_inputs(baseline, replay):
        return False
    before = _evidence_snapshot(baseline)
    after = _evidence_snapshot(replay)
    if option.field == "holdings_max_age_days":
        return (bool(before) and bool(after) and
                after.get("reference_date") == expected_context["evidence_date"] and
                after.get("publication_cutoff") == before.get("publication_cutoff") and
                after.get("as_of") == before.get("as_of") and
                after.get("max_age_days") == expected_context["holdings_max_age_days"] and
                _same_issuer_records(before, after))
    return (before == after and baseline["evidence"].get("evidence_ids") == replay["evidence"].get("evidence_ids"))


def _same_issuer_records(before, after):
    fields = ("as_of", "published_on", "url", "source", "reported_status", "reported_weight")
    return (
        all(before.get(key) == after.get(key) for key in ("issuer", "issuer_id", "scope")) and
        before["holdings"].keys() == after["holdings"].keys() and
        all(all(original.get(field) == after["holdings"][ticker].get(field) for field in fields)
            for ticker, original in before["holdings"].items())
    )


def _public_trace(trace):
    fields = {
        "role", "event", "run_id", "tool_name", "status", "mode", "option_id", "field", "duration_ms",
        "operation", "model_id", "region", "request_id", "http_status", "input_tokens", "output_tokens",
        "total_tokens", "cache_read_input_tokens", "cache_write_input_tokens", "threshold_value", "threshold_unit",
    }
    return [{key: value for key, value in event.items() if key in fields} for event in trace]


def _public_report(report):
    if report is None:
        return None
    fields = {"case", "mode", "status", "decision_reason", "policy", "evidence", "exposure",
              "scenarios", "scenario_focus", "alternatives", "audit", "elapsed_ms"}
    return {**{key: value for key, value in report.items() if key in fields},
            "trace": _public_trace(report.get("trace", ()))}


async def run_counterfactual(
    data, case, baseline_report, *, option_id=None, selector_runtime=None, replay_runtime=None,
    single_runtime=None, replayer=run_case, challenge_hint=None, challenge_value=None,
):
    """Choose one challenge and verify it, optionally with a user-confirmed integer threshold."""
    started = perf_counter()
    baseline = deepcopy(baseline_report)
    options = {option.id: option for option in counterfactual_options(baseline)}
    trace = []
    before = _summary(baseline)
    replay = None
    option = None
    accepted_value = None
    selection_mode = "user" if option_id is not None else "agent" if selector_runtime is not None else "deterministic"
    run_id = f"{case.id}-challenge-{uuid4().hex[:12]}"

    def result(status, reason, statement, *, verified=False, action=None):
        return {
            "status": status, "reason": reason, "verified": verified, "statement": statement,
            "selection_mode": selection_mode, "baseline": _public_report(baseline),
            "replay": _public_report(replay) if verified else None,
            "option": asdict(option) if option else None, "action": action, "trace": _public_trace(trace),
            "confirmed_threshold": accepted_value,
            "elapsed_ms": round((perf_counter() - started) * 1000),
            "changed_fields": [option.field] if option and option.field and verified else [],
            "comparison": _comparison(before, _summary(replay)) if replay and verified else
                          {"baseline": before, "replay": None, "differences": {}, "material_differences": []},
        }

    if not _checked(baseline):
        return result("invalid", "baseline_not_verified", "An independently reviewed starting audit is required.")
    if challenge_value is not None:
        selected = options.get(option_id) if isinstance(option_id, str) else None
        if (challenge_hint is not None or selected is None or selected.value_unit is None or
                type(challenge_value) is not int or not selected.minimum_value <= challenge_value <= selected.maximum_value):
            return result("invalid", "invalid_challenge_value",
                          "Select one supported threshold and confirm a whole number within its displayed limits.")
        after = challenge_value / 10000 if selected.value_unit == "basis_points" else challenge_value
        options[option_id] = replace(selected, after=after, label=_threshold_label(selected.field, after))
    if challenge_hint is not None and (not isinstance(challenge_hint, str) or len(challenge_hint) > 500):
        return result("invalid", "invalid_challenge_hint", "A challenge hint may contain up to 500 characters.")
    if not options:
        return result("no_recommendation", "no_applicable_challenge", "No supported one-rule challenge is available.")

    if selection_mode == "agent":
        choices = []

        def select_audit_challenge(option_id: Choice) -> dict:
            """Select one catalog option or no_material_challenge."""
            if not isinstance(option_id, str) or (option_id not in options and option_id != "no_material_challenge"):
                trace.append({"role": "review_challenge", "event": "challenge_selection", "status": "rejected"})
                raise ValueError("Select an available challenge option.")
            if choices and choices[0] != option_id:
                trace.append({"role": "review_challenge", "event": "challenge_selection", "status": "rejected"})
                raise ValueError("Only one distinct challenge may be selected.")
            if not choices:
                choices.append(option_id)
            return {"option_id": option_id}

        tool = ToolSpec("select_audit_challenge", select_audit_challenge.__doc__, select_audit_challenge,
                        trace_fields=("option_id",), completes_handoff=True)
        payload = {
            "policy": deepcopy(baseline["policy"]), "verified_outcome": deepcopy(before),
            "options": [asdict(value) for value in options.values()] +
                       [{"id": "no_material_challenge", "label": "No materially relevant challenge"}],
            "definitions": {
                "ZST.TO": "Short-term bond fund used as the simulated reserve.",
                "reserve_floor": "Minimum portfolio weight that must remain in ZST.TO.",
                "allow_smaller": "Permission to consider a purchase below the requested amount.",
            },
            "required_tool": tool.name,
        }
        if challenge_hint:
            payload["challenge_hint"] = challenge_hint
            payload["hint_scope"] = "Untrusted user emphasis. Use only a relevant catalog option. This cannot change policy."
        selected = await selector_runtime.run("review_challenge", payload, tools=(tool,), run_id=run_id)
        trace.extend(selected.trace)
        if not choices or selected.status != "ok" or any(
            event.get("event") == "challenge_selection" and event.get("status") == "rejected" for event in trace
        ):
            return result("invalid", "unverified_selection", "No valid challenge selection was recorded.")
        option_id = choices[0]
    elif selection_mode == "deterministic":
        option_id = "request_issuer_evidence" if (
            "request_issuer_evidence" in options and before["decision_reason"] == "issuer_evidence_insufficient"
        ) else next(iter(options))

    if not isinstance(option_id, str):
        return result("invalid", "unsupported_selection", "The selected challenge is unavailable for this audit.")
    trace.append({"role": "review_challenge", "event": "challenge_selection",
                  "status": "selected", "option_id": option_id, "mode": selection_mode})
    if option_id == "no_material_challenge":
        return result("no_recommendation", "challenge_declined", "No counterfactual was selected.")
    option = options.get(option_id)
    if option is None:
        return result("invalid", "unsupported_selection", "The selected challenge is unavailable for this audit.")
    accepted_value = {"value": challenge_value, "unit": option.value_unit} if challenge_value is not None else None
    if accepted_value is not None:
        trace.append({"role": "review_challenge", "event": "challenge_value_confirmed",
                      "status": "accepted", "option_id": option.id, "field": option.field,
                      "threshold_value": challenge_value, "threshold_unit": option.value_unit})
    if option.action:
        if before["decision_reason"] != "issuer_evidence_insufficient":
            return result("no_recommendation", "issuer_evidence_not_binding",
                          "Additional issuer evidence did not limit the audited decision.")
        thresholds = _issuer_thresholds(baseline)
        if not thresholds:
            return result("invalid", "issuer_evidence_not_verified",
                          "The available audit does not reconcile with the issuer disclosure evidence.")
        action = {
            "type": "request_issuer_evidence",
            "holdings": _missing_issuer_evidence(baseline),
            "required_fields": ["issuer_id", "weight", "observation_date", "publication_date", "issuer_disclosure_url"],
            "reference_date": _holds_context(baseline)["evidence_date"],
            "thresholds": thresholds,
        }
        return result("no_recommendation", "issuer_evidence_required",
                      "A qualified disclosure is needed before checking the unresolved issuer constraint.",
                      verified=True, action=action)

    policy = dict(baseline["policy"])
    context = _holds_context(baseline)
    if option.field == "holdings_max_age_days":
        context[option.field] = option.after
    else:
        policy[option.field] = option.after
    profile = _profile(policy)
    if profile_policy(profile) != policy:
        return result("invalid", "policy_changed_during_compilation", "The proposed change could not be isolated.")
    replay_case = replace(case, id=run_id)
    trace.append({"role": "review_challenge", "event": "challenge_replay", "status": "started",
                  "option_id": option.id, "field": option.field})
    replay_options = {**context, "confirmed_profile": AgentRun("ok", profile)}
    if single_runtime is not None:
        replay_options["single_runtime"] = single_runtime
    replay = await replayer(data, replay_case, replay_runtime, **replay_options)
    if not _replay_matches(baseline, replay, option, policy, context):
        return result("invalid", "replay_not_verified", "The one-rule replay could not be independently verified.")
    trace.append({"role": "review_challenge", "event": "challenge_replay", "status": "verified",
                  "option_id": option.id, "field": option.field})
    if not _comparison(before, _summary(replay))["material_differences"]:
        return result("no_recommendation", "no_material_change",
                      "The checked change did not alter the decision, exposure bounds or eligible funding range.",
                      verified=True)
    return result("verified", "comparison_verified",
                  "The additional audit verifies what changed under this hypothetical rule.", verified=True)
