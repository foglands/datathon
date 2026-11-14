"""Reject incomplete stress paths even when both window endpoints survive."""

import os
import unittest
from dataclasses import replace

from datathon.data import load_market_data
from datathon.finance import BASE_WEIGHTS, STRESS_WINDOWS, StressWindow, evaluate_portfolio
from datathon.governance import audit_decision
from datathon.workflow import examples, proposed_weights, run_case


@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "requires the official starter data")
class StarterCalendarTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = load_market_data(os.environ["DATATHON_STARTER_PATH"])
        cls.trough = "2022-06-16"
        cls.missing_price = replace(cls.market, prices={
            ticker: {day: value for day, value in series.items() if day != cls.trough}
            for ticker, series in cls.market.prices.items()
        })
        cls.missing_fx = replace(cls.market, fx={day: value for day, value in cls.market.fx.items() if day != cls.trough})

    async def test_single_missing_trough_withholds_an_alternative(self):
        _, drawdown = examples("robert")
        case = replace(drawdown, loss_limit=.1575)
        complete = await run_case(self.market, case)
        self.assertEqual(complete["decision_reason"], "baseline_breaches_policy")
        self.assertEqual(complete["alternatives"]["status"], "no_feasible")
        windows = complete["scenarios"]["baseline"]["windows"]
        self.assertAlmostEqual(windows["2022"]["max_drawdown"], .160530175174885)
        self.assertEqual(windows["2022"]["trough_date"], self.trough)
        self.assertEqual([row["observations"] for row in windows.values()], [244, 67])

        for market in (self.missing_price, self.missing_fx):
            with self.subTest(missing="price" if market is self.missing_price else "FX"):
                incomplete = await run_case(market, case)
                self.assertEqual(incomplete["status"], "insufficient_evidence")
                self.assertEqual(incomplete["decision_reason"], "market_evidence_insufficient")
                self.assertIn(f"1 missing ({self.trough})", incomplete["explanation"])
                self.assertNotIn("alternatives", incomplete)
                self.assertFalse(incomplete["audit"]["verified"])

    def test_independent_review_requires_the_same_archived_sessions(self):
        for market in (self.missing_price, self.missing_fx):
            with self.subTest(missing="price" if market is self.missing_price else "FX"):
                audit = audit_decision(
                    prices_cad=market.prices, baseline=BASE_WEIGHTS, proposal=proposed_weights(),
                    policy={"metric": "max_drawdown", "loss_limit": .1575, "reserve_floor": .15, "target": .10,
                            "allowed_sources": ("QQQ", "ZST.TO"), "windows": STRESS_WINDOWS},
                    metrics={}, evidence={"basis": "CAD", "price_source": "starter:prices_daily.csv",
                                          "fx_source": "starter:fx_usdcad_daily.csv", "fx_dates": tuple(market.fx)},
                    official_starter=market.official_starter,
                )
                self.assertEqual(audit["status"], "insufficient_evidence")
                self.assertEqual(audit["decision_reason"], "market_evidence_insufficient")
                self.assertIn(f"1 missing ({self.trough})", audit["findings"][0]["message"])
                self.assertFalse(audit["verified"])

    def test_only_documented_fx_exclusions_are_accepted(self):
        extra_window = StressWindow("2023", "2023 replay", "2023-07-31", "2023-10-31")
        report = evaluate_portfolio(self.market, BASE_WEIGHTS, windows=(*STRESS_WINDOWS, extra_window))
        dates = {key: row["dates"] for key, row in report["windows"].items()}
        self.assertEqual({key: len(days) for key, days in dates.items()}, {"2022": 244, "2025": 67, "2023": 63})
        self.assertTrue({"2022-09-30", "2022-11-11"}.isdisjoint(dates["2022"]))
        self.assertNotIn("2023-10-02", dates["2023"])
