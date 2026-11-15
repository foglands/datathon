"""Keep comparison model handoffs grounded and non-executable."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun, StrandsAgents
from datathon.assistant_request_model import interpret_comparison_request

try:
    from strands.hooks import AfterToolCallEvent, AfterToolsEvent
except ModuleNotFoundError as exc:
    if exc.name != "strands":
        raise
    AfterToolCallEvent = AfterToolsEvent = None


ASSETS = ("AGG", "GLD")
TOOL = "locate_comparison_clauses"
EXCERPT = "AGG and GLD"


def parsed(status, fields=None, sources=None, message="Please clarify the request."):
    return {"status": status, "fields": fields or {}, "sources": sources or {}, "message": message}


class ComparisonRequestModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_does_not_reinterpret_a_ready_or_unsupported_whole_request(self):
        runtime = AsyncMock()
        for status in ("ready", "unsupported"):
            with patch("datathon.assistant_request_model.parse_comparison_request", return_value=parsed(status)):
                result = await interpret_comparison_request("A historical comparison", ASSETS, runtime)
            self.assertEqual(result["status"], status)
            self.assertEqual(result["interpretation"], "local")
        runtime.run.assert_not_awaited()

    async def test_tool_cannot_drop_a_negated_prefix_or_replace_the_request(self):
        for chosen in ("AGG and GLD", "Compare NVDA and SPY"):
            runtime = AsyncMock()

            async def rejected(role, payload, *, tools, stop_after_tool):
                self.assertEqual(role, "comparison_request")
                self.assertEqual(stop_after_tool, TOOL)
                tool, = tools
                with self.assertRaises(ValueError):
                    tool.handler(options_clause=chosen)
                return AgentRun("ok", {"first_asset": "NVDA", "max_drawdown": .05})

            runtime.run.side_effect = rejected
            with patch("datathon.assistant_request_model.parse_comparison_request",
                       return_value=parsed("unrecognized")) as parser:
                result = await interpret_comparison_request("Do not use AGG and GLD.", ASSETS, runtime)
            self.assertEqual(result["status"], "unrecognized")
            self.assertEqual(result["fields"], {})
            self.assertEqual(parser.call_count, 1)

    async def test_whole_request_cap_and_conflicts_survive_a_partial_model_handoff(self):
        async def invoke(_role, _prompt, tools, record):
            tool, = tools
            tool.handler(options_clause=EXCERPT)
            record("tool", tool_name=TOOL, status="success")
            return {"status": "ok", "summary": "Clause located.", "evidence_ids": []}, "tool_use"

        runtime = StrandsAgents(invoker=invoke)
        request = f"I have two candidates; {EXCERPT}; maximum drawdown limit is 12%."
        draft = await interpret_comparison_request(request, ASSETS, runtime)
        self.assertTrue(draft["scope_review_required"])
        self.assertEqual(draft["fields"]["max_drawdown"], .12)
        conflicting = request + " Maximum drawdown limit is 8%."
        blocked = await interpret_comparison_request(conflicting, ASSETS, runtime)
        self.assertEqual(blocked["status"], "clarify")
        self.assertFalse(blocked["scope_review_required"])

    @unittest.skipIf(AfterToolCallEvent is None, "Install the pinned Strands SDK to verify its comparison tool.")
    async def test_sdk_selects_exact_clauses_for_a_reviewable_draft_and_redacts_trace(self):
        test = self
        request = f"A fictional scenario; {EXCERPT}; my context requires review."

        class RecordedAgent:
            def __init__(self, *, tools, **_):
                self.tool, = tools
                self.callbacks = {}
                self.hooks = SimpleNamespace(add_callback=self.callbacks.__setitem__)
                schema = self.tool.tool_spec["inputSchema"]["json"]
                test.assertEqual(schema["properties"]["options_clause"]["type"], "string")
                test.assertNotIn("max_drawdown", schema["properties"])

            async def invoke_async(self, prompt, *, structured_output_model, **_):
                test.assertIsNone(structured_output_model)
                payload = json.loads(prompt.split("\n", 1)[1])
                test.assertIn(EXCERPT, payload["candidate_clauses"])
                use = {"name": TOOL, "toolUseId": "local-comparison-review", "input": {"options_clause": EXCERPT}}
                result = [part async for part in self.tool.stream(use, {})][-1].tool_result
                self.callbacks[AfterToolCallEvent](SimpleNamespace(tool_use=use, result=result, duration=.001))
                finished = SimpleNamespace(end_turn=False)
                self.callbacks[AfterToolsEvent](finished)
                test.assertTrue(finished.end_turn)
                return SimpleNamespace(stop_reason="tool_use")

        def parse(text, symbols, *, extract_only=False):
            self.assertEqual(symbols, ASSETS)
            if not extract_only or text == request:
                self.assertEqual(text, request)
                return parsed("unrecognized")
            self.assertEqual(text, EXCERPT)
            return parsed("clarify", {"first_asset": "AGG", "second_asset": "GLD"},
                          {"first_asset": "AGG", "second_asset": "GLD"})

        client = SimpleNamespace(meta=SimpleNamespace(events=SimpleNamespace(register=lambda *_: None)))
        with patch("strands.Agent", RecordedAgent), patch("strands.models.BedrockModel", return_value=SimpleNamespace(client=client)), \
                patch("datathon.assistant_request_model.parse_comparison_request", side_effect=parse):
            result = await interpret_comparison_request(request, ASSETS, StrandsAgents())
        self.assertEqual(result["status"], "clarify")
        self.assertEqual(result["interpretation"], "bedrock")
        self.assertTrue(result["scope_review_required"])
        self.assertEqual(result["fields"], {"first_asset": "AGG", "second_asset": "GLD"})
        self.assertNotIn(EXCERPT, json.dumps(result["trace"]))
