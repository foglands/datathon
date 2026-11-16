"""Exercise the new three-path UI and its confirmation/publication boundaries."""

import json
import os
from unittest import TestCase, skipUnless
from unittest.mock import patch

from tests.test_app import APP, AppTest
from datathon.decision_workflow import confirm_decision, run_decision
from datathon.decision_release import publish_report
from datathon.decision_view import _report, _explain, _explanation_activity
from datathon.data import load_market_data


class ExplanationActivityTests(TestCase):
    def test_withdrawn_narrative_exposes_reason_and_trace_without_rejected_text(self):
        explanation = {"mode": "deterministic", "model_version": "test-model",
                       "trace": [{"event": "model_response"}],
                       "summary": "Checked historical result.",
                       "narrative": {"status": "withdrawn", "reason": "narrative_factual_claim_mismatch",
                                     "text": "Unverified model claim"}}
        report = {"explanation": explanation}
        activity = _explanation_activity(report)
        self.assertEqual(activity["mode"], "deterministic")
        self.assertEqual(activity["model_version"], "test-model")
        self.assertEqual(activity["trace"], explanation["trace"])
        self.assertEqual(activity["narrative"]["reason"], "narrative_factual_claim_mismatch")
        self.assertNotIn("Unverified model claim", json.dumps(activity))
        with patch("datathon.decision_view.st") as interface:
            _explain(report)
        interface.caption.assert_called_once_with("Verification reason: narrative factual claim mismatch.")
        interface.write.assert_called_once_with("Checked historical result.")


