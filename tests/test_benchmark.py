"""Check the bundled benchmark against the production audit and trace gates."""

import json
import unittest

from datathon.agents import AgentRun
from datathon.benchmark import usage
from datathon.benchmark_single import SingleAgentRuntime
from datathon.workflow import examples, preset_profile, run_case
from tests.test_tool_routing import MARKET, select_tool_arguments


class SingleAgentBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, case, *, reverse_calls=False, forge_review=False):
        async def invoke(role, prompt, tools, record):
            self.assertEqual(role, "single")
            payload = json.loads(prompt.split("\n", 1)[1])
            self.assertEqual(set(payload["required_tools"]), {tool.name for tool in tools})
            routed_arguments = {
                "lookup_evidence": select_tool_arguments("evidence", payload["evidence"]),
                "stress_replay": select_tool_arguments("scenario", payload["scenario"]),
            }
            if reverse_calls:
                tools = reversed(tools)
            for tool in tools:
                arguments = routed_arguments.get(tool.name, {})
                status = "success"
                output = None
                if not (forge_review and tool.name == "recheck_decision"):
                    try:
                        output = tool.handler(**arguments)
                    except ValueError:
                        status = "error"
                record("tool", tool_name=tool.name, status=status, input=arguments, output=output)
            return {"status": "ok", "summary": "The proposed trade passes.",
                    "evidence_ids": ["model:invented"]}, "end_turn"

        return await run_case(MARKET, case, single_runtime=SingleAgentRuntime(invoker=invoke),
                              confirmed_profile=AgentRun("ok", preset_profile(case)))

    async def test_single_matches_independent_audit_with_present_or_missing_issuer_disclosures(self):
        for case in examples("amira", stress=True):
            with self.subTest(case=case.id):
                control = await run_case(MARKET, case, confirmed_profile=AgentRun("ok", preset_profile(case)))
                report = await self.run_case(case)
                self.assertEqual(report["status"], "insufficient_evidence" if case.missing_qqq else "fail")
                self.assertEqual(report["audit"], control["audit"])
                self.assertEqual(report["evidence"], control["evidence"])
                self.assertEqual(report["explanation"], control["explanation"])
                self.assertNotIn("model:invented", report["evidence"]["evidence_ids"])
                self.assertEqual(usage(report["trace"])["agent_sessions"], 1)
                self.assertTrue(all(event["role"] == "single" for event in report["trace"]
                                    if event["event"] in {"agent_start", "tool", "agent_end"}))

    async def test_tool_dependencies_reject_out_of_order_calls(self):
        case = examples("robert")[0]
        report = await self.run_case(case, reverse_calls=True)
        failed = {event["tool_name"] for event in report["trace"]
                  if event["event"] == "tool" and event["status"] == "error"}
        self.assertEqual(failed, {"stress_replay", "solve_funding_range", "recheck_decision"})
        self.assertEqual(report["status"], "execution_error")
        self.assertNotIn("audit", report)

    async def test_claimed_review_success_does_not_release_a_decision(self):
        case = examples("robert")[0]
        report = await self.run_case(case, forge_review=True)
        self.assertTrue(any(event["event"] == "tool" and event["tool_name"] == "recheck_decision"
                            and event["status"] == "success" for event in report["trace"]))
        self.assertEqual(report["status"], "execution_error")
        self.assertNotIn("audit", report)


class BenchmarkUsageTests(unittest.TestCase):
    def test_missing_usage_remains_unknown_for_an_incomplete_group(self):
        available = {"event": "bedrock", "status": "success", "input_tokens": 123, "output_tokens": 34}
        missing = {"event": "bedrock", "status": "success"}
        failed = {"event": "bedrock", "status": "error"}
        counted = usage([available, failed])
        self.assertEqual((counted["input_tokens"], counted["output_tokens"], counted["failed_converse"]), (123, 34, 1))
        incomplete = usage([available, missing, failed])
        self.assertEqual((incomplete["converse"], incomplete["token_responses"]), (2, 1))
        self.assertIsNone(incomplete["input_tokens"])
        self.assertIsNone(incomplete["output_tokens"])
