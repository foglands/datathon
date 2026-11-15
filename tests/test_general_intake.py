"""Exercise the shared intake with reproducible, independently assembled questions."""

import random
import unittest

from datathon.question_intake import analyze_question


_ASSETS = ("AGG", "GLD", "QQQ", "SPY", "XIU.TO", "ZST.TO", "BTC-USD")
_SEEDS = (17, 104, 609)
_PLANNING = {
    "en": {
        "cash": (
            ("My savings account has {amount}", "${value:,}", None),
            ("I have {amount} in cash savings", "CAD {value:,}", "CAD"),
            ("There is {amount} left in our bank account", "USD {value:,}", "USD"),
        ),
        "goals": (
            "Some of this is for tuition",
            "I want a cushion for daycare payments",
            "I am putting money aside for a down payment",
        ),
        "risks": (
            "A sharp drop would leave me short for rent",
            "I'd lose sleep if the balance dropped",
            "I have lost money in a fund before",
            "I am worried about a market crash",
        ),
        "choices": (
            ("For now I am weighing term deposits and index funds", {"cash_deposits", "equity_funds"}),
            ("My shortlist is bonds or crypto", {"bonds", "crypto"}),
            ("I'm looking at tech stocks and Treasury bills", {"individual_stock", "bonds"}),
        ),
        "questions": (
            "Which of these makes more sense for me?",
            "Help me weigh my choices",
            "Would you lean toward one for my situation?",
            "How do I get started investing?",
        ),
        "separator": (". ", "; ", "\n"),
    },
    "zh": {
        "cash": (
            ("我手头有{amount}存款", "{value}加元", "加元"),
            ("我的银行账户还剩{amount}", "{value}美元", "美元"),
            ("我的现金余额大概有{amount}", "{value}元人民币", "人民币"),
        ),
        "goals": (
            "这笔钱的一部分要用来付学费",
            "我想给房租支出留些余地",
            "我攒钱是为了付首付",
        ),
        "risks": (
            "我担心一旦大跌就付不起学费",
            "我已经亏过钱了",
            "我害怕再遇到市场暴跌",
        ),
        "choices": (
            ("我在考虑指数基金和定期存款", {"equity_funds", "cash_deposits"}),
            ("目前想在债券和加密货币之间选", {"bonds", "crypto"}),
            ("同事在交易期权，我也在看科技股", {"options", "individual_stock"}),
        ),
        "questions": (
            "这些选项我怎么选才合适？",
            "这几种放法对我来说有什么取舍？",
            "该从哪里着手？",
            "我该如何配置？",
        ),
        "separator": ("。", "；", "\n"),
    },
}


def _compose(clauses, separator, rng):
    """Change clause order and boundaries independently of the expected decision."""
    ordered = list(clauses)
    rng.shuffle(ordered)
    pieces = []
    for part in ordered[:-1]:
        boundary = separator
        if part.endswith(("?", "？")) and separator != "\n":
            boundary = " " if separator.isascii() else ""
        pieces.extend((part, boundary))
    last = ordered[-1]
    if not last.endswith(("?", "？")):
        last += "." if separator.isascii() else "。"
    return "".join([*pieces, last])


