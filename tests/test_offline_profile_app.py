"""Verify offline trade intake and credential failures at the Streamlit entry point."""

import os
import unittest
from unittest.mock import patch

from datathon.agents import AgentRun, StrandsAgents
from datathon.finance import solve_funding
from datathon.publication import publish_report
from tests.test_app import APP, AppTest, CONFIRM, INTERPRET


_QUESTION = (
    "Add five percentage points of NVDA by selling only QQQ. "
    "The maximum historical drawdown must not exceed 20%."
)
_OFFLINE = "Interpret text offline"
_BEDROCK = "Interpret text with Bedrock"
_SCOPE = "I checked this draft against my request and confirmed every binding rule for this audit."


@unittest.skipIf(AppTest is None, "Install Streamlit to run the UI tests.")
@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH for official-data UI tests.")
class OfflineProfileAppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.app.radio(key="workspace").set_value("Reference cases").run()
        self.app.radio(key="reference_workspace").set_value("Earlier assistant validation").run()
        self.assertFalse(self.app.exception)

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def select(self, kind, label, value):
        self.widget(kind, label).set_value(value).run()
        self.assertFalse(self.app.exception)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assertFalse(self.app.exception)

    def enter_trade_question(self):
        self.app.text_area(key="assistant_question").set_value(_QUESTION)
        self.click("Interpret question")
        self.assertEqual(self.widget("radio", "Profile input").value, _OFFLINE)

    def assert_unconfirmed_draft(self, question=_QUESTION, drawdown=20.0):
        self.assertEqual(self.widget("text_area", "Fictional investment request").value, question)
        self.assertEqual(self.widget("number_input", "NVDA purchase size (percentage points)").value, 5.0)
        self.assertEqual(self.widget("selectbox", "Funding for the original proposal").value, "QQQ")
        self.assertEqual(self.widget("number_input", "Historical loss cap (%)").value, drawdown)
        self.assertEqual(self.widget("radio", "The cap measures").value, "max_drawdown")
        self.assertFalse(self.widget("checkbox", _SCOPE).value)
        self.assertTrue(self.widget("button", CONFIRM).disabled)
        self.assertNotIn("request_confirmed", self.app.session_state)

    def test_question_runs_offline_after_review_without_funding_search(self):
        with (
            patch.object(StrandsAgents, "run", side_effect=AssertionError("Bedrock requires explicit selection")) as runtime,
            patch("datathon.workflow.solve_funding", wraps=solve_funding) as solver,
        ):
            self.enter_trade_question()
            self.assert_unconfirmed_draft()
            self.select("checkbox", _SCOPE, True)
            self.click(CONFIRM)
            confirmed = self.app.session_state["request_confirmed"]
            report = self.app.session_state["request_results"][confirmed]
            self.assertEqual(report["mode"], "offline")
            self.assertEqual(report["policy"]["target"], .05)
            self.assertEqual(report["policy"]["initial_source"], "QQQ")
            self.assertEqual(report["policy"]["loss_limit"], .20)
            self.assertEqual(report["policy"]["metric"], "max_drawdown")
            self.assertFalse(report["search_alternatives"])
            self.assertTrue(publish_report(report)["publication"]["independent_review_verified"])
            self.assertTrue(any(event.get("role") == "alternatives" and event.get("event") == "stage_skipped"
                                for event in report["trace"]))
            self.select("number_input", "Historical loss cap (%)", 21.0)
            self.assertNotIn("request_confirmed", self.app.session_state)
            self.assertFalse(self.widget("checkbox", _SCOPE).value)
            self.assertTrue(self.widget("button", CONFIRM).disabled)
            runtime.assert_not_awaited()
            solver.assert_not_called()

    def test_missing_bedrock_credentials_offer_unconfirmed_offline_continuation(self):
        failure = AgentRun(
            "error", {}, ({"role": "profile", "event": "agent_exception",
                            "error_type": "NoCredentialsError", "error_code": None},), "invocation_error",
        )
        with patch.object(StrandsAgents, "run", return_value=failure) as runtime:
            self.enter_trade_question()
            self.select("radio", "Profile input", _BEDROCK)
            runtime.assert_not_awaited()
            edited_question = _QUESTION.replace("20%", "18%")
            self.widget("text_area", "Fictional investment request").set_value(edited_question)
            self.click(INTERPRET)
            runtime.assert_awaited_once()
            self.assertEqual(runtime.await_args.args[1]["user_request"], edited_question)
            message = " ".join(alert.value for alert in (*self.app.error, *self.app.warning))
            self.assertIn("AWS credentials", message)
            self.assertNotIn("NoCredentialsError", message)
            self.assertNotIn("invocation_error", message)
            self.assertNotIn("request_confirmed", self.app.session_state)
            self.click("Continue offline")
            self.assertEqual(self.widget("radio", "Profile input").value, _OFFLINE)
            self.assert_unconfirmed_draft(edited_question, drawdown=18.0)
            runtime.assert_awaited_once()

    def test_direct_entry_defaults_to_offline(self):
        with patch.object(
            StrandsAgents, "run", side_effect=AssertionError("Opening direct entry requires no model call"),
        ) as runtime:
            self.app.radio(key="reference_workspace").set_value("Audited trade examples").run()
            self.select("radio", "Input", "Write a request")
            self.assertEqual(self.widget("radio", "Profile input").value, "Enter inputs directly")
            self.assertEqual(self.widget("radio", "Audit execution").value, "Offline")
            self.assertNotIn("request_confirmed", self.app.session_state)
            runtime.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
