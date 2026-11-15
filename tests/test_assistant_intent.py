"""Task suggestions require the bounded tool handoff and carry no executable inputs."""

import json
import unittest
from unittest.mock import AsyncMock

from datathon.agents import AgentRun, StrandsAgents
from datathon.assistant_intent import suggest_intent
from datathon.runtime_budget import PROFILE_MAX_REQUEST_BYTES


class AssistantIntentTests(unittest.IsolatedAsyncioTestCase):
    async def test_suggestion_retains_task_and_redacts_tool_payload(self):
        request = "Comparer deux portefeuilles fictifs avec des pertes historiques."

        async def invoke(role, prompt, tools, record):
            self.assertEqual(role, "assistant_intent")
            self.assertEqual(json.loads(prompt.split("\n", 1)[1])["user_request"], request)
            tool, = tools
            selected = tool.handler("compare_allocations")
            record("tool", tool_name=tool.name, status="success", input={**selected, "request": request},
                   output={"summary": request})
            return {"status": "ok", "summary": request, "evidence_ids": []}, "tool_use"

        result = await suggest_intent(request, StrandsAgents(invoker=invoke))
        self.assertEqual((result["status"], result["task"]), ("proposed", "compare_allocations"))
        self.assertNotIn(request, json.dumps(result, ensure_ascii=False))
        self.assertEqual(set(result), {"status", "task", "trace", "usage"})
        self.assertTrue(any(row.get("tool_name") == "select_investment_task" for row in result["trace"]))

    async def test_no_route_for_unsupported_or_multiple_selections(self):
        for selections, expected in ((["unsupported"], "unsupported"),
                                     (["trade_audit", "compare_allocations"], "unavailable"),
                                     (["invent_prices"], "unavailable"),
                                     ([], "unavailable")):
            runtime = AsyncMock()

            async def run(role, payload, *, tools, stop_after_tool):
                tool, = tools
                self.assertEqual(stop_after_tool, tool.name)
                for choice in selections:
                    try:
                        tool.handler(choice)
                    except ValueError:
                        pass
                return AgentRun("ok", {"task": "trade_audit", "search_authorized": True})

            runtime.run.side_effect = run
            with self.subTest(selections=selections):
                result = await suggest_intent("An investment question", runtime)
                self.assertEqual((result["status"], result["task"]), (expected, None))
                self.assertNotIn("search_authorized", result)

    async def test_empty_and_excess_utf8_inputs_never_call_runtime(self):
        runtime = AsyncMock()
        for request in (" \n", "é" * PROFILE_MAX_REQUEST_BYTES):
            result = await suggest_intent(request, runtime)
            self.assertEqual((result["status"], result["task"]), ("needs_input", None))
        runtime.run.assert_not_awaited()
