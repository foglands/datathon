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
        proposal = {"status": "proposed", "task": "compare_allocations", "trace": [], "usage": {}}
        question = "Compare a Canadian equity fund with a bond fund for a planned withdrawal."
        with patch("datathon.streamlit_assistant.suggest_intent", return_value=proposal) as suggest:
            self.app.text_area(key="assistant_question").set_value(question).run()
            self.click("Suggest a task with Bedrock")
            self.assertEqual(suggest.await_args.args[0], question)
            self.assertEqual(self.app.selectbox(key="assistant_task").value, "compare_allocations")
            self.assertNotIn("assistant_confirmed", self.app.session_state)
            self.assertFalse(any(item.label == "Confirm inputs and compare" for item in self.app.button))
