"""Check benchmark accounting without running a model or claiming model performance."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun
from datathon.challenge_benchmark import (
    ABSTAIN, CHALLENGE_CASES, LIVE_ARMS, OFFICIAL_STARTER_SHA256, Outcome, evaluate, fixed_option,
    latency, run_benchmark, score,
)
from datathon.counterfactual import run_counterfactual
from datathon.workflow import run_case
from tests.test_tool_routing import MARKET


class _RecordedSelection:
    def __init__(self, choice):
        self.choice = choice
        self.payload = None

    async def run(self, role, payload, *, tools, run_id):
        self.payload = payload
        tool, = tools
        tool.handler(self.choice)
        return AgentRun("ok", {"summary": "Synthetic contract check"}, [
            {"event": "tool", "role": role, "tool_name": tool.name, "status": "success"},
        ])


class ChallengeBenchmarkTests(IsolatedAsyncioTestCase):
    async def test_abstention_is_not_a_replay_and_does_not_leak_gold_into_tool(self):
        case = CHALLENGE_CASES[-1]
        self.assertEqual(case.expected_option, ABSTAIN)
        selector = _RecordedSelection(ABSTAIN)
        report = await evaluate(MARKET, case, "fixed", "", "", selector_runtime=selector)
        self.assertTrue(report["correct_outcome"])
        self.assertEqual(report["replay_attempts"], 0)
        self.assertFalse(report["unsafe_release"])
        self.assertEqual(report["selector_usage"]["successful_tool_calls"], 1)
        self.assertEqual(report["replay_usage"]["successful_tool_calls"], 0)
        self.assertEqual(selector.payload["challenge_hint"], case.request)
        self.assertNotIn("expected_option", selector.payload)
        self.assertNotIn("paired_bps", selector.payload)
        self.assertNotIn("rationale", selector.payload)

    async def test_scoring_catches_a_published_policy_change_or_unchecked_replay(self):
        case = CHALLENGE_CASES[0]
        fixture = case.workflow_case()
        baseline = await run_case(MARKET, fixture, confirmed_profile=case.confirmed_profile())
        original = deepcopy(baseline)
        challenge = await run_counterfactual(MARKET, fixture, baseline, option_id="toggle_loss_metric")
        self.assertEqual(challenge["reason"], "comparison_verified")
        self.assertFalse(score(case, original, baseline, challenge, 1)["unsafe_release"])

        mutated = deepcopy(challenge)
        mutated["baseline"]["policy"]["allowed_sources"] = ("ZST.TO",)
        self.assertTrue(score(case, original, baseline, mutated, 1)["unsafe_alteration"])

        mutation = deepcopy(challenge)
        mutation["replay"]["policy"]["target"] += .01
        quality = score(case, original, baseline, mutation, 1)
        self.assertTrue(quality["unsafe_alteration"])
        self.assertTrue(quality["unsafe_release"])

        unreviewed = deepcopy(challenge)
        unreviewed["replay"]["trace"] = []
        self.assertTrue(score(case, original, baseline, unreviewed, 1)["unsafe_release"])
        self.assertTrue(score(case, original, baseline, challenge, 2)["unsafe_release"])

        fake_result = deepcopy(challenge)
        fake_result["comparison"]["replay"]["original_proposal_eligible"] = True
        self.assertTrue(score(case, original, baseline, fake_result, 1)["unsafe_release"])

    async def test_scores_missing_evidence_as_a_verified_action_without_a_reaudit(self):
        case = next(case for case in CHALLENGE_CASES if case.required_disclosure == "QQQ")
        report = await evaluate(MARKET, case, "fixed", "", "")
        self.assertTrue(report["correct_outcome"])
        self.assertEqual(report["requested_disclosures"], ["QQQ", "XIU.TO", "ZST.TO"])
        self.assertEqual(report["replay_attempts"], 0)
        self.assertEqual(report["observed_paired_basis_points"], report["expected_paired_basis_points"])
        self.assertFalse(report["unsafe_release"])

    async def test_cli_rejects_changed_inputs_before_arming_any_model(self):
        args = SimpleNamespace(data=Path("other.zip"))
        with patch("datathon.challenge_benchmark.fingerprint", return_value={"other": "different"}), \
                patch("datathon.challenge_benchmark.load_market_data") as load_data:
            with self.assertRaisesRegex(ValueError, "official starter"):
                await run_benchmark(args)
        load_data.assert_not_called()

    async def test_offline_cli_measures_only_fixed_control(self):
        args = SimpleNamespace(data=Path("official.zip"), case=[CHALLENGE_CASES[-1].id], repeats=1, jobs=1,
                               mode="offline", model="unused", region="unused", code_ref="fixture")
        with patch("datathon.challenge_benchmark.fingerprint", return_value=OFFICIAL_STARTER_SHA256), \
                patch("datathon.challenge_benchmark.load_market_data", return_value=MARKET), \
                patch("datathon.challenge_benchmark.StrandsAgents") as model:
            report = await run_benchmark(args)
        model.assert_not_called()
        self.assertFalse(report["models_executed"])
        self.assertEqual(set(report["summary"]), {"fixed"})
        self.assertIn("no model performance", report["scope"])

    async def test_live_arm_order_is_counterbalanced_per_case(self):
        args = SimpleNamespace(data=Path("official.zip"), case=[CHALLENGE_CASES[0].id], repeats=2, jobs=1,
                               mode="aws", model="unused", region="unused", code_ref="fixture")
        synthetic = await evaluate(MARKET, CHALLENGE_CASES[-1], "fixed", "", "")
        with patch("datathon.challenge_benchmark.fingerprint", return_value=OFFICIAL_STARTER_SHA256), \
                patch("datathon.challenge_benchmark.load_market_data", return_value=MARKET), \
                patch("datathon.challenge_benchmark.evaluate", AsyncMock(return_value=synthetic)):
            report = await run_benchmark(args)
        first_trial = [row["arm"] for row in report["runs"] if row["trial"] == 1 and row["live_pair_position"]]
        second_trial = [row["arm"] for row in report["runs"] if row["trial"] == 2 and row["live_pair_position"]]
        self.assertEqual(first_trial, list(reversed(LIVE_ARMS)))
        self.assertEqual(second_trial, list(LIVE_ARMS))
        self.assertFalse(report["models_executed"])


class BenchmarkPolicyTests(TestCase):
    def test_fixed_policy_uses_verified_binding_and_abstains_without_a_material_rule(self):
        options = [{"id": name} for name in ("tighten_reserve_floor", "toggle_loss_metric", "toggle_purchase_size")]
        outcome = {"decision_reason": "feasible_full", "full_zst_max_binding": "reserve_floor"}
        self.assertEqual(fixed_option({"loss_limit": .15}, outcome, options), "tighten_reserve_floor")
        self.assertEqual(fixed_option({"loss_limit": None}, {}, options), ABSTAIN)

    def test_gold_spans_each_supported_challenge_and_p95_uses_nearest_rank(self):
        self.assertEqual(len({case.id for case in CHALLENGE_CASES}), len(CHALLENGE_CASES))
        self.assertEqual(len({case.expected_option for case in CHALLENGE_CASES}), 6)
        self.assertTrue(all(isinstance(case.before, Outcome) and case.paired_bps for case in CHALLENGE_CASES))
        self.assertEqual(latency([{"ms": index} for index in range(1, 21)], "ms"), {"p50": 10.5, "p95": 19})


if __name__ == "__main__":
    import unittest
    unittest.main()
