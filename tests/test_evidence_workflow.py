"""Verify evidence availability and the decision reason through the offline workflow."""

from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from datathon.agents import AgentRun
from datathon.data import issuer_evidence, load_market_data
from datathon.finance import STRESS_WINDOWS
from datathon.workflow import examples, preset_profile, run_case
from tests.test_tool_routing import MARKET


DECISION_DATE = "2026-11-14"
QQQ_ID = "issuer:QQQ:2026-06-30"


class EvidenceWorkflowTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("DATATHON_STARTER_PATH")
        cls.market = load_market_data(path) if path else MARKET

    def assert_historical_replay(self, report):
        windows = {window.id for window in STRESS_WINDOWS}
        for result in (report["scenarios"], report["audit"]["verified"]):
            self.assertEqual(set(result["proposal"]["windows"]), windows)
        self.assertNotIn("maximum", report["audit"]["verified"])

    def issuer_finding(self, report):
        return next(item for item in report["audit"]["findings"] if item["metric_id"] == "proposal.issuer_weight.policy")

    async def test_current_disclosures_establish_breach_with_partial_coverage(self):
        amira, = examples("amira")
        report = await run_case(self.market, amira, evidence_date=DECISION_DATE, holdings_max_age_days=180)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["decision_reason"], "issuer_evidence_insufficient")
        self.assertEqual(report["alternatives"]["status"], "insufficient_issuer_evidence")
        self.assertIn(QQQ_ID, report["evidence"]["evidence_ids"])
        finding = self.issuer_finding(report)
        self.assertEqual(finding["status"], "fail")
        self.assertAlmostEqual(finding["actual"]["lower"], .1415030546423205)
        self.assertGreater(finding["actual"]["upper"], finding["actual"]["lower"])
        self.assert_historical_replay(report)

    async def test_issuer_limit_uses_full_precision_before_display_rounding(self):
        amira, = examples("amira")
        exact_limit = await run_case(self.market, replace(amira, issuer_cap=.1415), evidence_date=DECISION_DATE)
        finding = self.issuer_finding(exact_limit)
        known_lower = finding["actual"]["lower"]
        self.assertEqual(f"{known_lower:.2%}", f"{finding['limit']:.2%}")
        self.assertGreater(known_lower, finding["limit"])
        self.assertEqual(finding["status"], "fail")

        higher_limit = await run_case(self.market, replace(amira, issuer_cap=.1416), evidence_date=DECISION_DATE)
        self.assertEqual(higher_limit["status"], "insufficient_evidence")
        self.assertEqual(self.issuer_finding(higher_limit)["status"], "insufficient_evidence")

    async def test_current_historical_replay_survives_stale_unpublished_and_missing_holdings(self):
        amira, missing_qqq = examples("amira", stress=True)
        current = await run_case(self.market, amira, evidence_date=DECISION_DATE, holdings_max_age_days=180)
        variants = (
            (amira, DECISION_DATE, 90, "stale"),
            (amira, "2026-08-27", 180, "future"),
            (missing_qqq, DECISION_DATE, 180, "unknown"),
        )
        for case, evidence_date, max_age, expected_status in variants:
            with self.subTest(evidence_date=evidence_date, max_age=max_age, status=expected_status):
                report = await run_case(self.market, case, evidence_date=evidence_date, holdings_max_age_days=max_age)
                self.assertEqual(report["status"], "insufficient_evidence")
                self.assertEqual(report["decision_reason"], "issuer_evidence_insufficient")
                self.assertNotIn(QQQ_ID, report["evidence"]["evidence_ids"])
                holding = report["evidence"]["issuer_snapshot"]["holdings"]["QQQ"]
                self.assertEqual(holding["status"], expected_status)
                self.assertIsNone(holding["weight"])
                if expected_status != "unknown":
                    self.assertTrue(holding["reason"])
                self.assertEqual(self.issuer_finding(report)["status"], "insufficient_evidence")
                self.assert_historical_replay(report)
                self.assertEqual(report["scenarios"], current["scenarios"])

    async def test_disclosure_becomes_eligible_on_publication_day(self):
        amira, = examples("amira")
        result = await run_case(self.market, amira, evidence_date="2026-08-28", holdings_max_age_days=180)
        self.assertEqual(result["status"], "fail")
        self.assertIn(QQQ_ID, result["evidence"]["evidence_ids"])

    async def test_age_limit_is_inclusive_and_based_on_holdings_observation(self):
        amira, = examples("amira")
        # 137 days separate June 30 holdings and the November 14 decision date.
        current = await run_case(self.market, amira, evidence_date=DECISION_DATE, holdings_max_age_days=137)
        stale = await run_case(self.market, amira, evidence_date=DECISION_DATE, holdings_max_age_days=136)
        self.assertIn(QQQ_ID, current["evidence"]["evidence_ids"])
        self.assertNotIn(QQQ_ID, stale["evidence"]["evidence_ids"])
        self.assertEqual(stale["evidence"]["issuer_snapshot"]["holdings"]["QQQ"]["status"], "stale")

    async def test_malformed_disclosure_is_excluded_and_market_replay_survives(self):
        amira, = examples("amira")
        snapshot = issuer_evidence()
        snapshot["holdings"]["QQQ"]["published_on"] = "unavailable"
        with patch("datathon.workflow.issuer_evidence", return_value=snapshot):
            result = await run_case(self.market, amira, evidence_date=DECISION_DATE)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["decision_reason"], "issuer_evidence_insufficient")
        self.assertNotIn(QQQ_ID, result["evidence"]["evidence_ids"])
        qqq = result["evidence"]["issuer_snapshot"]["holdings"]["QQQ"]
        self.assertEqual(qqq["status"], "invalid")
        self.assertIsNone(qqq["weight"])
        self.assertTrue(qqq["reason"])
        self.assert_historical_replay(result)

    async def test_malformed_market_endpoint_prevents_decision(self):
        robert, _ = examples("robert")
        endpoint = STRESS_WINDOWS[0].end
        missing_prices = {ticker: dict(values) for ticker, values in self.market.prices.items()}
        del missing_prices["NVDA"][endpoint]
        invalid_prices = {**self.market.prices, "NVDA": {**self.market.prices["NVDA"], endpoint: float("nan")}}
        bad_data = (
            ("missing NVDA close", replace(self.market, prices=missing_prices)),
            ("invalid NVDA close", replace(self.market, prices=invalid_prices)),
            ("invalid FX fixing", replace(self.market, fx={**self.market.fx, endpoint: 0.0})),
        )
        for failure, market in bad_data:
            with self.subTest(failure=failure):
                report = await run_case(market, robert, evidence_date=DECISION_DATE)
                self.assertEqual(report["status"], "insufficient_evidence")
                self.assertEqual(report["decision_reason"], "market_evidence_insufficient")
                self.assertFalse(report.get("alternatives"))
                self.assertNotIn("maximum", report.get("audit", {}).get("verified", {}))
                self.assertFalse(any(event["role"] == "alternatives" for event in report["trace"]))

    async def test_breached_baseline_and_disallowed_smaller_purchase_are_separate(self):
        terminal, drawdown = examples("robert")
        baseline = await run_case(self.market, drawdown, evidence_date=DECISION_DATE, holdings_max_age_days=1)
        self.assertEqual(baseline["decision_reason"], "baseline_breaches_policy")
        self.assertEqual(baseline["alternatives"]["status"], "no_feasible")
        self.assertEqual(baseline["audit"]["verified"]["baseline"]["status"], "fail")
        self.assertTrue(baseline["audit"]["verified"]["no_feasible_confirmed"])

        profile = {**preset_profile(terminal), "allowed_sources": ["ZST.TO"], "allow_smaller": False}
        exact = await run_case(self.market, terminal, confirmed_profile=AgentRun("ok", profile),
                               evidence_date=DECISION_DATE, holdings_max_age_days=1)
        self.assertEqual(exact["decision_reason"], "requested_size_infeasible")
        self.assertEqual(exact["alternatives"]["status"], "requested_size_infeasible")
        self.assertEqual(exact["audit"]["verified"]["baseline"]["status"], "pass")
        self.assertIsNone(exact["alternatives"]["frontier"]["max_total"])
        self.assertGreater(exact["alternatives"]["frontier"]["diagnostic_max_total"], 0.0)
        self.assertNotIn("maximum", exact["audit"]["verified"])
        self.assertNotIn("issuer_snapshot", exact["evidence"])
