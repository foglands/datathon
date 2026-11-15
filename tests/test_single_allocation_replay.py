"""Verify single-allocation replay, review, and substitute input provenance."""

import unittest
from dataclasses import replace

from datathon.allocation_compare import analyze_allocation, compare_allocations, publish_allocation_comparison
from tests.test_allocation_compare import _fixture


class SingleAllocationReplayTests(unittest.TestCase):
    def setUp(self):
        self.market = _fixture()
        self.weights = {"HIGHER_RETURN": .50, "LOWER_DRAWDOWN": .50}

    def test_mixed_allocation_returns_verified_metrics_without_a_relative_winner(self):
        report = publish_allocation_comparison(analyze_allocation(self.market, self.weights, max_drawdown=.13))
        self.assertEqual(report["kind"], "single_allocation")
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["finding"]["basis"], "single_allocation")
        self.assertIsNone(report["finding"]["option"])
        self.assertIsNone(report["priority"])
        allocation = report["options"]["Proposed allocation"]
        self.assertEqual(allocation["weights"], self.weights)
        self.assertEqual(allocation["max_drawdown_test"], "fail")
        for row in allocation["windows"].values():
            self.assertAlmostEqual(row["terminal_return"], .14)
            self.assertAlmostEqual(row["max_drawdown"], .14)
        self.assertTrue(report["verification"]["review_id"])

    def test_limited_and_tampered_reports_preserve_the_review_boundary(self):
        report = analyze_allocation(self.market, self.weights, include_2023=True, require_esg=True)
        published = publish_allocation_comparison(report)
        self.assertEqual(published["status"], "limited")
        self.assertEqual(published["finding"]["basis"], "esg_unassessed")
        self.assertEqual(set(published["verification"]["windows"]), {"2022", "2023", "2025"})
        report["options"]["Proposed allocation"]["windows"]["2022"]["max_drawdown"] = 0.01
        held = publish_allocation_comparison(report)
        self.assertEqual(held["status"], "withheld")
        self.assertFalse(held["options"])
        self.assertEqual(held["kind"], "single_allocation")

    def test_proxy_scope_is_checked_against_replayed_weights(self):
        prices = {"SPY": self.market.prices["HIGHER_RETURN"], "QQQ": self.market.prices["LOWER_DRAWDOWN"]}
        sources = tuple((name, content.replace("HIGHER_RETURN", "SPY").replace("LOWER_DRAWDOWN", "QQQ"))
                        for name, content in self.market.source_csvs)
        market = replace(self.market, prices=prices, source_csvs=sources)
        weights = {"SPY": .75, "QQQ": .25}
        report = analyze_allocation(market, weights)
        context = {
            "requested_weights": {"VOO": .25, "SPY": .25, "IVV": .25, "QQQ": .25},
            "proxy_substitutions": {"VOO": "SPY", "IVV": "SPY"},
        }
        published = publish_allocation_comparison(report, replay_context=context)
        self.assertEqual(published["status"], "verified")
        self.assertEqual(published["replay_context"], context)
        self.assertEqual(published["options"]["Proposed allocation"]["weights"], weights)

        context["requested_weights"] = {"VOO": .25, "SPY": .50, "IVV": .25}
        context["proxy_substitutions"]["VOO"] = "QQQ"
        self.assertEqual(published["replay_context"]["proxy_substitutions"], {"VOO": "SPY", "IVV": "SPY"})
        unsupported_proxy = publish_allocation_comparison(report, replay_context=context)
        self.assertEqual(unsupported_proxy["status"], "withheld")
        self.assertFalse(unsupported_proxy["options"])
        self.assertIn("benchmark objectives", unsupported_proxy["reason"])

        context["proxy_substitutions"]["VOO"] = "SPY"
        mismatched_weights = publish_allocation_comparison(report, replay_context=context)
        self.assertEqual(mismatched_weights["status"], "withheld")
        self.assertFalse(mismatched_weights["options"])

    def test_comparisons_still_require_two_choices(self):
        with self.assertRaisesRegex(ValueError, "exactly two"):
            compare_allocations(self.market, {"Only choice": self.weights})
        with self.assertRaisesRegex(ValueError, "total 100%"):
            analyze_allocation(self.market, {"HIGHER_RETURN": .98})
