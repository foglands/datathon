"""The default customer path is conversational; technical controls stay in validation."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.test_app import APP, AppTest
from tests.test_customer_research import asset, fx, plan
from datathon.customer_workflow import research_question


@unittest.skipIf(AppTest is None, "Streamlit is required")
class CustomerViewTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertFalse(self.app.exception)

    def test_home_has_one_question_no_professional_modes_or_personas(self):
        self.assertEqual(len(self.app.text_area), 1)
        self.assertEqual(len(self.app.selectbox), 0)
        self.assertEqual(len(self.app.number_input), 0)
        self.assertFalse(any("Amira" in button.label or "Mateo" in button.label or "Robert" in button.label for button in self.app.button))
        self.assertTrue(any(button.label == "Research my idea" for button in self.app.button))

    def test_customer_can_research_without_confirming_technical_inputs(self):
        request = "i want to invest stock share of amd with 3000 cad"
        provider = Mock(asset=Mock(return_value=asset()), fx=Mock(return_value=fx()))
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan())):
            report = asyncio.run(research_question(request, provider=provider))
        self.app.text_area(key="customer_question").set_value(request).run()
        with patch("datathon.customer_view.customer_runtime", return_value=None), \
             patch("datathon.customer_view.research_question", AsyncMock(return_value=report)):
            next(button for button in self.app.button if button.label == "Research my idea").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state["customer_report"]["status"], "ready")
        self.assertEqual(len(self.app.metric), 3)
        self.assertTrue(any(button.label == "Update my research" for button in self.app.button))
        self.assertFalse(any(button.label == "Confirm and run historical review" for button in self.app.button))

    def test_model_and_provider_failure_remain_visible_without_fake_report(self):
        report = {"question": "unknown", "plan": plan(mode="clarify"), "analyses": [], "errors": [], "fx": None,
                  "blocks": {}, "editor": {}, "method": "test", "created_at": "2026-11-16", "status": "needs_input"}
        from datathon.review_snapshot import fingerprint
        report["report_digest"] = fingerprint(report)
        self.app.session_state["customer_report"] = report
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.metric), 0)


if __name__ == "__main__":
    unittest.main()