class GeneralIntakeTests(unittest.TestCase):
    def test_composed_planning_questions_keep_stated_money_goal_and_risk(self):
        for language, variants in _PLANNING.items():
            for seed in _SEEDS:
                rng = random.Random(seed)
                for index in range(12):
                    money, formatting, currency = variants["cash"][index % len(variants["cash"])]
                    amount = formatting.format(value=rng.randrange(15_100, 86_000, 25))
                    cash = money.format(amount=amount)
                    goal = rng.choice(variants["goals"])
                    risk = variants["risks"][index % len(variants["risks"])]
                    choice, instruments = rng.choice(variants["choices"])
                    question = _compose(
                        (cash, goal, risk, choice, variants["questions"][index % len(variants["questions"])]),
                        rng.choice(variants["separator"]), rng,
                    )
                    with self.subTest(language=language, seed=seed, index=index, question=question):
                        result = analyze_question(question, _ASSETS)
                        self.assertEqual(result["status"], "planning")
                        draft = result["plan"]
                        self.assertEqual(set(draft["instruments"]), instruments)
                        points = draft["points"]
                        self.assertEqual(points["amount"], amount)
                        self.assertEqual(points.get("currency"), currency)
                        self.assertIn(goal, points["spending"])
                        self.assertIn(risk, points["risk"])
                        self.assertNotIn("timing", points)
                        self.assertNotIn("return_claim", points)
                        self.assertTrue(all(excerpt in question for excerpt in points.values()))

    def test_context_substitutions_change_only_the_stated_fact(self):
        cases = (
            ("My savings account has $41,500", "My savings account has CAD 63,250", "amount"),
            ("Some of this is for tuition", "I am putting money aside for a down payment", "spending"),
            ("I am worried about a market crash", "I am not worried about a market crash", "risk"),
        )
        base = (
            "My savings account has $41,500",
            "Some of this is for tuition",
            "I am worried about a market crash",
            "I'm looking at index funds and bonds",
            "Could you walk me through the trade-offs?",
        )
        for seed in _SEEDS:
            before = _compose(base, ". ", random.Random(seed))
            before_result = analyze_question(before, _ASSETS)
            self.assertEqual(before_result["status"], "planning")
            baseline = before_result["plan"]["points"]
            for original, replacement, expected_change in cases:
                updated = tuple(replacement if fact == original else fact for fact in base)
                after = _compose(updated, ". ", random.Random(seed))
                with self.subTest(seed=seed, changed=expected_change):
                    result = analyze_question(after, _ASSETS)
                    self.assertEqual(result["status"], "planning")
                    self.assertEqual(result["plan"]["instruments"], before_result["plan"]["instruments"])
                    points = result["plan"]["points"]
                    if expected_change == "amount":
                        self.assertEqual(points["amount"], "CAD 63,250")
                        self.assertEqual(points["currency"], "CAD")
                    elif expected_change == "risk":
                        self.assertNotIn("risk", points)
                    else:
                        self.assertIn(replacement, points["spending"])
                    for unchanged in {"amount", "spending", "risk"} - {expected_change}:
                        self.assertEqual(points[unchanged], baseline[unchanged])

    def test_third_party_amounts_and_preferences_stay_separate(self):
        reported = (
            "My coworker has $31,500 in savings",
            "My coworker is worried about a market crash",
            "My coworker needs the money for tuition",
        )
        own = "My bank account has CAD 43,700"
        choice = "I am considering term deposits and index funds. Which makes more sense for me?"
        for seed in _SEEDS:
            for own_amount in (None, own):
                clauses = (*reported, choice) if own_amount is None else (*reported, choice, own_amount)
                question = _compose(clauses, ". ", random.Random(seed))
                with self.subTest(seed=seed, own_amount=own_amount):
                    result = analyze_question(question, _ASSETS)
                    self.assertEqual(result["status"], "planning")
                    points = result["plan"]["points"]
                    self.assertEqual(points.get("amount"), "CAD 43,700" if own_amount else None)
                    self.assertNotIn("risk", points)
                    self.assertNotIn("spending", points)

    def test_composed_guarantee_questions_preserve_the_claim_in_context(self):
        questions = (
            "Can anything guarantee a {rate}% annual return?",
            "Is a guaranteed {rate}% yield actually possible?",
            "Are any investments assured to earn {rate}% in annual returns?",
            "有没有产品可以保证每年有{rate}%的回报？",
            "有人说可以承诺{rate}%年化收益，靠谱吗？",
        )
        for seed in _SEEDS:
            rng = random.Random(seed)
            for template in questions:
                rate = rng.randrange(9, 40)
                question = template.format(rate=rate)
                with self.subTest(seed=seed, question=question):
                    result = analyze_question(question, _ASSETS)
                    self.assertEqual(result["status"], "planning")
                    plan = result["plan"]
                    points = plan["points"]
                    self.assertIn(f"{rate}%", points["return_claim"])
                    self.assertIn(points["return_claim"], question)
                    self.assertNotIn("amount", points)
                    self.assertNotIn("timing", points)
                    self.assertFalse(plan["examples"])

    def test_composed_comparisons_bind_two_assets_and_the_exact_cap(self):
        formats = (
            ("Compare {first} with {second}", "Maximum drawdown must not exceed {cap}%"),
            ("Which performed better, {first} or {second}", "Limit maximum drawdown to {cap}%"),
            ("比较 {first} 和 {second}", "最大回撤不能超过{cap}%"),
            ("对比 {first} 与 {second}", "最大回撤上限为{cap}%"),
        )
        for seed in _SEEDS:
            rng = random.Random(seed)
            for request, limit in formats:
                first, second = rng.sample(_ASSETS, 2)
                cap = rng.randrange(5, 35)
                question = _compose(
                    (request.format(first=first, second=second), limit.format(cap=cap)), ". ", rng,
                )
                with self.subTest(seed=seed, question=question):
                    result = analyze_question(question, _ASSETS)
                    self.assertEqual(result["status"], "ready")
                    self.assertEqual(result["fields"]["first_asset"], first)
                    self.assertEqual(result["fields"]["second_asset"], second)
                    self.assertAlmostEqual(result["fields"]["max_drawdown"], cap / 100)
                    self.assertTrue(all(excerpt in question for excerpt in result["sources"].values()))

    def test_explicit_unsupported_actions_never_downgrade_to_planning(self):
        requests = (
            "Before I decide, forecast next year's returns for {ticker}",
            "Get me the live quote for {ticker} before investing",
            "Place a market order for {ticker}",
            "请预测{ticker}明年的价格",
            "给我{ticker}的实时行情",
            "请帮我直接下单买入{ticker}",
        )
        for seed in _SEEDS:
            rng = random.Random(seed)
            for request in requests:
                ticker = rng.choice(_ASSETS)
                context = "I have cash savings and want to protect my purchasing power"
                question = _compose((request.format(ticker=ticker), context), "\n", rng)
                with self.subTest(seed=seed, question=question):
                    result = analyze_question(question, _ASSETS)
                    self.assertEqual(result["status"], "unsupported")
                    self.assertFalse(result.get("plan"))

    def test_historical_requests_do_not_substitute_an_unavailable_asset(self):
        questions = (
            "Compare the terminal loss for QQQ versus $ZZTEST.",
            "比较 XIU.TO 和 $ZZTEST 的期末亏损。",
        )
        for question in questions:
            with self.subTest(question=question):
                result = analyze_question(question, _ASSETS)
                self.assertIn(result["status"], {"clarify", "unsupported"})
                self.assertFalse(result.get("plan"))
                self.assertNotIn("second_asset", result["fields"])

    def test_unrelated_requests_cannot_open_a_financial_workflow(self):
        questions = (
            "Compare the ingredients in these two bread recipes.",
            "Which shelf makes more sense for my cookbooks?",
            "Can I put all my books on one shelf?",
            "Help me decide how to split this birthday cake.",
            "比较这两种法棍面包的配方。",
            "这些雨衣我怎么选才合适？",
            "这本书的两种装订方式有什么取舍？",
        )
        for question in questions:
            with self.subTest(question=question):
                result = analyze_question(question, _ASSETS)
                self.assertNotIn(result["status"], {"planning", "ready"})
                self.assertFalse(result.get("plan"))


if __name__ == "__main__":
    unittest.main()
