"""Check the production workflow at the published numeric boundary."""

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from datathon.agents import AgentRun
from datathon.data import load_market_data
from datathon.publication import publish_report
from datathon.sector import sector_analysis
from datathon.workflow import examples, preset_profile, run_case


@unittest.skipUnless(os.getenv("DATATHON_STARTER_PATH"), "Requires the official starter market data.")
class FinancialBoundaryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = load_market_data()

    async def test_a_shared_but_wrong_cad_price_does_not_pass_review(self):
        day = "2022-06-16"
        fx = self.market.fx[day]
        # Convert one originally USD close using the reverse exchange-rate direction.
        prices = dict(self.market.prices)
        prices["QQQ"] = {**prices["QQQ"], day: prices["QQQ"][day] / (fx * fx)}
        damaged = replace(self.market, prices=prices)
        case = replace(examples("robert")[0], search_alternatives=False)
        report = await run_case(damaged, case, confirmed_profile=AgentRun("ok", preset_profile(case)))
        public = publish_report(report)
        self.assertEqual(public["decision_reason"], "market_conversion_invalid")
        self.assertFalse(public["publication"]["independent_review_verified"])
        self.assertFalse(public["audit"]["verified"])
        self.assertNotIn("scenarios", public)

    async def test_optional_calculation_failure_leaves_original_audit_available(self):
        case = replace(examples("robert")[0], search_alternatives=False, include_sector=True)

        def wrong_sector(*args, **kwargs):
            report = sector_analysis(*args, **kwargs)
            report["sectors"]["Information Technology"]["after"]["lower"] = .99
            return report

        with patch("datathon.workflow.sector_analysis", side_effect=wrong_sector):
            report = await run_case(self.market, case, confirmed_profile=AgentRun("ok", preset_profile(case)))
        public = publish_report(report)
        self.assertTrue(public["publication"]["independent_review_verified"])
        self.assertEqual(public["status"], "fail")
        self.assertFalse(public.get("sector_analysis", {}).get("sectors"))
        self.assertAlmostEqual(public["audit"]["verified"]["proposal"]["windows"]["2022"]["max_drawdown"],
                               .20660369268865786)
        self.assertNotIn("alternatives", public)
