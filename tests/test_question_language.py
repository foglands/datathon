"""Test the English-only language gate independently of financial intent."""

import unittest

from datathon.question_language import is_english_question


class QuestionLanguageTests(unittest.TestCase):
    def test_accepts_clear_english_and_short_ticker_comparisons(self):
        questions = (
            "Gold or bonds?",
            "Bitcoin or ETF?",
            "Crypto or ETFs?",
            "Savings or an ETF?",
            "Compare AGG and GLD",
            "What if I sell QQQ?",
            "AGG vs. GLD",
            "AGG & GLD: historical drawdown?",
            "Could you compare Vanguard FTSE Canada All Cap Index ETF and XIC?",
            "How should I invest in Québec?",
            "Compare National Bank of Canada with Société Générale.",
            "I’ve saved CA$42,500. Would an S&P 500 ETF suit my goals?",
        )
        for question in questions:
            with self.subTest(question=question):
                self.assertTrue(is_english_question(question))

    def test_rejects_non_english_questions_and_mixed_language(self):
        questions = (
            "AGG ou GLD",
            "Geld anlegen?",
            "Quel FNB?",
            "Investir?",
            "AGG et GLD",
            "¿Oro o bonos?",
            "Comment investir mon épargne?",
            "Comparar AGG y GLD",
            "黄金还是债券？",
            "Compare AGG and GLD. 我更在意风险。",
            "Comparez AGG et GLD. I want the lower historical loss.",
            "How do I invest? Investir?",
            "How should I invest my cash? Oro o bonos?",
        )
        for question in questions:
            with self.subTest(question=question):
                self.assertFalse(is_english_question(question))

    def test_needs_visible_question_text(self):
        for question in ("", " ", "\n\t"):
            with self.subTest(question=question):
                self.assertFalse(is_english_question(question))


if __name__ == "__main__":
    unittest.main()