@skipUnless(AppTest and os.environ.get("DATATHON_STARTER_PATH"), "Streamlit and the official snapshot are required.")
class DecisionViewTests(TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertFalse(self.app.exception)

    def click(self, label):
        next(item for item in self.app.button if item.label == label).click().run()
        self.assertFalse(self.app.exception)

    def draft(self, question):
        self.app.text_area(key="decision_question").set_value(question).run()
        self.click("Draft offline")

    def approve(self):
        rev = self.app.session_state["decision_revision"]
        self.app.checkbox(key=f"decision_approved_{rev}").set_value(True).run()
        self.click("Confirm and run historical review")
        return self.app.session_state["decision_result"][1]

    def test_confirmation_and_view_switch_share_one_immutable_result(self):
        with patch("datathon.decision_view.run_decision", wraps=run_decision) as replay:
            self.draft("Compare AGG and GLD.")
            replay.assert_not_called()
            rev = self.app.session_state["decision_revision"]
            self.assertEqual(self.app.text_area(key=f"decision_holdings_{rev}_0").value, "AGG 100%")
            report = self.approve()
            self.assertEqual(report["publication"]["status"], "released")
            self.assertEqual(replay.call_count, 1)

            fingerprint = json.dumps(report, sort_keys=True)
            self.app.radio(key="decision_result_view").set_value("Metrics first").run()
            self.assertFalse(self.app.exception)
            self.assertEqual(json.dumps(self.app.session_state["decision_result"][1], sort_keys=True), fingerprint)
            self.assertEqual(replay.call_count, 1)
            self.assertTrue(self.app.get("download_button"))
            self.app.text_area(key=f"decision_holdings_{rev}_0").set_value("SPY 100%").run()
            self.assertFalse(self.app.get("download_button"))
            self.assertEqual(replay.call_count, 1)

    def test_tampering_is_blocked_before_any_metric_is_rendered(self):
        confirmed = confirm_decision({"intent": "evaluate", "portfolios": [{"label": "Test", "weights": {"AGG": 1}}]})
        report = publish_report(run_decision(confirmed, load_market_data()))
        report["options"]["Test"]["windows"]["2022"]["max_drawdown"] = .99
        with patch("datathon.decision_view.st") as interface:
            _report(report, confirmed, load_market_data, None, False)
        interface.error.assert_called_once()
        interface.dataframe.assert_not_called()
        interface.write.assert_not_called()
        interface.download_button.assert_not_called()

    def test_selecting_another_profile_refreshes_the_editable_fields(self):
        self.draft("Compare AGG and GLD.")
        revision = self.app.session_state["decision_revision"]
        self.app.selectbox(key=f"decision_profile_{revision}").set_value("Robert").run()
        self.assertIn("Capital preservation", self.app.text_input(key=f"decision_objective_{revision}").value)
        self.assertEqual(self.app.selectbox(key=f"decision_finance_literacy_{revision}").value, "expert")
        self.app.selectbox(key=f"decision_profile_{revision}").set_value("Mateo").run()
        self.assertTrue(self.app.checkbox(key=f"decision_esg_{revision}").value)

    def test_unknown_share_purchase_has_context_and_an_upload_route(self):
        self.draft("I want to buy 200 shares of AMD.")
        draft = self.app.session_state["decision_draft"][0]
        self.assertEqual(draft["intent"], "evaluate")
        self.assertIn("investable_capital_share", draft["missing"])
        self.assertTrue(any("AMD is outside" in item.value for item in self.app.warning))
        self.assertTrue(any("proportion of your investable capital" in item.value for item in self.app.info))
        self.assertTrue(self.app.get("file_uploader"))
        self.assertNotIn("decision_result", self.app.session_state)

    def test_unavailable_bedrock_preserves_a_french_draft_without_running(self):
        self.app.text_area(key="decision_question").set_value("Comparez AGG et GLD selon les résultats historiques.").run()
        with patch("datathon.decision_view.configured_decision_runtime", side_effect=RuntimeError("not available")), \
                patch("datathon.decision_view.run_decision") as replay:
            self.click("Draft with Amazon Bedrock")
        replay.assert_not_called()
        draft = self.app.session_state["decision_draft"][0]
        self.assertEqual(draft["origin"], "offline_draft")
        self.assertEqual(draft["intent"], "compare")
        self.assertTrue(any("Bedrock" in item.value for item in self.app.info))
        self.assertNotIn("decision_result", self.app.session_state)

    def test_original_audit_requires_separate_search_and_clear_resets_everything(self):
        self.click("Try Robert's question")
        self.click("Draft offline")
        with patch("datathon.decision_workflow.search_funding") as search:
            original = self.approve()
            search.assert_not_called()
        self.assertEqual(original["verdict"], "fail")
        self.assertIsNone(original.get("funding"))
        self.app.selectbox(key="decision_followup_question").set_value("purchase_quantity").run()
        self.assertFalse(self.app.exception)
        self.assertNotIn("decision_challenge_result", self.app.session_state)
        self.click("Confirm and run this hypothetical check")
        self.assertEqual(self.app.session_state["decision_result"][1], original)
        self.assertEqual(len(self.app.session_state["decision_challenge_result"][2]["steps"]), 1)
        self.click("Start a new question")
        self.assertEqual(self.app.text_area(key="decision_question").value, "")
        for key in ("decision_result", "decision_draft", "decision_storage", "decision_challenge_result"):
            self.assertNotIn(key, self.app.session_state)

    def test_evaluation_preserves_esg_as_an_unresolved_requirement(self):
        self.click("Try Mateo's question")
        self.click("Draft offline")
        report = self.approve()
        self.assertEqual(report["intent"], "evaluate")
        self.assertEqual(report["publication"]["status"], "released")
        self.assertEqual(report["verdict"], "unknown")
        self.assertTrue(any(row["status"] == "unknown" for row in report["rules"]))

    def test_unresolved_exposure_is_visible_and_withholds_the_ranking(self):
        self.draft("Compare AGG and GLD.")
        rev = self.app.session_state["decision_revision"]
        self.app.text_area(key=f"decision_rules_{rev}").set_value(json.dumps({
            "constraints": [{"asset_set": {"sector": "Information Technology"}, "max": .2}],
            "risk_limits": [],
        }))
        self.app.selectbox(key=f"decision_priority_{rev}").set_value("max_drawdown").run()
        report = self.approve()
        self.assertTrue(report["exposure"])
        self.assertEqual(report["ranking"]["order"], [])
        self.assertIn("Look-through exposure and screening evidence", [item.label for item in self.app.expander])
        self.assertTrue(any(report["ranking"]["reason"] in item.value for item in self.app.info))
        self.assertFalse(any("**Reviewed ranking**" in item.value for item in self.app.markdown))
