"""Reject incomplete stress paths even when both window endpoints survive."""

import os
import unittest
from dataclasses import replace

from datathon.data import describe_market_coverage, load_market_data, verify_cad_conversion
from datathon.finance import BASE_WEIGHTS, STRESS_WINDOWS, StressWindow, evaluate_portfolio
from datathon.governance import audit_decision
from datathon.market_calendar import starter_calendar_coverage
from datathon.publication import publish_report
from datathon.workflow import examples, proposed_weights, run_case


class CalendarScopeTests(unittest.TestCase):
    def test_no_completeness_claim_for_unregistered_date_range(self):
        result = starter_calendar_coverage("2026-01-02", "2026-01-05", ["2026-01-02", "2026-01-05"])
        self.assertEqual(result["status"], "coverage_not_verified")
        self.assertEqual(result["reason"], "reference_calendar_unavailable")
        self.assertIsNone(result["calendar_id"])
        self.assertIsNone(result["expected_observations"])
        self.assertEqual(result["missing_dates"], [])


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
                published = publish_report(incomplete)
                self.assertEqual(published["publication"]["status"], "limited")
                self.assertFalse(published["publication"]["independent_review_verified"])
                self.assertNotIn("scenarios", published)
                coverage_input = published["publication"]["versions"]["inputs"]["market_data"]
                self.assertEqual(coverage_input["status"], "coverage_diagnostic")
                coverage = coverage_input["windows"]["2022"]["coverage"]
                self.assertEqual(coverage["status"], "incomplete")
                missing_reason = "missing_converted_price" if market is self.missing_price else "missing_fx_fixing"
                self.assertEqual(coverage["missing_dates"], [{"date": self.trough, "reason": missing_reason}])

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

    def test_calendar_coverage_has_reasoned_exclusions_and_observation_counts(self):
        extra = StressWindow("2023", "2023 replay", "2023-07-31", "2023-10-31")
        verification = verify_cad_conversion(self.market, tickers=BASE_WEIGHTS, windows=(*STRESS_WINDOWS, extra))
        windows = verification["windows"]
        self.assertEqual({key: window["observations"] for key, window in windows.items()},
                         {"2022": 244, "2025": 67, "2023": 63})
        for window in windows.values():
            coverage = window["coverage"]
            self.assertEqual(coverage["status"], "verified")
            self.assertEqual(coverage["expected_observations"], window["observations"])
            self.assertEqual(coverage["consecutive_gaps"], [])
        self.assertIn({"date": "2022-09-30", "reason": "documented_fx_exclusion"},
                      windows["2022"]["coverage"]["excluded_dates"])
        self.assertIn({"date": "2022-06-20", "reason": "documented_exchange_closure"},
                      windows["2022"]["coverage"]["excluded_dates"])

    def test_gap_reasons_and_counts_use_consecutive_expected_market_sessions(self):
        price_gap = "2022-06-17"
        fx_gap = "2022-06-21"
        broken = replace(self.market, prices={
            **self.market.prices,
            "QQQ": {day: value for day, value in self.market.prices["QQQ"].items() if day != price_gap},
        }, fx={day: value for day, value in self.market.fx.items() if day != fx_gap})
        result = describe_market_coverage(broken, tickers=BASE_WEIGHTS, windows=STRESS_WINDOWS)
        first = result["windows"]["2022"]
        self.assertEqual(first["coverage"]["status"], "incomplete")
        self.assertEqual(first["observations"], 242)
        self.assertEqual(first["coverage"]["expected_observations"], 244)
        self.assertEqual(first["coverage"]["missing_dates"], [
            {"date": price_gap, "reason": "missing_converted_price"},
            {"date": fx_gap, "reason": "missing_fx_fixing"},
        ])
        self.assertEqual(first["coverage"]["consecutive_gaps"],
                         [{"start": price_gap, "end": fx_gap, "observations": 2}])
        self.assertEqual(result["windows"]["2025"]["coverage"]["status"], "verified")
