"""A bundled-tool Strands baseline for the portfolio audit benchmark."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .agents import DEFAULT_MODEL, DEFAULT_REGION, ROLES, AgentRun, InvokeAgent, Role, StrandsAgents, ToolSpec


_SINGLE_ROLE = Role(
    "You are the sole agent conducting the decision audit after the investor confirmed the policy. "
    "Complete each tool listed in required_tools to finish the audit. Start with lookup_evidence. "
    "Wait for its result, then call stress_replay and also measure_exposure when required. "
    "Wait for the scenario and any required exposure before calling an authorized solve_funding_range. "
    "When search_alternatives is false, recheck only the submitted trade and do not search alternatives. "
    "Wait for all applicable tools before calling recheck_decision. Do not call dependent tools in the same batch. "
    "Use exact machine values from the payload. For lookup_evidence, scope is 'market_replay' "
    "when policy.issuer_cap is null and 'market_and_issuer' when it is a number. Copy every market "
    "evidence ID and add every listed issuer evidence ID for 'market_and_issuer'. Use an empty "
    "holdings_as_of for 'market_replay'. For stress_replay, use exactly policy.metric when "
    "loss_limit is a number, or 'comparison' otherwise. Include every required window. "
    "After the review, summarize only its "
    "verified conclusions and relevant evidence IDs. The review result controls the decision. "
    + " ".join(ROLES[role].instructions for role in ("exposure", "alternatives", "review", "explanation"))
)


class _BundledStrandsAgent(StrandsAgents):
    def _role_config(self, role: str) -> Role:
        return _SINGLE_ROLE if role == "single" else super()._role_config(role)


class SingleAgentRuntime:
    """Run one agent with all the shared audit tools in one conversation.

    The workflow supplies the same Python tools and enforces their dependencies.
    Natural-language benchmark cases use the original intake parser under the
    standard profile budget before running the confirmed decision separately.
    """

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL,
        region: str = DEFAULT_REGION,
        timeout_seconds: float = 95,
        max_turns: int = 16,
        max_total_tokens: int = 54000,
        invoker: InvokeAgent | None = None,
        stop_after_review: bool = False,
    ) -> None:
        self._decision = _BundledStrandsAgent(
            model_id=model_id, region=region, timeout_seconds=timeout_seconds,
            max_turns=max_turns, max_total_tokens=max_total_tokens, invoker=invoker,
        )
        self._intake = StrandsAgents(model_id=model_id, region=region, invoker=invoker)
        self._stop_after_review = stop_after_review

    async def run(
        self,
        payload: Mapping[str, Any],
        tools: Sequence[ToolSpec],
        *,
        run_id: str,
        required_tools: Sequence[str],
    ) -> AgentRun:
        return await self._decision.run(
            "single", payload, tools, run_id=run_id, required_tools=required_tools,
            stop_after_tool="recheck_decision" if self._stop_after_review else None,
        )

    async def interpret(self, request: str, *, run_id: str) -> AgentRun:
        return await self._intake.run("profile", {"user_request": request}, run_id=run_id)
