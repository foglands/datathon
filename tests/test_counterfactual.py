"""Challenge selection and one-rule re-audit tests on the frozen market fixtures."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import os
import unittest
from unittest.mock import AsyncMock

from datathon.agents import AgentRun, StrandsAgents
from datathon.benchmark_single import SingleAgentRuntime
from datathon.counterfactual import counterfactual_options, run_counterfactual
from datathon.data import load_market_data
from datathon.workflow import examples, preset_profile, run_case
from tests.test_tool_routing import MARKET, select_tool_arguments


class ChallengeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        data_path = os.environ.get("DATATHON_STARTER_PATH")
        cls.market = load_market_data(Path(data_path)) if data_path else MARKET

    async def baseline(self, case, **changes):
        profile = AgentRun("ok", {**preset_profile(case), **changes})
        return await run_case(self.market, case, confirmed_profile=profile)

    async def test_loss_metric_reaudit_changes_funding_verdict_and_preserves_baseline(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)
        report["user_request"] = "Private request"
        report["agent_commentary"] = "Unverified commentary"
        report["trace"].append({"event": "tool", "role": "profile", "input": {"request": "Private request"}})
        original = deepcopy(report)
        replayer = AsyncMock(wraps=run_case)
        result = await run_counterfactual(self.market, robert, report, option_id="toggle_loss_metric", replayer=replayer)
        self.assertEqual(report, original)
        for field in ("policy", "audit", "scenarios"):
            self.assertEqual(result["baseline"][field], original[field])
        self.assertNotIn("user_request", result["baseline"])
        self.assertNotIn("agent_commentary", result["baseline"])
        self.assertNotIn("input", result["baseline"]["trace"][-1])
        self.assertTrue(result["verified"])
        self.assertEqual(result["changed_fields"], ["metric"])
        self.assertEqual(result["replay"]["policy"], {**report["policy"], "metric": "max_drawdown"})
        comparison = result["comparison"]
        self.assertEqual(comparison["baseline"]["solver_status"], "feasible_full")
        self.assertEqual(comparison["replay"]["solver_status"], "no_feasible")
        self.assertEqual(comparison["replay"]["decision_reason"], "baseline_breaches_policy")
        self.assertNotIn("proposal_terminal_loss", comparison["differences"])
        self.assertNotIn("proposal_max_drawdown", comparison["differences"])
        replayer.assert_awaited_once()

    async def test_reserve_floor_reaudit_uses_only_the_tighter_floor(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)
        result = await run_counterfactual(self.market, robert, report, option_id="tighten_reserve_floor")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["option"]["trigger"], "confirmed_positive_reserve_floor")
        self.assertEqual(result["replay"]["policy"], {**report["policy"], "reserve_floor": .18})
        self.assertAlmostEqual(result["comparison"]["replay"]["full_zst_max"], .02)
        self.assertEqual(result["comparison"]["replay"]["full_zst_max_binding"], "reserve_floor")

    async def test_purchase_size_can_map_a_diagnostic_to_an_eligible_alternative(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert, allow_smaller=False, allowed_sources=["ZST.TO"])
        result = await run_counterfactual(self.market, robert, report, option_id="toggle_purchase_size")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["changed_fields"], ["allow_smaller"])
        before, after = (result["comparison"][stage] for stage in ("baseline", "replay"))
        self.assertEqual(before["solver_status"], "requested_size_infeasible")
        self.assertFalse(before["alternative_eligible"])
        self.assertEqual(after["solver_status"], "feasible_partial")
        self.assertTrue(after["alternative_eligible"])
        self.assertAlmostEqual(before["diagnostic_max_total"], after["eligible_max_total"])

    async def test_holdings_age_changes_issuer_audit_only(self):
        amira, = examples("amira")
        report = await self.baseline(amira)
        result = await run_counterfactual(self.market, amira, report, option_id="tighten_holdings_age")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["changed_fields"], ["holdings_max_age_days"])
        self.assertEqual(report["policy"], result["replay"]["policy"])
        self.assertEqual(report["scenarios"], result["replay"]["scenarios"])
        after = result["comparison"]["replay"]
        self.assertEqual(after["status"], "insufficient_evidence")
        self.assertAlmostEqual(after["proposal_issuer_lower"], .10)
        self.assertEqual(after["issuer_evidence_ids"], [])

    async def test_issuer_action_does_not_invent_or_reaudit_missing_disclosures(self):
        _, amira = examples("amira", stress=True)
        report = await self.baseline(amira)
        replayer = AsyncMock()
        result = await run_counterfactual(self.market, amira, report, option_id="request_issuer_evidence", replayer=replayer)
        self.assertEqual(result["status"], "no_recommendation")
        self.assertTrue(result["verified"])
        self.assertEqual(result["reason"], "issuer_evidence_required")
        self.assertIn("QQQ", result["action"]["holdings"])
        self.assertIn("publication_date", result["action"]["required_fields"])
        self.assertIsNone(result["replay"])
        replayer.assert_not_awaited()

    async def test_action_includes_independently_derived_qqq_evidence_budget(self):
        amira, = examples("amira")
        report = await self.baseline(amira)
        result = await run_counterfactual(self.market, amira, report, option_id="request_issuer_evidence")
        thresholds = result["action"]["thresholds"]
        self.assertEqual(thresholds["proposal"]["status"], "breach")
        self.assertIsNone(thresholds["proposal"]["maximum_combined_additional_exposure"])
        self.assertEqual(thresholds["baseline"]["basis"], "independent_audit")
        qqq = thresholds["qqq_only"]
        self.assertEqual(qqq["status"], "unresolved")
        self.assertEqual(qqq["unknown_holdings"], {"XIU.TO": .25, "ZST.TO": .20})
        self.assertAlmostEqual(qqq["known_lower"], .1339062980483545)
        self.assertAlmostEqual(qqq["maximum_combined_additional_exposure"], .0060937019516455)

    async def test_issuer_uncertainty_routes_to_evidence_instead_of_unrelated_size_rule(self):
        amira, = examples("amira")
        report = await self.baseline(amira)
        replayer = AsyncMock()
        result = await run_counterfactual(self.market, amira, report, replayer=replayer)
        self.assertEqual(result["reason"], "issuer_evidence_required")
        self.assertEqual(result["selection_mode"], "deterministic")
        replayer.assert_not_awaited()

    async def test_bounded_model_selection_requires_actual_callback(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)

        async def invoke(role, prompt, tools, record):
            self.assertEqual(role, "review_challenge")
            payload = json.loads(prompt.split("\n", 1)[1])
            self.assertEqual(payload["challenge_hint"], "Which drawdown rule applies?")
            tool, = tools
            self.assertEqual(tool.name, "select_audit_challenge")
            tool.handler("toggle_loss_metric")
            record("tool", tool_name=tool.name, status="success")
            return {"status": "ok", "summary": "Invented verdict ignored.", "evidence_ids": []}, "end_turn"

        selected = await run_counterfactual(self.market, robert, report, selector_runtime=StrandsAgents(invoker=invoke),
                                            challenge_hint="Which drawdown rule applies?")
        self.assertEqual(selected["selection_mode"], "agent")
        self.assertEqual(selected["status"], "verified")
        self.assertEqual(selected["option"]["id"], "toggle_loss_metric")
        self.assertEqual(selected["comparison"]["replay"]["decision_reason"], "baseline_breaches_policy")
        self.assertNotIn("Which drawdown rule applies?", json.dumps(selected))

        class FakeStatus:
            async def run(self, *_args, **_kwargs):
                return AgentRun("ok", {"status": "ok", "summary": "No real callback.", "evidence_ids": []})

        replayer = AsyncMock()
        missing = await run_counterfactual(self.market, robert, report, selector_runtime=FakeStatus(), replayer=replayer)
        self.assertEqual(missing["status"], "invalid")
        self.assertFalse(missing["verified"])
        replayer.assert_not_awaited()

    async def test_bundled_replay_preserves_the_same_comparison(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)

        async def invoke(role, prompt, tools, record):
            self.assertEqual(role, "single")
            payload = json.loads(prompt.split("\n", 1)[1])
            routes = {
                "lookup_evidence": select_tool_arguments("evidence", payload["evidence"]),
                "stress_replay": select_tool_arguments("scenario", payload["scenario"]),
            }
            for tool in tools:
                output = tool.handler(**routes.get(tool.name, {}))
                record("tool", tool_name=tool.name, status="success", output=output)
            return {"status": "ok", "summary": "A proposal to approve was ignored.", "evidence_ids": []}, "end_turn"

        option = "toggle_loss_metric"
        deterministic = await run_counterfactual(self.market, robert, report, option_id=option)
        bundled = await run_counterfactual(self.market, robert, report, option_id=option,
                                           single_runtime=SingleAgentRuntime(invoker=invoke))
        self.assertEqual(bundled["comparison"], deterministic["comparison"])
        self.assertEqual(bundled["replay"]["audit"], deterministic["replay"]["audit"])
        self.assertTrue(any(event["event"] == "tool" and event["role"] == "single" and
                            event["tool_name"] == "recheck_decision" for event in bundled["replay"]["trace"]))

    async def test_unsupported_or_duplicate_choices_release_no_comparison(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)
        replayer = AsyncMock()
        unsupported = await run_counterfactual(self.market, robert, report, option_id="request_issuer_evidence",
                                               replayer=replayer)
        self.assertEqual(unsupported["reason"], "unsupported_selection")
        self.assertIsNone(unsupported["comparison"]["replay"])

        expect_rejected = self.assertRaises
        class ConflictingSelector:
            async def run(self, role, payload, *, tools, run_id):
                tool, = tools
                tool.handler("toggle_loss_metric")
                with expect_rejected(ValueError):
                    tool.handler("tighten_reserve_floor")
                return AgentRun("ok", {"status": "ok"})

        conflict = await run_counterfactual(self.market, robert, report, selector_runtime=ConflictingSelector(),
                                            replayer=replayer)
        self.assertEqual(conflict["reason"], "unverified_selection")
        replayer.assert_not_awaited()

    async def test_tampered_replay_cannot_replace_the_audited_baseline(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)

        async def tampered(data, case, runtime, **options):
            result = await run_case(data, case, runtime, **options)
            result["policy"]["reserve_floor"] = .01
            return result

        invalid = await run_counterfactual(self.market, robert, report, option_id="toggle_loss_metric", replayer=tampered)
        self.assertEqual(invalid["reason"], "replay_not_verified")
        self.assertFalse(invalid["verified"])
        self.assertIsNone(invalid["replay"])
        self.assertEqual(report["policy"]["reserve_floor"], .15)

    async def test_nonmaterial_counterfactual_and_optout_do_not_recommend(self):
        robert, _ = examples("robert")
        report = await self.baseline(robert)
        result = await run_counterfactual(self.market, robert, report, option_id="toggle_purchase_size")
        self.assertEqual(result["status"], "no_recommendation")
        self.assertEqual(result["reason"], "no_material_change")
        self.assertTrue(result["verified"])
        self.assertFalse(result["comparison"]["differences"])

        replayer = AsyncMock()
        result = await run_counterfactual(self.market, robert, report, option_id="no_material_challenge", replayer=replayer)
        self.assertEqual(result["reason"], "challenge_declined")
        self.assertFalse(result["verified"])
        replayer.assert_not_awaited()

    async def test_an_invalid_base_audit_has_no_challenge(self):
        robert, _ = examples("robert")
        report = await self.baseline(replace(robert, tamper=True))
        self.assertEqual(counterfactual_options(report), ())
        result = await run_counterfactual(self.market, robert, report, option_id="toggle_loss_metric")
        self.assertEqual(result["reason"], "baseline_not_verified")
        self.assertFalse(result["verified"])
