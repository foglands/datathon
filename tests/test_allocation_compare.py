"""Regression coverage for the profile-driven portfolio comparison release."""

import unittest
from dataclasses import replace

from datathon.allocation_compare import compare_allocations, comparison_assets, publish_allocation_comparison
from datathon.data import MarketData
from datathon.finance import STRESS_WINDOWS
from datathon.market_calendar import starter_replay_sessions
from datathon.scope import EXTRA_WINDOW


def _fixture():
    paths = {"HIGHER_RETURN": {}, "LOWER_DRAWDOWN": {}}
    for window in (*STRESS_WINDOWS, EXTRA_WINDOW):
        dates = sorted(starter_replay_sessions(window.start, window.end))
        for ticker, low, finish in (("HIGHER_RETURN", 76, 125), ("LOWER_DRAWDOWN", 96, 103)):
            paths[ticker].update(dict.fromkeys(dates, float(finish)))
            paths[ticker][dates[0]] = 100.0
            paths[ticker][dates[1]] = float(low)
    fx = dict.fromkeys(paths["HIGHER_RETURN"], 1.3)
    metadata = {"file": "prices_daily.csv", "source": "Fixture", "source_url": "https://example.com/prices",
                "retrieved_on": "2026-11-15"}
    source_csvs = (
        ("prices_daily.csv", "ticker,date,adj_close,currency\n" + "".join(
            f"{ticker},{date},{price},CAD\n" for ticker, rows in paths.items() for date, price in rows.items()
        )),
        ("fx_usdcad_daily.csv", "date,usdcad\n" + "".join(f"{day},{rate}\n" for day, rate in fx.items())),
        ("sources_metadata.csv", ",".join(metadata) + "\n" + ",".join(metadata.values()) + "\n"),
    )
    return MarketData(paths, fx, (metadata,), official_starter=True, source_csvs=source_csvs)


class AllocationCompareTests(unittest.TestCase):
    def setUp(self):
        self.market = _fixture()
        self.options = {"A": {"HIGHER_RETURN": 1.0}, "B": {"LOWER_DRAWDOWN": 1.0}}

    def test_profile_priority_changes_finding_on_identical_confirmed_options(self):
        return_comparison = compare_allocations(self.market, self.options, priority="terminal_return")
        loss_comparison = compare_allocations(self.market, self.options, priority="max_drawdown")
        self.assertEqual(comparison_assets(self.market, include_2023=True), ("HIGHER_RETURN", "LOWER_DRAWDOWN"))
        self.assertEqual(return_comparison["status"], "verified")
        self.assertEqual(return_comparison["finding"]["option"], "A")
        self.assertEqual(loss_comparison["finding"]["option"], "B")
        for label, (ret, risk) in {"A": (.25, .24), "B": (.03, .04)}.items():
            for values in return_comparison["options"][label]["windows"].values():
                self.assertAlmostEqual(values["terminal_return"], ret)
                self.assertAlmostEqual(values["max_drawdown"], risk)
        self.assertEqual(set(return_comparison["verification"]["windows"]), {"2022", "2025"})

    def test_binding_cap_and_unassessed_esg_gate_overall_finding(self):
        checked = compare_allocations(self.market, self.options, priority="terminal_return", max_drawdown=.10)
        self.assertEqual(checked["options"]["A"]["max_drawdown_test"], "fail")
        self.assertEqual(checked["finding"]["basis"], "cap_pass")
        self.assertEqual(checked["finding"]["option"], "B")
        screened = compare_allocations(self.market, self.options, priority="terminal_return",
                                      max_drawdown=.10, include_2023=True, require_esg=True)
        self.assertEqual(screened["status"], "limited")
        self.assertEqual(screened["requirements"]["esg"]["status"], "unassessed")
        self.assertIsNone(screened["finding"]["option"])
        self.assertEqual(set(screened["options"]["A"]["windows"]), {"2022", "2023", "2025"})

    def test_neutral_comparison_keeps_metrics_and_checks_an_explicit_limit(self):
        neutral = publish_allocation_comparison(compare_allocations(self.market, self.options))
        self.assertEqual(neutral["status"], "verified")
        self.assertEqual(neutral["finding"]["status"], "neutral")
        self.assertEqual(neutral["finding"]["basis"], "no_priority")
        self.assertIsNone(neutral["finding"]["option"])
        self.assertIsNone(neutral["options"]["A"]["priority_value"])
        self.assertAlmostEqual(neutral["options"]["A"]["windows"]["2022"]["max_drawdown"], .24)

        one_passes = compare_allocations(self.market, self.options, max_drawdown=.10)
        self.assertEqual(one_passes["finding"]["basis"], "cap_pass")
        self.assertEqual(one_passes["finding"]["option"], "B")
        both_breach = compare_allocations(self.market, self.options, max_drawdown=.01)
        self.assertEqual(both_breach["finding"]["basis"], "all_breach_cap")
        self.assertIsNone(both_breach["finding"]["option"])

    def test_unverified_prices_or_mutated_reports_have_no_published_metrics(self):
        report = compare_allocations(self.market, self.options, priority="terminal_return")
        self.assertEqual(publish_allocation_comparison(report)["status"], "verified")
        report["options"]["A"]["windows"]["2022"]["terminal_return"] = .99
        self.assertEqual(publish_allocation_comparison(report)["options"], {})

        asset = "HIGHER_RETURN"
        dates = self.market.prices[asset].copy()
        dates[STRESS_WINDOWS[0].start] *= 2
        altered = replace(self.market, prices={**self.market.prices, asset: dates})
        held = compare_allocations(altered, self.options, priority="max_drawdown")
        self.assertEqual(publish_allocation_comparison(held)["status"], "withheld")
        self.assertEqual(held["options"], {})
