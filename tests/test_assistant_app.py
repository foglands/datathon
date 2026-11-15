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
        proposal = {"status": "ready", "task": "trade_audit", "trace": [], "usage": {}}
        question = "Add eight percentage points of NVDA by selling only ZST.TO."
        with patch("datathon.streamlit_assistant.interpret_semantic_request", return_value=proposal) as suggest:
            self.app.text_area(key="assistant_question").set_value(question).run()
            self.click("Interpret with Amazon Bedrock")
            self.assertEqual(suggest.await_args.args[0], question)
            self.assertEqual(self.app.text_area(key="assistant_trade_question").value, question)
            self.assertFalse(self.app.session_state["request_results"])
            self.assertNotIn("request_confirmed", self.app.session_state)
            confirm = next(item for item in self.app.button if item.label == "Confirm inputs and run audit")
            self.assertTrue(confirm.disabled)

    def test_non_english_question_is_blocked_before_cloud_or_market_data(self):
        self.app.text_area(key="assistant_question").set_value("¿Cómo debería invertir mis ahorros?").run()
        with patch("datathon.streamlit_assistant.interpret_semantic_request") as interpret:
            with patch("datathon.streamlit_assistant._market_bundle") as market:
                self.click("Interpret with Amazon Bedrock")
        interpret.assert_not_called()
        market.assert_not_called()
        self.assertTrue(any("Please enter your question in English" in item.value for item in self.app.warning))
        self.assertNotIn("assistant_question_draft", self.app.session_state)
        self.app.text_area(key="assistant_question").set_value("Can you help me invest my cash?").run()
        self.click("Interpret question")
        self.assertEqual(self.app.session_state["assistant_question_draft"][0]["status"], "planning")

    def test_model_only_comparison_requires_full_scope_confirmation(self):
        proposal = {"status": "ready", "task": "compare_allocations", "trace": [], "usage": {}}
        self.app.text_area(key="assistant_question").set_value("Show me how AGG and GLD held up in past downturns.").run()
        with patch("datathon.streamlit_assistant.interpret_semantic_request", return_value=proposal):
            self.click("Interpret with Amazon Bedrock")
        compare = next(button for button in self.app.button if button.label == "Confirm inputs and compare")
        self.assertTrue(compare.disabled)
        self.app.checkbox(key="assistant_confirm_text_scope").set_value(True).run()
        self.click("Confirm inputs and compare")
        self.assertIn("assistant_comparison", self.app.session_state)

    def test_mixed_request_answers_planning_and_exposes_unsupported_forecast(self):
        self.app.text_area(key="assistant_question").set_value(
            "How could I invest cash set aside for tuition? Predict next year's price for GLD."
        ).run()
        with patch("datathon.streamlit_assistant._market_bundle") as market:
            self.click("Interpret question")
        market.assert_not_called()
        self.assertEqual(self.app.session_state["assistant_question_draft"][0]["status"], "planning")
        self.assertTrue(any("future price" in item.value for item in self.app.warning))
        self.assertFalse(self.app.get("download_button"))

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

    def test_all_in_and_return_promise_are_answered_before_any_optional_replay(self):
        question = (
            "I have saved $34,000 and never invested. My colleagues are trading stock options. "
            "Can I put all my savings into NVDA or Bitcoin? Is there a guaranteed 22% annual return?"
        )
        self.app.text_area(key="assistant_question").set_value(question).run()
        self.click("Interpret question")
        self.assertTrue(any("fraud warning sign" in item.value for item in self.app.warning))
        for topic in ("Individual company stocks", "Cryptoassets such as Bitcoin", "Options and leverage"):
            self.assertTrue(any(topic in item.value for item in self.app.markdown))
        self.assertNotIn("assistant_comparison", self.app.session_state)

        self.click("Compare NVDA and BTC-USD historically")
        report = self.app.session_state["assistant_comparison"][1]
        self.assertEqual(set(report["options"]), {"NVDA", "BTC-USD"})
        self.assertEqual(report["finding"]["status"], "neutral")
        self.assertIsNone(report["requirements"]["max_drawdown"]["limit"])


    def test_single_allocation_can_run_with_currency_suffix(self):
        question = (
            "I have $63,000 for retirement. Analyze my portfolio with 60% in SPY and 40% in AGG. Currency: CAD."
        )
        self.app.text_area(key="assistant_question").set_value(question).run()
        self.click("Interpret question")
        self.assertTrue(any(item.value == "Stated currency · CAD" for item in self.app.text))
        self.assertFalse(any("Confirm the currency for any calculation" in item.value for item in self.app.caption))
        self.click("Run historical portfolio replay")
        report = self.app.session_state["assistant_comparison"][1]
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["options"]["Proposed allocation"]["weights"], {"SPY": .6, "AGG": .4})

    def test_single_allocation_proxy_requires_approval_and_keeps_balance_separate(self):
        question = (
            "I have $63,000 to invest. Can you assess my proposed allocation of "
            "40% in VOO, 35% in SPY, and 25% in QQQ? "
            "The $88,000 balance is in CAD."
        )
        self.app.text_area(key="assistant_question").set_value(question).run()
        self.click("Interpret question")
        self.assertTrue(any("different cash balances" in item.value for item in self.app.warning))
        self.assertTrue(any("75.00% in funds tracking the S&P 500 Index" in item.value for item in self.app.markdown))
        run = next(item for item in self.app.button if item.label == "Run illustrative portfolio replay")
        self.assertTrue(run.disabled)
        self.app.checkbox(key="assistant_approve_proxy").set_value(True).run()
        self.click("Run illustrative portfolio replay")
        report = self.app.session_state["assistant_comparison"][1]
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["options"]["Proposed allocation"]["weights"], {"SPY": .75, "QQQ": .25})
        self.assertTrue(any("Verified illustrative replay" in item.value for item in self.app.markdown))

    def test_missing_prices_without_a_documented_proxy_withhold_replay(self):
        question = "Evaluate my allocation of 65% in VTI and 35% in AGG."
        self.app.text_area(key="assistant_question").set_value(question).run()
        self.click("Interpret question")
        self.assertTrue(any("missing for VTI" in item.value for item in self.app.warning))
        self.assertFalse(any("portfolio replay" in item.label for item in self.app.button))
