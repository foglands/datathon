"""Regression tests for text-grounded comparison choices and constraints."""

import unittest

from datathon.assistant_request import parse_comparison_request


ASSETS = ("AGG", "GLD", "SPY", "QQQ", "NVDA", "ZST.TO", "BTC-USD", "XIU.TO")


class ComparisonRequestTests(unittest.TestCase):
    def test_english_request_uses_an_explicit_metric_and_limit(self):
        question = "Compare QQQ and SPY by maximum drawdown. My limit is 12%."
        draft = parse_comparison_request(question, ASSETS)
        self.assertEqual(draft["status"], "ready")
        self.assertEqual(draft["fields"], {
            "first_asset": "QQQ", "second_asset": "SPY", "priority": "max_drawdown", "max_drawdown": .12,
        })
        self.assertEqual(draft["sources"]["max_drawdown"], "maximum drawdown. My limit is 12%")
        self.assertTrue(all(quote in question for quote in draft["sources"].values()))

    def test_chinese_request_carries_withdrawal_cap_and_esg(self):
        question = "比较 BTC-USD 和 XIU.TO，半年后要用钱，最大回撤不能超过12%，必须考虑ESG。"
        draft = parse_comparison_request(question, ASSETS)
        self.assertEqual(draft["status"], "ready")
        self.assertEqual(draft["fields"], {
            "first_asset": "BTC-USD", "second_asset": "XIU.TO", "objective": "Fund a planned withdrawal",
            "withdrawal_time": "Within 1 year", "max_drawdown": .12, "require_esg": True,
        })
        self.assertEqual(draft["sources"]["require_esg"], "必须考虑ESG")

    def test_allocation_weights_and_complete_quote(self):
        question = "Compare 70% AGG + 30% GLD vs 50% AGG + 50% GLD."
        draft = parse_comparison_request(question, ASSETS)
        self.assertEqual(draft["status"], "ready")
        self.assertEqual(draft["fields"]["options"], {
            "Current allocation": {"AGG": .7, "GLD": .3}, "Proposed allocation": {"AGG": .5, "GLD": .5},
        })
        self.assertEqual(draft["sources"]["options"], "70% AGG + 30% GLD vs 50% AGG + 50% GLD")

    def test_unstated_priority_is_not_replaced_with_an_assumption(self):
        for question in ("Which performed better, AGG or GLD?", "Show terminal return and maximum drawdown for AGG vs GLD."):
            with self.subTest(question=question):
                draft = parse_comparison_request(question, ASSETS)
                self.assertEqual(draft["status"], "ready")
                self.assertEqual(draft["fields"], {"first_asset": "AGG", "second_asset": "GLD"})

    def test_conflicting_or_ambiguous_instructions_do_not_release_a_draft(self):
        for question in (
            "Rank AGG vs GLD by maximum drawdown and terminal return.",
            "Compare AGG and GLD. Do not use maximum drawdown.",
            "Compare AGG and GLD and exclude AGG.",
            "Compare AGG and GLD. Only consider dividends.",
            "Compare AGG and GLD. If there is a recession, maximum drawdown must not exceed 12%.",
            "Compare AGG vs $TSM and GLD.",
            "Compare 70% AGG + 20% GLD vs 50% AGG + 50% GLD.",
            "Compare AGG and GLD. Maximum drawdown cap is 10% and maximum drawdown cap is 12%.",
            "AGG 和 GLD 哪个在历史窗口里更稳健",
        ):
            with self.subTest(question=question):
                self.assertEqual(parse_comparison_request(question, ASSETS)["status"], "clarify")

    def test_outside_scope_is_distinguished_from_a_trade_request(self):
        for question in (
            "How will AGG fare vs GLD next year?",
            "Compare volatility for AGG vs GLD.",
            "Compare AGG and GLD over the last 2 years.",
            "Compare AGG and GLD in USD.",
        ):
            with self.subTest(question=question):
                self.assertEqual(parse_comparison_request(question, ASSETS)["status"], "unsupported")
        self.assertEqual(parse_comparison_request(
            "Add exactly eight percentage points of NVDA by selling only ZST.TO.", ASSETS,
        )["status"], "unrecognized")

    def test_replay_exclusion_and_profile_preferences_are_grounded(self):
        draft = parse_comparison_request(
            "Compare AGG and GLD for long-term growth. My risk tolerance is low. Do not include 2023.", ASSETS,
        )
        self.assertEqual(draft["status"], "ready")
        self.assertEqual(draft["fields"]["objective"], "Growth")
        self.assertEqual(draft["fields"]["risk_tolerance"], "Low")
        self.assertIs(draft["fields"]["include_2023"], False)
