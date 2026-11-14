"""Explicit handoffs for the investment simulation."""

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Optional

from .data import issuer_evidence, issuer_exposure_weights
from .finance import BASE_WEIGHTS, STRESS_WINDOWS, evaluate_portfolio, solve_funding
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


async def run_case(data, case, runtime=None):
    """Run fresh role sessions with source and calculation data owned by Python."""
    from .agents import ToolSpec

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

    official = issuer_evidence()
    issuer_weights = issuer_exposure_weights(allow_scope_assumptions=False)
    if case.missing_qqq:
        issuer_weights["QQQ"] = None
        official["holdings"]["QQQ"].update(weight=None, status="unknown", url=None, published_on=None)

    def get_evidence():
        return {
            "basis": "CAD",
            "price_source": "starter:prices_daily.csv",
            "fx_source": "starter:fx_usdcad_daily.csv",
            "issuer_snapshot": official,
            "issuer_weights": issuer_weights,
            "windows": [window.id for window in STRESS_WINDOWS],
            "evidence_ids": source_ids,
        }

    source_ids = ["starter:prices_daily.csv", "starter:fx_usdcad_daily.csv"]
    source_ids.extend(f"issuer:{ticker}:2026-06-30" for ticker, entry in official["holdings"].items()
                      if entry["status"] == "disclosed")
    expected_profile = {
        "metric": case.metric if case.loss_limit is not None else None,
        "limit_bps": round(case.loss_limit * 10000) if case.loss_limit is not None else None,
        "target_bps": 1000,
        "reserve_floor_bps": round(case.reserve_floor * 10000) if case.reserve_floor else None,
        "issuer_cap_bps": round(case.issuer_cap * 10000) if case.issuer_cap is not None else None,
        "allowed_sources": ["QQQ", "ZST.TO"],
        "allow_smaller": True,
        "prefer_reserve": True if case.id.startswith("robert") else None,
    }
    result = {"case": case.id, "mode": "offline" if runtime is None else "aws"}
    try:
        parsed, evidence = await asyncio.gather(
            role("profile", {"user_request": case.user_request}, offline={
                "status": "needs_input" if case.ambiguous else "ok", "summary": "Scenario fixture", "evidence_ids": [],
                **expected_profile,
            }),
            role("evidence", {"assets": list(BASE_WEIGHTS), "needs": ["CAD history", "issuer holdings with as-of date"]},
                 tool_name="lookup_evidence", operation=get_evidence),
        )
        if parsed["status"] == "needs_input":
            result.update(status="needs_input", explanation="Does 14% refer to terminal loss or maximum drawdown?")
            return result
        if case.ambiguous:
            raise RoleError("profile: ambiguous loss limit was accepted without clarification")
        comparable = {field: parsed.get(field) for field in expected_profile}
        comparable["allowed_sources"] = sorted(parsed.get("allowed_sources", []))
        if comparable != expected_profile:
            mismatches = [field for field in expected_profile if expected_profile[field] != comparable[field]]
            raise RoleError("profile: inconsistent with confirmed scenario fields: " + ", ".join(mismatches))
        policy_view = {
            "target": parsed["target_bps"] / 10000,
            "reserve_floor": (parsed.get("reserve_floor_bps") or 0) / 10000,
            "allowed_sources": tuple(comparable["allowed_sources"]),
            "loss_limit": parsed["limit_bps"] / 10000 if parsed.get("limit_bps") is not None else None,
            "metric": parsed.get("metric") or "terminal_loss",
            "issuer_cap": parsed["issuer_cap_bps"] / 10000 if parsed.get("issuer_cap_bps") is not None else None,
        }
        confirmed = {**policy_view, "issuer_exposure": issuer_weights, "windows": STRESS_WINDOWS}

        original = proposed_weights(amount=policy_view["target"])
        qqq_only = proposed_weights("QQQ", amount=policy_view["target"])

        def inspect_exposure():
            return {"snapshot_as_of": official["as_of"], "baseline": exposure_range(BASE_WEIGHTS, issuer_weights),
                    "proposal": exposure_range(original, issuer_weights), "qqq_only": exposure_range(qqq_only, issuer_weights)}

        evaluations = {}

        def stress_test():
            for label, weights in (("baseline", BASE_WEIGHTS), ("proposal", original), ("qqq_only", qqq_only)):
                evaluations[label] = evaluate_portfolio(data, weights)
            return {label: financial_metrics(row) for label, row in evaluations.items()}

        exposure, stress = await asyncio.gather(
            role("exposure", {"proposal": original, "data": evidence["issuer_snapshot"]},
                 tool_name="measure_exposure", operation=inspect_exposure),
            role("scenario", {"policy": policy_view, "windows": evidence["windows"]},
                 tool_name="stress_replay", operation=stress_test),
        )
        solution = {}

        def find_alternatives():
            solve_kwargs = {k: v for k, v in confirmed.items() if k not in {"windows"}}
            solution.update(solve_funding(data, **solve_kwargs))
            return {k: solution.get(k) for k in ("status", "frontier", "certificate")}

        alternatives = await role("alternatives", {"policy": policy_view, "exposure": exposure, "stress": stress},
                                  tool_name="solve_funding_range", operation=find_alternatives)
        review_result = {}

        def review():
            review_metrics = {label: row for label, row in evaluations.items() if label != "qqq_only"}
            review_metrics.update(frontier=solution.get("frontier"), solver_status=solution["status"], certificate=solution.get("certificate"))
            if case.tamper:
                first_window = STRESS_WINDOWS[0].id
                p = review_metrics["proposal"]
                wrong_window = {**p["windows"][first_window], "terminal_loss": .01}
                review_metrics["proposal"] = {**p, "windows": {**p["windows"], first_window: wrong_window}}
            best = solution.get("best")
            if best:
                best_weights = best.get("weights", best)
                review_metrics["maximum"] = evaluate_portfolio(data, best_weights)
            review_result.update(audit_decision(prices_cad=data.prices, baseline=BASE_WEIGHTS, proposal=original,
                                                maximum=best, policy=confirmed, metrics=review_metrics,
                                                evidence={**evidence, "fx_dates": tuple(data.fx)}))
            return review_result

        await role("review", {"policy": policy_view, "candidate_status": alternatives, "proposal": original},
                   tool_name="recheck_decision", operation=review)
        result.update(status=review_result["status"], policy=policy_view, evidence=evidence, exposure=exposure,
                      scenarios=stress, alternatives=alternatives, audit=review_result)
        if review_result["status"] == "invalid":
            result["explanation"] = "The independent calculation detected an invalid claim and withheld the recommendation."
        else:
            stated = await role("explanation", {"policy": policy_view, "audited_result": review_result,
                                                 "reason": alternatives, "exposure": exposure, "evidence_ids": source_ids})
            result["explanation"] = explain_audit(review_result, alternatives)
            if runtime is not None:
                result["agent_commentary"] = stated["summary"]
        return result
    except RoleError as exc:
        result.update(status="execution_error", error=str(exc))
        return result
    finally:
        result.update(agent_outputs=outputs, trace=trace, elapsed_ms=round((perf_counter() - started) * 1000))


def explain_audit(review, alternatives):
    if review["status"] == "insufficient_evidence":
        return "An applicable constraint needs more evidence. The historical replay is available separately."
    if alternatives["status"] == "no_feasible":
        return "The tested funding choices have no solution under the stated policy. Review the baseline and binding constraints."
    return "Compare the original request with the audited alternatives under the stated scenario and constraints."
