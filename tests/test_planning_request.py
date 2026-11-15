import unittest

from datathon.planning_request import parse_planning_request


class PlanningRequestTests(unittest.TestCase):
    def test_open_ended_baby_expenses_question_retains_the_stated_tradeoffs(self):
        question = (
            "My bank account holds $72,000, and inflation has been on my mind. "
            "I've heard about gold and S&P 500 ETFs. I would like to earn extra income for my baby's childcare. "
            "I lost money in a previous fund, and I am worried about another market crash. "
            "How should I invest these savings?"
        )
        draft = parse_planning_request(question)
        self.assertEqual(draft["instruments"], ("sp500", "gold"))
        points = draft["points"]
        self.assertEqual(points["amount"], "$72,000")
        self.assertIn("baby's childcare", points["spending"])
        self.assertIn("inflation", points["inflation"])
        self.assertIn("extra income", points["growth"])
        self.assertIn("worried about another market crash", points["risk"])
        self.assertNotIn("currency", points)
        self.assertNotIn("timing", points)
        self.assertNotIn("loss_limit", points)
        self.assertTrue(all(excerpt in question for excerpt in points.values()))

    def test_other_goals_and_instruments_use_only_stated_currency_and_timing(self):
        question = (
            "I have CAD 25,000 in savings. I'll need this money in 11 months for tuition. "
            "Should I put it in bonds or a GIC?"
        )
        draft = parse_planning_request(question)
        self.assertEqual(draft["instruments"], ("cash_deposits", "bonds"))
        points = draft["points"]
        self.assertEqual(points["amount"], "CAD 25,000")
        self.assertEqual(points["currency"], "CAD")
        self.assertIn("tuition", points["spending"])
        self.assertIn("11 months", points["timing"])

    def test_chinese_planning_intake(self):
        question = "我有8万加币存款，要兼顾宝宝的开销和通胀，之前亏过钱，半年后要用钱。我该不该买标普500 ETF或黄金？"
        draft = parse_planning_request(question)
        self.assertEqual(draft["instruments"], ("sp500", "gold"))
        points = draft["points"]
        self.assertEqual(points["amount"], "8万加币")
        self.assertEqual(points["currency"], "加币")
        self.assertIn("宝宝的开销", points["spending"])
        self.assertIn("半年后要用钱", points["timing"])
        self.assertTrue(all(excerpt in question for excerpt in points.values()))

    def test_execution_and_explicit_historical_requests_keep_their_routes(self):
        for question in (
            "Compare AGG and GLD. Maximum drawdown must not exceed 12%.",
            "Should I buy gold? Compare gold and stock funds by maximum drawdown.",
            "How should I invest my savings? Forecast next year's returns for gold.",
            "Add eight percentage points of NVDA by selling only ZST.TO.",
            "Should I execute the order to buy gold with my savings?",
            "We need to decide where to eat today. What are my options?",
            "Can I put all my books on one shelf?",
        ):
            with self.subTest(question=question):
                self.assertIsNone(parse_planning_request(question))

    def test_owned_balance_uses_plural_and_singular_statements(self):
        for clause in ("My cash savings are CAD 39,475.", "Our bank account total is CAD 39,475."):
            with self.subTest(clause=clause):
                plan = parse_planning_request(f"{clause} Where would you park this money?")
                self.assertEqual(plan["points"]["amount"], "CAD 39,475")
                self.assertEqual(plan["points"]["currency"], "CAD")

    def test_multiple_unattributed_amounts_do_not_become_the_investment_budget(self):
        draft = parse_planning_request("I owe $6,000 and someone offered $20,000. Should I buy gold?")
        self.assertEqual(draft["instruments"], ("gold",))
        self.assertNotIn("amount", draft["points"])

    def test_unknown_timing_and_denied_concern_stay_unstated(self):
        draft = parse_planning_request(
            "I am not worried about losses. My withdrawal date is unknown. Is gold a good investment?"
        )
        self.assertEqual(draft["instruments"], ("gold",))
        self.assertNotIn("risk", draft["points"])
        self.assertNotIn("timing", draft["points"])

    def test_mixed_question_keeps_concentration_and_guarantee_as_context(self):
        question = (
            "I worked for four years and saved $38,000. I'm new to investing. My colleagues trade tech stocks, "
            "options, and crypto. I want financial independence. Can I put all $38k into Bitcoin or Nvidia? "
            "Is there anything that guarantees a 24% return each year?"
        )
        draft = parse_planning_request(question)
        self.assertEqual(draft["instruments"], ("individual_stock", "crypto", "options"))
        self.assertEqual(draft["examples"], ("NVDA", "BTC-USD"))
        points = draft["points"]
        self.assertEqual(points["amount"], "$38,000")
        self.assertIn("all $38k", points["concentration"])
        self.assertIn("24% return", points["return_claim"])
        self.assertIn("colleagues", points["peer_trading"])
        self.assertNotIn("timing", points)
        self.assertNotIn("currency", points)

    def test_standalone_return_claim_routes_to_education_without_fabricating_a_product(self):
        draft = parse_planning_request("Can you recommend a guaranteed 18% annual return?")
        self.assertIn("18% annual return", draft["points"]["return_claim"])
        self.assertFalse(draft["examples"])
        self.assertIsNone(parse_planning_request("Forecast next year's return for BTC-USD and guarantee a 20% return."))
