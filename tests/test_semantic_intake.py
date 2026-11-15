"""Exercise the semantic boundary with Strands tool validation and a stub AWS response."""

import json
import unittest
from importlib.util import find_spec
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun, DEFAULT_MODEL, DEFAULT_REGION, StrandsAgents
from datathon.runtime_budget import PROFILE_MAX_REQUEST_BYTES, RuntimeBudgetExceeded
from datathon.semantic_intake import interpret_semantic_request


_TOOL = "classify_investment_question"


class SemanticIntakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_unquoted_sources_unknown_tags_and_multiple_handoffs(self):
        request = "Does it make sense to set some savings aside for the next market dip?"
        route = {"task": "planning", "task_source": "clause_1"}
        attempts = (
            ({**route, "task_source": "A fabricated source"},),
            ({**route, "points": {"risk": "clause_55"}},),
            ({**route, "points": {"amount": "clause_1"}},),
            ({**route, "task": "trade_audit", "points": {"risk": "clause_1"}},),
            (route, route),
            (),
        )
        for invocations in attempts:
            runtime = AsyncMock()

            async def run(role, payload, *, tools, stop_after_tool):
                self.assertEqual(role, "semantic_intake")
                self.assertEqual(payload["user_request"], request)
                self.assertEqual(stop_after_tool, _TOOL)
                tool, = tools
                for arguments in invocations:
                    try:
                        tool.handler(**arguments)
                    except ValueError:
                        pass
                return AgentRun("ok", {"risk": 0.0, "summary": "Guaranteed profits."})

            runtime.run.side_effect = run
            with self.subTest(invocations=invocations):
                result = await interpret_semantic_request(request, runtime)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["task"])
                self.assertIsNone(result["plan"])
                runtime.run.assert_awaited_once()

    async def test_handles_absent_input_and_runtime_budget_without_accepting_a_route(self):
        runtime = AsyncMock()
        for request in ("   ", "é" * PROFILE_MAX_REQUEST_BYTES, "\ud800"):
            self.assertEqual((await interpret_semantic_request(request, runtime))["status"], "needs_input")
        runtime.run.assert_not_awaited()

        request = "Would a deposit help me set aside some savings?"
        self.assertEqual((await interpret_semantic_request(request, None))["status"], "unavailable")
        runtime.run.side_effect = RuntimeBudgetExceeded("deadline", {"limit_reached": "deadline"})
        result = await interpret_semantic_request(request, runtime)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["usage"]["limit_reached"], "deadline")

    async def test_does_not_ascribe_third_party_negated_or_hypothetical_context_to_the_investor(self):
        positive = "I would lie awake after a big paper loss."
        request = ("My cousin is terrified of losing money. I’m not worried about a temporary decline. "
                   f"If I had $60,000, it might sit in the bank. {positive} Would this investment suit my goal?")
        for risk_source, expected in (("clause_1", {}), ("clause_2", {}), ("clause_4", {"risk": positive})):
            runtime = AsyncMock()

            async def run(_role, _payload, *, tools, stop_after_tool):
                tool, = tools
                self.assertEqual(stop_after_tool, tool.name)
                tool.handler(task="planning", task_source="clause_5", points={
                    "risk": risk_source, "cash_position": "clause_3", "timing": "clause_1",
                })
                return AgentRun("ok", {})

            runtime.run.side_effect = run
            with self.subTest(risk_source=risk_source):
                result = await interpret_semantic_request(request, runtime)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["plan"]["points"], expected)

    @unittest.skipIf(find_spec("strands") is None, "Install the pinned Strands SDK to exercise the Bedrock tool.")
    async def test_sdk_passes_intact_question_and_accepts_only_evidenced_instruments(self):
        import boto3
        from botocore.stub import Stubber
        from strands.models import BedrockModel

        spending = "My lease renewal will draw on my savings."
        avoided = "I do not want gold."
        decision = "What should I consider before moving some money into bond funds?"
        request = f" {spending} {avoided} {decision}  "
        captures = []
        session = boto3.Session(aws_access_key_id="test", aws_secret_access_key="test", region_name=DEFAULT_REGION)
        model = BedrockModel(model_id=DEFAULT_MODEL, streaming=False, boto_session=session)
        model.client.meta.events.register(
            "before-parameter-build.bedrock-runtime.Converse", lambda params, **_: captures.append(params),
        )
        with Stubber(model.client) as stub, patch("strands.models.BedrockModel", return_value=model):
            stub.add_response("converse", {
                "output": {"message": {"role": "assistant", "content": [{"toolUse": {
                    "toolUseId": "semantic-test", "name": _TOOL, "input": {
                        "task": "planning", "task_source": "clause_3", "points": {"spending": "clause_1"},
                        "instruments": {"bonds": "clause_3", "gold": "clause_2", "crypto": "clause_1"},
                        "suggested_trade_weight": 1.0,
                    },
                }}]}},
                "stopReason": "tool_use", "usage": {"inputTokens": 120, "outputTokens": 30, "totalTokens": 150},
                "metrics": {"latencyMs": 2}, "ResponseMetadata": {"RequestId": "semantic-test", "HTTPStatusCode": 200},
            })
            result = await interpret_semantic_request(request, StrandsAgents())
            stub.assert_no_pending_responses()

        capture, = captures
        payload = json.loads(capture["messages"][0]["content"][0]["text"].split("\n", 1)[1])
        self.assertEqual(payload["user_request"], request)
        self.assertEqual(payload["candidate_clauses"], {"clause_1": spending, "clause_2": avoided, "clause_3": decision})
        tool, = capture["toolConfig"]["tools"]
        schema = tool["toolSpec"]["inputSchema"]["json"]
        self.assertEqual(set(schema["properties"]["task"]["enum"]),
                         {"planning", "compare_allocations", "trade_audit", "unsupported"})
        self.assertEqual(set(schema["properties"]), {"task", "task_source", "points", "instruments"})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["task"], "planning")
        self.assertEqual(result["plan"], {"points": {"spending": spending}, "instruments": ("bonds",),
                                         "instrument_sources": {"bonds": decision}, "examples": ()})
        self.assertEqual(result["usage"]["reported_total_tokens"], 150)
        trace = json.dumps(result["trace"])
        self.assertTrue(any(row.get("tool_name") == _TOOL for row in result["trace"]))
        self.assertNotIn(spending, trace)
        self.assertNotIn(decision, trace)
