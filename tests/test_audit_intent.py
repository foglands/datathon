"""Check that user intent controls portfolio search and release of diagnostic results."""

from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

from datathon.agents import AgentRun, StrandsAgents
from datathon.benchmark_single import SingleAgentRuntime
from datathon.counterfactual import counterfactual_options, run_counterfactual
from datathon.data import load_market_data
from datathon.workflow import Case, examples, preset_profile, profile_policy, run_case
from tests.test_tool_routing import MARKET, select_tool_arguments


class AuditIntentTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = load_market_data() if os.environ.get("DATATHON_STARTER_PATH") else MARKET

    def setUp(self):
        self.case = examples("robert")[0]
        self.profile = {**preset_profile(self.case), "allow_smaller": None}

    def test_requirements_for_only_the_original_trade(self):
        self.assertFalse(Case("user", "Check my purchase.", "terminal_loss", None, 0).search_alternatives)
        compiled = profile_policy({**self.profile, "allowed_sources": []}, search_alternatives=False)
        self.assertEqual(compiled["allowed_sources"], ("ZST.TO",))
        self.assertIs(compiled["allow_smaller"], False)
        with self.assertRaisesRegex(ValueError, "excluded"):
            profile_policy({**self.profile, "allowed_sources": ["QQQ"]}, search_alternatives=False)

    async def test_original_trade_invokes_neither_search_nor_candidate_review(self):
        case = replace(self.case, search_alternatives=False)
        called = []

        async def invoke(role, prompt, tools, record):
            payload = json.loads(prompt.split("\n", 1)[1])
            routed = ({role: payload} if role != "single" else
                      {name: payload[name] for name in ("evidence", "scenario")})
            for tool in tools:
                called.append(tool.name)
                name = {"lookup_evidence": "evidence", "stress_replay": "scenario"}.get(tool.name)
                arguments = select_tool_arguments(name, routed.get(name))
                output = tool.handler(**arguments)
                record("tool", tool_name=tool.name, status="success", output=output)
            return {"status": "ok", "summary": "No candidate requested.", "evidence_ids": []}, "end_turn"

        runtimes = ({},
                    {"runtime": StrandsAgents(invoker=invoke)},
                    {"single_runtime": SingleAgentRuntime(invoker=invoke)})
        for runtime in runtimes:
            with self.subTest(runtime=list(runtime)):
                called.clear()
                with (patch("datathon.workflow.solve_funding", side_effect=AssertionError("unexpected search")),
                      patch("datathon.governance._frontier", side_effect=AssertionError("unexpected candidate review"))):
                    report = await run_case(self.market, case, confirmed_profile=AgentRun("ok", self.profile),
                                            include_agent_commentary=True, **runtime)
                if runtime:
                    self.assertEqual(called, ["lookup_evidence", "stress_replay", "recheck_decision"])
                self.assertEqual(report["status"], "fail")
                self.assertEqual(set(report["audit"]["verified"]), {"baseline", "proposal"})
                self.assertEqual(set(report["scenarios"]), {"baseline", "proposal"})
                self.assertNotIn("alternatives", report)
                self.assertNotIn("agent_commentary", report)
                self.assertFalse(report["needs_smaller_authorization"])
                self.assertIn("not_requested", {event.get("reason") for event in report["trace"]})

    async def test_search_asks_about_smaller_size_only_when_it_can_help(self):
        eligible = await run_case(self.market, self.case, confirmed_profile=AgentRun("ok", self.profile))
        self.assertEqual(eligible["decision_reason"], "feasible_full")
        self.assertFalse(eligible["needs_smaller_authorization"])

        exact_only = {**self.profile, "allowed_sources": ["ZST.TO"]}
        limited = await run_case(self.market, self.case, confirmed_profile=AgentRun("ok", exact_only))
        self.assertEqual(limited["decision_reason"], "requested_size_infeasible")
        self.assertTrue(limited["needs_smaller_authorization"])
        self.assertNotIn("maximum", limited["audit"]["verified"])
        self.assertNotIn("diagnostic_max_total", json.dumps(limited))

        smaller = await run_case(self.market, self.case,
                                  confirmed_profile=AgentRun("ok", {**exact_only, "allow_smaller": True}))
        self.assertEqual(smaller["decision_reason"], "feasible_partial")
        self.assertFalse(smaller["needs_smaller_authorization"])
        expected = .05 if self.market.official_starter else .012 / .26
        self.assertAlmostEqual(smaller["audit"]["verified"]["maximum"]["total"], expected)

        drawdown = await run_case(self.market, examples("robert")[1],
                                  confirmed_profile=AgentRun("ok", {**exact_only, "metric": "max_drawdown"}))
        self.assertEqual(drawdown["decision_reason"], "baseline_breaches_policy")
        self.assertFalse(drawdown["needs_smaller_authorization"])

    async def test_audit_only_loss_replay_preserves_authorization(self):
        case = replace(self.case, search_alternatives=False)
        report = await run_case(self.market, case, confirmed_profile=AgentRun("ok", self.profile))
        options = {option.id for option in counterfactual_options(report)}
        self.assertIn("toggle_loss_metric", options)
        self.assertNotIn("toggle_purchase_size", options)
        replay = await run_counterfactual(self.market, case, report, option_id="toggle_loss_metric")
        self.assertEqual(replay["status"], "verified")
        self.assertFalse(replay["replay"]["search_alternatives"])
        self.assertNotIn("alternatives", replay["replay"])

    async def test_issuer_followup_for_an_original_trade_has_no_candidate(self):
        case = replace(examples("amira")[0], search_alternatives=False)
        profile = {**preset_profile(case), "initial_source": "QQQ", "allow_smaller": None}
        report = await run_case(self.market, case, confirmed_profile=AgentRun("ok", profile))
        self.assertEqual(report["decision_reason"], "issuer_evidence_insufficient")
        followup = await run_counterfactual(self.market, case, report, option_id="request_issuer_evidence")
        self.assertEqual(followup["reason"], "issuer_evidence_required")
        self.assertEqual(set(followup["action"]["thresholds"]), {"baseline", "proposal"})
