"""Check benchmark accounting without running a model or claiming model performance."""

import csv
import io
import os
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun
from datathon.challenge_benchmark import (
    ABSTAIN, CHALLENGE_CASES, EXPANDED_CASES, LIVE_ARMS, OFFICIAL_STARTER_SHA256, Outcome,
    evaluate, fingerprint, fixed_option, latency, run_benchmark, score,
)
from datathon.counterfactual import run_counterfactual
from datathon.data import _csv_texts, load_market_data
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

    async def test_missing_official_fx_endpoint_never_enters_selection_denominator(self):
        case = next(case for case in EXPANDED_CASES if case.omitted_fx_date)
        selector = _RecordedSelection("toggle_loss_metric")
        report = await evaluate(MARKET, case, "fixed", "", "", selector_runtime=selector)
        self.assertIn(case.omitted_fx_date, MARKET.fx)
        self.assertIsNone(selector.payload)
        self.assertTrue(report["resilience_pass"])
        self.assertIsNone(report["choice_correct"])
        self.assertEqual(report["replay_attempts"], 0)
        self.assertFalse(report["unsafe_release"])

        args = SimpleNamespace(data=Path("official.zip"), cohort="expanded", case=[case.id], repeats=1, jobs=1,
                               mode="offline", model="unused", region="unused", code_ref="fixture")
        with patch("datathon.challenge_benchmark.fingerprint", return_value=OFFICIAL_STARTER_SHA256), \
                patch("datathon.challenge_benchmark.load_market_data", return_value=MARKET):
            aggregate = await run_benchmark(args)
        self.assertEqual(aggregate["summary"], {})
        self.assertEqual(aggregate["resilience_summary"]["fixed"]["correct_outcome"], 1)
        self.assertNotIn("choice_correct", aggregate["resilience_summary"]["fixed"])

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

    def test_expansion_uses_new_requests_and_distinct_publication_boundaries(self):
        old_ids = {case.id for case in CHALLENGE_CASES}
        expanded_ids = {case.id for case in EXPANDED_CASES}
        self.assertFalse(old_ids & expanded_ids)
        self.assertEqual(len(expanded_ids), 11)
        self.assertEqual(sum(case.expected_reason == "no_material_change" for case in EXPANDED_CASES), 4)
        dates = {"issuer_filings_tomorrow": "2026-08-27", "issuer_same_day_available": "2026-08-28",
                 "issuer_at_age_cutoff": "2026-09-28"}
        self.assertEqual({case.id: case.evidence_date for case in EXPANDED_CASES if case.id in dates}, dates)
        self.assertEqual((date.fromisoformat(dates["issuer_at_age_cutoff"]) - date(2026, 6, 30)).days, 90)

    def test_gold_spans_each_supported_challenge_and_p95_uses_nearest_rank(self):
        self.assertEqual(len({case.id for case in CHALLENGE_CASES}), len(CHALLENGE_CASES))
        self.assertEqual(len({case.expected_option for case in CHALLENGE_CASES}), 6)
        self.assertTrue(all(isinstance(case.before, Outcome) and case.paired_bps for case in CHALLENGE_CASES))
        self.assertEqual(latency([{"ms": index} for index in range(1, 21)], "ms"), {"p50": 10.5, "p95": 19})


@skipUnless(os.getenv("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH to the official starter.")
class ExpandedOfficialDataTests(IsolatedAsyncioTestCase):
    async def test_all_forced_choices_match_frozen_gold_on_official_inputs(self):
        starter = Path(os.environ["DATATHON_STARTER_PATH"])
        self.assertEqual(fingerprint(starter), OFFICIAL_STARTER_SHA256)
        data = load_market_data(starter)
        for case in EXPANDED_CASES:
            with self.subTest(case=case.id):
                observed = await evaluate(data, case, "fixed", "", "",
                                          selector_runtime=_RecordedSelection(case.expected_option))
                self.assertTrue(observed["correct_outcome"])
                self.assertEqual(observed["expected_paired_basis_points"], observed["observed_paired_basis_points"])

    def test_loss_frontiers_match_independent_decimal_endpoint_calculation(self):
        texts = _csv_texts(Path(os.environ["DATATHON_STARTER_PATH"]))
        fx = {row["date"]: Decimal(row["usdcad"])
              for row in csv.DictReader(io.StringIO(texts["fx_usdcad_daily.csv"]))}
        weights = {ticker: Decimal(weight) for ticker, weight in
                   {"SPY": ".35", "XIU.TO": ".25", "QQQ": ".20", "ZST.TO": ".20", "NVDA": "0"}.items()}
        endpoints = (("2021-12-31", "2022-12-30"), ("2024-12-31", "2025-04-08"))
        endpoint_dates = {day for period in endpoints for day in period}
        prices = {
            (row["ticker"], row["date"]): Decimal(row["adj_close"]) *
            (fx[row["date"]] if row["currency"] == "USD" else 1)
            for row in csv.DictReader(io.StringIO(texts["prices_daily.csv"]))
            if row["ticker"] in weights and row["date"] in endpoint_dates
        }
        for name in ("thin_loss_margin", "reserve_already_dominated"):
            with self.subTest(case=name):
                case = next(case for case in EXPANDED_CASES if case.id == name)
                target, limit = Decimal(case.profile.target_bps) / 10_000, Decimal(case.profile.limit_bps) / 10_000
                remaining = target
                for start, end in endpoints:
                    growth = {ticker: prices[ticker, end] / prices[ticker, start] for ticker in weights}
                    hold_end = sum(weights[ticker] * growth[ticker] for ticker in weights)
                    qqq_only_end = hold_end + target * (growth["NVDA"] - growth["QQQ"])
                    self.assertGreaterEqual(qqq_only_end, 1 - limit)
                    marginal_drop = growth["ZST.TO"] - growth["QQQ"]
                    if marginal_drop > 0:
                        remaining = min(remaining, (qqq_only_end - (1 - limit)) / marginal_drop)
                gold = next(pair[1] for pair in case.paired_bps if pair[0] == "full_zst_max")
                self.assertEqual(round(10_000 * remaining), gold)


if __name__ == "__main__":
    import unittest
    unittest.main()
