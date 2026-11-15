"""Verify profile-driven outcomes and confirmation at the assistant entry point."""

import os
import unittest
from unittest.mock import patch

from tests.test_app import APP, AppTest


@unittest.skipIf(AppTest is None, "Install Streamlit to run the UI tests.")
@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH for official-data UI tests.")
class InvestmentAssistantTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertFalse(self.app.exception)

    def click(self, label):
        next(button for button in self.app.button if button.label == label).click().run()
        self.assertFalse(self.app.exception)

    def confirm_profile(self, objective, horizon):
        self.app.selectbox(key="assistant_objective").set_value(objective)
        self.app.selectbox(key="assistant_horizon").set_value(horizon).run()
        self.click("Confirm profile and continue")

    def compare_assets(self, first, second):
        self.app.selectbox(key="assistant_first_asset").set_value(first)
        self.app.selectbox(key="assistant_second_asset").set_value(second).run()
        self.click("Confirm inputs and compare")
        return self.app.session_state["assistant_comparison"][1]

    def test_confirmed_context_changes_the_result_without_changing_the_assets(self):
        self.assertEqual(self.app.radio(key="workspace").value, "Investment assistant")
        self.app.selectbox(key="assistant_task").set_value("compare_allocations").run()
        self.confirm_profile("Growth", "More than 5 years")
        growth = self.compare_assets("AGG", "GLD")
        self.assertEqual(growth["priority"], "terminal_return")
        self.assertEqual(growth["finding"]["option"], "GLD")
        self.assertTrue(self.app.get("download_button"))

        self.app.selectbox(key="assistant_objective").set_value("Capital preservation").run()
        self.assertNotIn("assistant_comparison", self.app.session_state)
        self.assertFalse(self.app.get("download_button"))
        self.confirm_profile("Capital preservation", "Within 1 year")
        preservation = self.compare_assets("AGG", "GLD")
        self.assertEqual(preservation["priority"], "max_drawdown")
        self.assertEqual(preservation["finding"]["option"], "AGG")

        self.app.checkbox(key="assistant_esg").set_value(True).run()
        self.click("Confirm profile and continue")
        limited = self.compare_assets("AGG", "GLD")
        self.assertEqual(limited["status"], "limited")
        self.assertTrue(limited["options"])
        self.assertIsNone(limited["finding"]["option"])

    def test_intent_suggestion_cannot_confirm_or_run_an_analysis(self):
        proposal = {"status": "proposed", "task": "trade_audit", "trace": [], "usage": {}}
        question = "Add eight percentage points of NVDA by selling only ZST.TO."
        with patch("datathon.streamlit_assistant.suggest_intent", return_value=proposal) as suggest:
            self.app.text_area(key="assistant_question").set_value(question).run()
            self.click("Interpret with Bedrock")
            self.assertEqual(suggest.await_args.args[0], question)
            self.assertEqual(self.app.text_area(key="assistant_trade_question").value, question)
            self.assertNotIn("request_results", self.app.session_state)
            self.assertFalse(any(item.label == "Confirm inputs and compare" for item in self.app.button))

    def test_question_text_sets_options_and_cap_without_manual_form(self):
        question = "Compare AGG and GLD. Maximum drawdown must not exceed {}%."
        for cap, expected in ((12, "AGG"), (8, None)):
            self.app.text_area(key="assistant_question").set_value(question.format(cap)).run()
            self.assertFalse(self.app.get("download_button"))
            self.click("Interpret question")
            self.assertNotIn("assistant_comparison", self.app.session_state)
            self.assertFalse(any(item.label == "Investment objective" for item in self.app.selectbox))
            self.assertFalse(self.app.number_input)
            self.click("Confirm inputs and compare")
            report = self.app.session_state["assistant_comparison"][1]
            self.assertEqual(set(report["options"]), {"AGG", "GLD"})
            self.assertEqual(report["requirements"]["max_drawdown"]["limit"], cap / 100)
            self.assertEqual(report["finding"]["option"], expected)

    def test_unhandled_requirement_does_not_run_using_unrelated_form(self):
        question = "Compare AGG and GLD and forecast next month returns."
        self.app.text_area(key="assistant_question").set_value(question).run()
        self.click("Interpret question")
        self.assertTrue(self.app.warning)
        self.assertFalse(any(item.label == "Confirm inputs and compare" for item in self.app.button))
        self.assertNotIn("assistant_comparison", self.app.session_state)

    def test_question_without_profile_can_compare_neutrally(self):
        self.app.text_area(key="assistant_question").set_value("Compare AGG and GLD.").run()
        self.click("Interpret question")
        self.click("Confirm inputs and compare")
        report = self.app.session_state["assistant_comparison"][1]
        self.assertIsNone(report["priority"])
        self.assertEqual(report["finding"]["status"], "neutral")

    def test_open_ended_question_gets_planning_guidance_before_a_historical_example(self):
        question = (
            "I have $62,000 in savings. I want to keep up with inflation and cover childcare costs, "
            "but I am scared of market crashes. Should I buy an S&P 500 ETF or gold?"
        )
        self.app.text_area(key="assistant_question").set_value(question).run()
        with patch("datathon.streamlit_assistant._market_bundle", side_effect=AssertionError("Must work without market data")):
            self.click("Interpret question")
        draft, route = self.app.session_state["assistant_question_draft"]
        self.assertEqual(draft["status"], "planning")
        self.assertIsNone(route)
        self.assertTrue(any("When will you first need to withdraw" in point.value for point in self.app.markdown))
        self.assertNotIn("assistant_comparison", self.app.session_state)

        self.click("Compare SPY and GLD historically")
        report = self.app.session_state["assistant_comparison"][1]
        self.assertEqual(set(report["options"]), {"SPY", "GLD"})
        self.assertIsNone(report["requirements"]["max_drawdown"]["limit"])
        self.assertEqual(report["finding"]["status"], "neutral")
