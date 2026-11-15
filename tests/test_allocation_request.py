"""Verify that one historical allocation uses only its stated scope and weights."""

import unittest

from datathon.allocation_request import parse_allocation_request


class AllocationRequestTests(unittest.TestCase):
    assets = ("AGG", "GLD", "QQQ", "SPY", "ZST.TO")

    def test_accepts_one_weighted_allocation_without_a_comparator(self):
        expected = {"VOO": .20, "SPY": .30, "IVV": .10, "QQQ": .40}
        allocations = (
            "20% in VOO, 30% in SPY, 10% in IVV and 40% in QQQ",
            "VOO 20%, SPY: 30 %, IVV=10%, QQQ at 40%",
            "20% VOO,30% SPY,10% IVV,40% QQQ",
            "1. 20% of VOO\n2. 30% to SPY\n3. IVV 10%\n4. QQQ 40%",
            "VOO 20%\nSPY 30%\nIVV 10%\nQQQ 40%",
        )
        for weights in allocations:
            with self.subTest(weights=weights):
                question = (
                    "I am trying to stay diversified so I don't lose money if a fund crashes. "
                    f"Analyze my allocation of {weights}."
                )
                first = parse_allocation_request(question)
                self.assertTrue(first["needs_assets"])
                self.assertEqual(first["fields"]["weights"], expected)
                draft = parse_allocation_request(question, self.assets)
                self.assertEqual(draft["status"], "allocation")
                self.assertEqual(draft["task"], "analyze_allocation")
                self.assertFalse(draft["needs_assets"])
                self.assertEqual(draft["fields"]["weights"], expected)
                self.assertEqual(draft["fields"]["unsupported_assets"], ("VOO", "IVV"))
                self.assertTrue(weights.removeprefix("1. ") in draft["sources"]["options"])

    def test_classifies_cashtags_and_lowercase_known_symbols(self):
        question = "Replay this portfolio A: 55.25% in agg, 20.5% of $SPY, and 24.25% in GLD."
        self.assertTrue(parse_allocation_request(question)["needs_assets"])
        draft = parse_allocation_request(question, self.assets)
        self.assertEqual(draft["status"], "allocation")
        self.assertEqual(draft["fields"]["weights"], {"AGG": .5525, "SPY": .205, "GLD": .2425})
        self.assertFalse(draft["fields"]["unsupported_assets"])

    def test_separate_balance_denomination_leaves_weights_and_cap_unchanged(self):
        question = (
            "I have $42,000 in USD. Audit my allocation of 34% in AGG and 66% in QQQ. "
            "Maximum drawdown must not exceed 17.25%. Add the 2023 replay. ESG screening is required."
        )
        draft = parse_allocation_request(question, self.assets)
        self.assertEqual(draft["status"], "allocation")
        self.assertEqual(draft["fields"]["weights"], {"AGG": .34, "QQQ": .66})
        self.assertEqual(draft["fields"]["max_drawdown"], .1725)
        self.assertTrue(draft["fields"]["include_2023"])
        self.assertTrue(draft["fields"]["require_esg"])
        self.assertTrue(all(excerpt in question for excerpt in draft["sources"].values()))

    def test_ambiguity_requires_correction_instead_of_reweighting(self):
        for allocation in (
            "50% SPY and 45% AGG",
            "55% SPY and 75% AGG",
            "50% AGG and 50% AGG",
            "50% SPY or 50% AGG",
            "50% SPY, 50% AGG, or hold cash instead",
            "approximately 50% SPY and 50% AGG",
            "0% SPY and 100% AGG",
            "20% SPY 80% AGG",
            "50% in SPY, QQQ, and 50% AGG",
            "100% SPY",
        ):
            with self.subTest(allocation=allocation):
                draft = parse_allocation_request(f"Analyze my allocation of {allocation}.", self.assets)
                self.assertEqual(draft["status"], "clarify")
                self.assertFalse(draft["needs_assets"])

    def test_additional_requirements_cannot_be_silently_removed(self):
        constraints = (
            "Do not include QQQ in the results.",
            "Use a maximum drawdown of 10% and also a maximum drawdown of 19%.",
            "Forecast what I will earn next year.",
            "I need at least a 14% return.",
            "Show volatility and only use the past 3 years.",
            "Calculate the historical results in USD.",
            "Replay both holdings with monthly rebalancing.",
        )
        for condition in constraints:
            with self.subTest(condition=condition):
                question = f"Can you evaluate this allocation of 40% SPY and 60% QQQ? {condition}"
                draft = parse_allocation_request(question, self.assets)
                self.assertIn(draft["status"], {"clarify", "unsupported"})
                self.assertFalse(draft["needs_assets"])

    def test_other_intents_remain_available(self):
        for question in (
            "Compare 55% SPY and 45% AGG against 30% SPY and 70% AGG.",
            "Allocation A: 40% SPY, 60% GLD. Allocation B: 40% SPY, 60% AGG.",
            "I scored 50% on one exam and 50% on another. How should I study?",
            "I saw historical returns of 40% VOO and 60% SPY.",
            "Sell 40% of SPY and 60% of AGG for cash.",
            "What should I think about as I invest my savings?",
        ):
            with self.subTest(question=question):
                self.assertIsNone(parse_allocation_request(question, self.assets))


if __name__ == "__main__":
    unittest.main()
