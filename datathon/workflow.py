"""Explicit handoffs for the investment simulation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Optional

from .agents import AgentRun, ToolSpec
from .data import issuer_evidence
from .evidence import DEFAULT_HOLDINGS_MAX_AGE_DAYS, validate_issuer_snapshot
from .finance import BASE_WEIGHTS, STRESS_WINDOWS, MarketEvidenceError, evaluate_portfolio, solve_funding
from .governance import audit_decision


@dataclass(frozen=True)
class Case:
    id: str
    user_request: str
    metric: str
    loss_limit: Optional[float]
    reserve_floor: float
    issuer_cap: Optional[float] = None
    missing_qqq: bool = False
    tamper: bool = False
    ambiguous: bool = False


def examples(group, stress=False):
    robert_message = (
        "I am Robert, approaching retirement in 3–5 years. In this simulation I want "
        "to add 10 percentage points of NVDA, initially funded from ZST.TO. I permit "
        "funding from QQQ or ZST.TO, allow a smaller purchase, and require at least "
        "15% in ZST.TO immediately after the trade. I prefer to preserve ZST.TO. "
    )
    amira_message = (
        "I am Amira, testing long-term growth over 15 years. I want to add 10 "
        "percentage points of NVDA, initially funded from ZST.TO. I permit QQQ or ZST.TO and allow a smaller "
        "purchase. I want a 14% maximum total NVIDIA issuer exposure, including "
        "indirect common-equity exposure. I have given no portfolio loss limit."
    )
    robert = [
        Case("robert_terminal", robert_message + "The maximum terminal loss in either historical window is 14%.", "terminal_loss", .14, .15),
        Case("robert_drawdown", robert_message + "The maximum drawdown in either historical window is 14%.", "max_drawdown", .14, .15),
    ]
    amira = [Case("amira_concentration", amira_message, "terminal_loss", None, 0, .14)]
    if stress:
        robert += [
            Case("robert_tampered", robert[0].user_request, "terminal_loss", .14, .15, tamper=True),
            Case("robert_ambiguous", robert_message + "I cannot lose more than 14%.", "terminal_loss", None, .15, ambiguous=True),
        ]
        amira.append(Case("amira_missing_qqq", amira_message, "terminal_loss", None, 0, .14, missing_qqq=True))
    if group == "robert":
        return robert
    if group == "amira":
        return amira
    return robert + amira


def preset_profile(case: Case) -> dict:
    """Return fresh form fields for a predefined simulation, in basis points."""
    return {
        "status": "needs_input" if case.ambiguous else "ok",
        "summary": "Scenario fixture",
        "evidence_ids": [],
        "metric": case.metric if case.loss_limit is not None else None,
        "limit_bps": round(case.loss_limit * 10000) if case.loss_limit is not None else None,
        "target_bps": 1000,
        "initial_source": "ZST.TO",
        "reserve_floor_bps": round(case.reserve_floor * 10000) if case.reserve_floor else None,
        "issuer_cap_bps": round(case.issuer_cap * 10000) if case.issuer_cap is not None else None,
        "allowed_sources": ["QQQ", "ZST.TO"],
        "allow_smaller": True,
        "prefer_reserve": True if case.id.startswith("robert") else None,
    }


def proposed_weights(source="ZST.TO", amount=.10):
    weights = dict(BASE_WEIGHTS)
    weights[source] -= amount
    weights["NVDA"] = weights.get("NVDA", 0) + amount
    return weights


def financial_metrics(result):
    """Keep daily arrays available to Python and out of the model prompt."""
    return {
        "weights": result["weights"],
        "windows": {
            key: {k: v for k, v in row.items() if k not in {"dates", "values", "path"}}
            for key, row in result["windows"].items()
        },
    }


def exposure_range(weights, issuer_weights):
    known = sum(weight * issuer_weights[ticker] for ticker, weight in weights.items() if issuer_weights.get(ticker) is not None)
    missing = {ticker: weight for ticker, weight in weights.items() if weight > 0 and issuer_weights.get(ticker) is None}
    return {"lower": known, "upper": min(1., known + sum(missing.values())), "unknown_weights": missing}


class RoleError(RuntimeError):
    """An agent stage did not provide the required handoff."""


def profile_policy(profile):
    """Validate a proposed profile before showing it for confirmation."""
    source = profile.get("initial_source")
    allowed = profile.get("allowed_sources", [])
    target = profile.get("target_bps")
    smaller = profile.get("allow_smaller")
    metric, limit = profile.get("metric"), profile.get("limit_bps")
    if profile.get("status") != "ok":
        raise ValueError(profile.get("summary") or "Please clarify the simulated request.")
    if type(target) is not int or not 0 < target <= 10000:
        raise ValueError("How many percentage points of NVDA do you want to add?")
    if source not in ("QQQ", "ZST.TO"):
        raise ValueError("Which fund finances the original purchase, QQQ or ZST.TO?")
    if not isinstance(allowed, (list, tuple)) or not allowed or any(t not in ("QQQ", "ZST.TO") for t in allowed):
        raise ValueError("May alternatives sell QQQ, ZST.TO, or either fund?")
    if source not in allowed:
        raise ValueError("The original source is excluded from the permitted funding sources. Which source or rule should change?")
    if target / 10000 > BASE_WEIGHTS[source] + 1e-12:
        raise ValueError(f"The proposed one-fund sale exceeds the starting {source} position. What smaller request should be evaluated?")
    if type(smaller) is not bool:
        raise ValueError("If the full purchase is infeasible, may the analysis consider a smaller purchase?")
    if (metric is None) != (limit is None) or (metric is not None and metric not in ("terminal_loss", "max_drawdown")):
        raise ValueError("Does the loss limit apply to terminal loss or maximum drawdown?")
    for field in ("limit_bps", "reserve_floor_bps", "issuer_cap_bps"):
        value = profile.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 10000):
            raise ValueError(f"Please give a percentage between 0% and 100% for {field}.")
    return {
        "initial_source": source,
        "target": target / 10000,
        "reserve_floor": (profile.get("reserve_floor_bps") or 0) / 10000,
        "allowed_sources": tuple(sorted(set(allowed))),
        "allow_smaller": smaller,
        "prefer_reserve": profile.get("prefer_reserve"),
        "loss_limit": limit / 10000 if limit is not None else None,
        "metric": metric or "terminal_loss",
        "issuer_cap": profile["issuer_cap_bps"] / 10000 if profile.get("issuer_cap_bps") is not None else None,
    }


async def interpret_request(request, runtime, run_id):
    """Extract an editable policy. Only confirmed drafts should be replayed."""
    parsed = await runtime.run("profile", {"user_request": request}, run_id=run_id)
    if parsed.status == "error":
        return parsed, None, f"Profile interpretation failed: {parsed.stop_reason}."
    if parsed.status != "ok":
        return parsed, None, parsed.data.get("summary") or "Please clarify the simulated request."
    try:
        return parsed, profile_policy(parsed.data), None
    except ValueError as exc:
        return parsed, None, str(exc)


async def run_case(
    data, case, runtime=None, *, confirmed_profile: AgentRun | None = None,
    evidence_date: str = "2026-11-14", holdings_max_age_days: int = DEFAULT_HOLDINGS_MAX_AGE_DAYS,
    single_runtime=None,
):
    """Audit the frozen market replay and qualify issuer data as of the evidence date."""
    started = perf_counter()
    trace = []
    outputs = {}

    async def role(name, payload, *, tool_name=None, operation=None, offline=None):
        calls = []

        def handler() -> dict:
            """Run the authorized operation for this case using frozen inputs."""
            if not calls:
                calls.append(operation())
            return calls[0]

        if runtime is None:
            if operation is not None:
                handler()
            supplied = offline or {"status": "ok", "summary": "Local role simulation", "evidence_ids": []}
            trace.append({"role": name, "event": "offline_role", "tool_name": tool_name, "status": supplied["status"]})
        else:
            specs = (ToolSpec(tool_name, handler.__doc__.strip(), handler),) if tool_name else ()
            result = await runtime.run(name, {**payload, "required_tool": tool_name}, tools=specs, run_id=case.id)
            trace.extend({"role": name, **event} for event in result.trace)
            supplied = result.data
            if result.status == "error" or not supplied:
                raise RoleError(f"{name}: {result.stop_reason}")
            if operation is not None and not calls:
                raise RoleError(f"{name}: required tool {tool_name} did not run")
        outputs[name] = supplied
        return calls[0] if calls else supplied

    async def routed_role(name, payload, tool, expected, operation, output):
        if runtime is None:
            trace.append({"role": name, "event": "tool_routing", "tool_name": tool.name,
                          "status": "offline", "arguments": expected})
            outputs[name] = {"status": "ok", "summary": "Local policy routing", "evidence_ids": []}
            operation(**expected)
            return
        result = await runtime.run(name, {**payload, "required_tool": tool.name}, tools=(tool,), run_id=case.id)
        trace.extend({"role": name, **event} for event in result.trace)
        if result.status in ("ok", "insufficient_evidence") and result.data and output:
            outputs[name] = result.data
            return
        trace.append({"role": name, "event": "tool_routing", "tool_name": tool.name,
                      "status": "deterministic_fallback", "arguments": expected,
                      "reason": result.stop_reason if result.status == "error" else "missing_checked_handoff"})
        outputs[name] = {"status": "fallback", "summary": "Python applied the confirmed policy.",
                         "evidence_ids": []}
        operation(**expected)

    def route(name, tool_name, submitted, expected, operation):
        # Only successful, policy-checked arguments enter the audit record.
        invalid = [key for key, value in submitted.items()
                   if (sorted(value) if isinstance(value, list) and all(isinstance(x, str) for x in value) else value)
                   != (sorted(expected[key]) if isinstance(expected[key], list) else expected[key])]
        if invalid:
            trace.append({"role": name, "event": "tool_routing", "tool_name": tool_name,
                          "status": "rejected", "invalid_fields": invalid})
            raise ValueError("Tool arguments must match the confirmed policy and complete available source set: "
                             + ", ".join(invalid))
        answer = operation(**submitted)
        trace.append({"role": name, "event": "tool_routing", "tool_name": tool_name,
                      "status": "accepted", "arguments": submitted})
        return answer

    if single_runtime is not None and (runtime is not None or confirmed_profile is None):
        raise ValueError("The single-agent benchmark requires a confirmed profile and its own runtime.")
    result = {"case": case.id, "mode": "aws" if runtime is not None or single_runtime is not None else "offline"}
    try:
        if confirmed_profile is None:
            fixture = preset_profile(case)
            parsed = await role("profile", {"user_request": case.user_request}, offline=fixture)
            if parsed["status"] == "needs_input":
                result.update(status="needs_input", explanation="Does 14% refer to terminal loss or maximum drawdown?")
                return result
            if case.ambiguous:
                raise RoleError("profile: ambiguous loss limit was accepted without clarification")
            expected_profile = {
                field: value for field, value in fixture.items() if field not in ("status", "summary", "evidence_ids")
            }
            comparable = {field: parsed.get(field) for field in expected_profile}
            comparable["allowed_sources"] = sorted(parsed.get("allowed_sources", []))
            if comparable != expected_profile:
                mismatches = [field for field in expected_profile if expected_profile[field] != comparable[field]]
                raise RoleError("profile: inconsistent with confirmed scenario fields: " + ", ".join(mismatches))
        else:
            parsed = confirmed_profile.data
            trace.extend(confirmed_profile.trace)
            outputs["profile"] = parsed
            trace.append({"role": "profile", "event": "policy_confirmed", "run_id": case.id})
        try:
            policy_view = profile_policy(parsed)
        except ValueError as exc:
            raise RoleError(str(exc)) from exc
        include_issuer = policy_view["issuer_cap"] is not None
        market_files = ("prices_daily.csv", "fx_usdcad_daily.csv")
        market_ids = [f"starter:{filename}" for filename in market_files]
        market_sources = {row["file"]: row for row in data.metadata if row.get("file") in market_files}
        raw_snapshot = issuer_evidence() if include_issuer else None
        issuer_context = {"reference_date": evidence_date, "publication_cutoff": evidence_date,
                          "max_age_days": holdings_max_age_days}
        if raw_snapshot and case.missing_qqq:
            raw_snapshot["holdings"].pop("QQQ", None)
        snapshot = None
        if include_issuer:
            try:
                snapshot = validate_issuer_snapshot(raw_snapshot, assets=BASE_WEIGHTS, **issuer_context)
            except ValueError as exc:
                raise RoleError(f"Invalid evidence policy: {exc}") from exc
        issuer_weights = snapshot["issuer_weights"] if snapshot else {}
        dated_ids = [f"issuer:{ticker}:{snapshot['as_of']}" for ticker, row in snapshot["holdings"].items()
                     if row["status"] == "disclosed"] if snapshot else []
        source_ids = market_ids + dated_ids
        windows = [window.id for window in STRESS_WINDOWS]
        evidence_args = {"scope": "market_and_issuer" if include_issuer else "market_replay",
                         "evidence_ids": source_ids, "holdings_as_of": (snapshot["as_of"] or "") if snapshot else ""}
        evidence = {}

        def get_evidence(scope, evidence_ids, holdings_as_of):
            if not evidence:
                evidence.update(basis="CAD", price_source=market_ids[0], fx_source=market_ids[1],
                                windows=windows, evidence_ids=evidence_ids, market_sources=market_sources)
                if scope == "market_and_issuer":
                    evidence.update(issuer_snapshot=snapshot, issuer_weights=issuer_weights)
            return evidence

        def lookup_evidence(scope: str, evidence_ids: list[str], holdings_as_of: str) -> dict:
            """Return only the frozen market evidence and applicable issuer snapshot for the confirmed rules."""
            return route("evidence", "lookup_evidence", {"scope": scope, "evidence_ids": evidence_ids,
                         "holdings_as_of": holdings_as_of}, evidence_args, get_evidence)

        evidence_payload = {
            "policy": {"issuer_cap": policy_view["issuer_cap"]},
            "catalog": {"market_evidence_ids": market_ids, "issuer_evidence_ids": dated_ids,
                        "holdings_as_of": evidence_args["holdings_as_of"]},
            "tool_contract": "Select market_replay for a policy without an issuer cap, using all market IDs "
                             "and an empty holdings_as_of. Select market_and_issuer when an issuer cap applies. "
                             "In that case include all listed market and issuer evidence IDs and the exact "
                             "holdings_as_of from the catalog, which may be empty when unverified. "
                             "Do not invent evidence for the missing funds.",
        }
        evidence_tool = ToolSpec("lookup_evidence", lookup_evidence.__doc__, lookup_evidence, trace_fields=tuple(evidence_args))

        calculation_policy = {k: v for k, v in policy_view.items() if k not in {"initial_source", "prefer_reserve"}}
        confirmed = {**calculation_policy, "issuer_exposure": issuer_weights, "windows": STRESS_WINDOWS}

        original = proposed_weights(policy_view["initial_source"], policy_view["target"])
        portfolios = {"baseline": BASE_WEIGHTS, "proposal": original}
        for source in policy_view["allowed_sources"]:
            if source != policy_view["initial_source"] and BASE_WEIGHTS[source] >= policy_view["target"]:
                label = "qqq_only" if source == "QQQ" else "zst_only"
                portfolios[label] = proposed_weights(source, amount=policy_view["target"])

        exposure = {}

        def inspect_exposure():
            if not evidence:
                raise ValueError("Look up the evidence first.")
            if not exposure:
                exposure.update(snapshot_as_of=snapshot["as_of"],
                                **{label: exposure_range(weights, issuer_weights) for label, weights in portfolios.items()})
            return exposure

        evaluations = {}
        stress = {}
        market_errors = []
        scenario_focus = {}
        scenario_args = {"metric": policy_view["metric"] if policy_view["loss_limit"] is not None else "comparison",
                         "window_ids": windows}

        def stress_test(metric, window_ids):
            if not evidence:
                raise ValueError("Look up the evidence first.")
            if not stress:
                selected_windows = [window for window in STRESS_WINDOWS if window.id in window_ids]
                try:
                    for label, weights in portfolios.items():
                        evaluations[label] = evaluate_portfolio(data, weights, windows=selected_windows)
                except MarketEvidenceError as exc:
                    market_errors[:] = [exc]
                    raise
                stress.update({label: financial_metrics(row) for label, row in evaluations.items()})
                focus_fields = {
                    "terminal_loss": ("terminal_loss", "terminal_return"),
                    "max_drawdown": ("max_drawdown", "peak_date", "trough_date"),
                    "comparison": ("terminal_loss", "max_drawdown"),
                }[metric]
                scenario_focus.update(metric=metric, window_ids=window_ids, portfolios={
                    label: {window: {key: row[key] for key in focus_fields} for window, row in entry["windows"].items()}
                    for label, entry in stress.items()
                })
            return scenario_focus

        def stress_replay(metric: str, window_ids: list[str]) -> dict:
            """Return the requested emphasis for every required window; Python retains both metrics for audit."""
            return route("scenario", "stress_replay", {"metric": metric, "window_ids": window_ids},
                         scenario_args, stress_test)

        scenario_payload = {
            "policy": {"metric": policy_view["metric"], "loss_limit": policy_view["loss_limit"]},
            "required_windows": windows,
            "tool_contract": "Use the confirmed metric for a loss limit. Without a loss limit, select "
                             "comparison to report both metrics. Include every required window ID.",
        }
        scenario_tool = ToolSpec("stress_replay", stress_replay.__doc__, stress_replay, trace_fields=tuple(scenario_args))
        solution = {}

        def find_alternatives():
            if not stress or (include_issuer and not exposure):
                raise ValueError("Complete replay and applicable exposure calculations before solving.")
            if not solution:
                solve_kwargs = {k: v for k, v in confirmed.items() if k != "windows"}
                solution.update(solve_funding(data, **solve_kwargs))
            option = {k: solution.get(k) for k in ("status", "frontier", "certificate")}
            return option

        review_result = {}

        def review():
            if not solution:
                raise ValueError("Solve the funding range before running independent review.")
            if review_result:
                return review_result
            review_metrics = {label: evaluations[label] for label in ("baseline", "proposal")}
            review_metrics.update(frontier=solution.get("frontier"), solver_status=solution["status"], certificate=solution.get("certificate"))
            if case.tamper:
                first_window = STRESS_WINDOWS[0].id
                p = review_metrics["proposal"]
                wrong_window = {**p["windows"][first_window], "terminal_loss": .01}
                review_metrics["proposal"] = {**p, "windows": {**p["windows"], first_window: wrong_window}}
            # The independent verifier can check an illustrative point without turning
            # its internal reserve-preserving tie-break into a user preference.
            best = solution.get("best") if policy_view["prefer_reserve"] is True else None
            if best:
                best_weights = best.get("weights", best)
                review_metrics["maximum"] = evaluate_portfolio(data, best_weights)
            review_evidence = {**evidence, "fx_dates": tuple(data.fx)}
            if include_issuer:
                review_evidence["issuer_snapshot"] = raw_snapshot
            review_result.update(audit_decision(prices_cad=data.prices, baseline=BASE_WEIGHTS, proposal=original,
                                                maximum=best, policy=confirmed, metrics=review_metrics,
                                                evidence=review_evidence,
                                                issuer_context=issuer_context if include_issuer else None))
            return review_result

        if not include_issuer:
            trace.append({"role": "exposure", "event": "role_skipped", "status": "not_applicable",
                          "reason": "No issuer exposure cap was confirmed."})
        if single_runtime is not None:
            tools = [evidence_tool, scenario_tool]
            if include_issuer:
                tools.append(ToolSpec("measure_exposure", "Use the qualified issuer disclosures to bound NVIDIA exposure.",
                                      inspect_exposure))
            tools += [ToolSpec("solve_funding_range", "Solve the authorized funding range after scenario and exposure.",
                               find_alternatives),
                      ToolSpec("recheck_decision", "Independently verify the replay and funding claims after the solver.", review)]
            single_run = await single_runtime.run({
                "policy": policy_view, "proposal": original, "evidence": evidence_payload, "scenario": scenario_payload,
                "ordered_stages": ["lookup_evidence", "stress_replay", *(["measure_exposure"] if include_issuer else []),
                                   "solve_funding_range", "recheck_decision"],
            }, tools, run_id=case.id, required_tools=[tool.name for tool in tools])
            trace.extend(single_run.trace)
            outputs["single"] = single_run.data
            if market_errors:
                raise market_errors[0]
            if not review_result or (single_run.status == "error" and review_result["status"] != "invalid"):
                raise RoleError(f"single: {single_run.stop_reason or 'missing_checked_review'}")
            alternatives = find_alternatives()
            stated = single_run.data
        else:
            await routed_role("evidence", evidence_payload, evidence_tool, evidence_args, get_evidence, evidence)
            if not evidence:
                raise RoleError("evidence: no checked tool result")
            scenario_run = routed_role("scenario", scenario_payload, scenario_tool, scenario_args, stress_test, stress)
            if include_issuer:
                await asyncio.gather(
                    role("exposure", {"proposal": original, "data": snapshot},
                         tool_name="measure_exposure", operation=inspect_exposure),
                    scenario_run,
                )
            else:
                await scenario_run
            if not stress:
                raise RoleError("scenario: no checked tool result")
            alternatives = await role("alternatives", {"policy": policy_view, "exposure": exposure, "stress": scenario_focus},
                                      tool_name="solve_funding_range", operation=find_alternatives)
            await role("review", {"policy": policy_view, "candidate_status": alternatives, "proposal": original},
                       tool_name="recheck_decision", operation=review)
        result.update(status=review_result["status"], decision_reason=review_result["decision_reason"],
                      policy=policy_view, evidence=evidence, exposure=exposure,
                      scenarios=stress, scenario_focus=scenario_focus, alternatives=alternatives, audit=review_result)
        if review_result["status"] == "invalid":
            result["explanation"] = "The independent calculation detected an invalid claim and withheld the recommendation."
        else:
            if single_runtime is None:
                stated = await role("explanation", {"policy": policy_view, "audited_result": review_result,
                                                     "reason": alternatives, "exposure": exposure, "evidence_ids": source_ids})
            result["explanation"] = explain_audit(review_result, alternatives, policy_view)
            if runtime is not None or single_runtime is not None:
                result["agent_commentary"] = stated["summary"]
        return result
    except MarketEvidenceError as exc:
        message = f"Historical replay is unavailable. {exc}"
        reason = "market_evidence_insufficient"
        trace.append({"role": "scenario", "event": "evidence_unavailable", "status": "insufficient_evidence"})
        result.update(status="insufficient_evidence", decision_reason=reason, policy=policy_view,
                      evidence=evidence, explanation=message,
                      audit={"status": "insufficient_evidence", "decision_reason": reason, "verified": {},
                             "findings": [{"metric_id": "input.market_evidence", "status": "insufficient_evidence",
                                           "message": str(exc)}]})
        return result
    except RoleError as exc:
        result.update(status="execution_error", error=str(exc))
        return result
    finally:
        result.update(agent_outputs=outputs, trace=trace, elapsed_ms=round((perf_counter() - started) * 1000))


def explain_audit(review, alternatives, policy):
    if review["decision_reason"] == "baseline_breaches_policy":
        return "The starting portfolio already breaches a tested rule. The reviewed funding search found no eligible change."
    if review["decision_reason"] == "market_evidence_insufficient":
        return "The required historical price or FX evidence could not be verified. No funding result is available."
    if review["decision_reason"] == "issuer_evidence_insufficient":
        if review["status"] == "fail":
            return "A tested rule is breached by the proposal. Incomplete issuer evidence limits which alternatives can be verified."
        return "The available disclosures cannot settle the issuer cap. The historical risk metrics are available separately."
    if review["status"] == "insufficient_evidence":
        return "The independent review needs more evidence before releasing a decision."
    if alternatives["status"] == "no_feasible":
        return "The tested funding choices have no solution under the stated policy. Review the baseline and binding constraints."
    if alternatives["status"] == "requested_size_infeasible":
        limit = alternatives["frontier"]["diagnostic_max_total"]
        detail = (
            f" The diagnostic limit with smaller purchases allowed is {limit:.2%} of the portfolio."
            if limit is not None else " The evidence does not establish the diagnostic limit for a smaller purchase."
        )
        return f"The full {policy['target']:.2%} purchase is infeasible under your confirmed policy." + detail
    if alternatives["status"] == "feasible_partial":
        limit = alternatives["frontier"]["max_total"]
        if limit <= 1e-9:
            return f"The full {policy['target']:.2%} purchase is infeasible. Keeping the baseline is the only eligible scenario."
        return f"The full {policy['target']:.2%} purchase is infeasible. You allowed a smaller purchase, up to {limit:.2%} under the tested policy."
    if alternatives["status"] == "insufficient_issuer_evidence":
        return "The verified issuer exposure bounds do not establish a feasible alternative. See the audit for any proven breach."
    upper = alternatives["frontier"]["full_zst_max"]
    return (
        f"The full {policy['target']:.2%} purchase has a verified funding mix. ZST.TO can fund up to "
        f"{upper * 100:.2f} percentage points of portfolio weight within the tested rules."
    )
