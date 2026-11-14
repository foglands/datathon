"""Exercise the Streamlit confirmation and comparison flow on the official snapshot."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError as exc:
    if exc.name != "streamlit":
        raise
    AppTest = None

from datathon.agents import AgentRun, StrandsAgents
from datathon.workflow import examples, preset_profile


APP = Path(__file__).resolve().parents[1] / "app.py"
CONFIRM = "Confirm inputs and run audit"
COMPARE = "Confirm this change and compare"
INTERPRET = "Interpret request with Bedrock"


@unittest.skipIf(AppTest is None, "Install Streamlit to run the UI tests.")
@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH to run official-data UI tests.")
class PortfolioAppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=15).run()
        self.assertFalse(self.app.exception)

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def has_button(self, label):
        return any(button.label == label for button in self.app.button)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assertFalse(self.app.exception)

    def select(self, kind, label, value):
        self.widget(kind, label).set_value(value).run()
        self.assertFalse(self.app.exception)

    def verify_only_rule_change(self, original, changed, key, before, after):
        self.assertEqual(original["policy"][key], before)
        self.assertEqual(changed["policy"][key], after)
        self.assertEqual(changed["policy"], {**original["policy"], key: after})
        self.assertTrue(any(
            event.get("event") == "one_rule_changed" and event.get("field") in {key, f"{key}_bps"}
            for event in changed["trace"]
        ))

    def compare(self, scenario):
        self.select("selectbox", "Scenario", scenario)
        self.assertNotIn("preset_result", self.app.session_state)
        self.assertFalse(self.has_button(COMPARE))
        self.click(CONFIRM)
        self.assertIn("preset_result", self.app.session_state)
        self.assertNotIn("comparison_result", self.app.session_state)
        self.click(COMPARE)
        self.assertGreaterEqual(len(self.app.tabs), 2)
        return self.app.session_state["preset_result"], self.app.session_state["comparison_result"]

    def test_loss_metric_changes_full_feasibility(self):
        original, changed = self.compare("Robert · loss definition")
        self.verify_only_rule_change(original, changed, "metric", "terminal_loss", "max_drawdown")
        self.assertEqual(original["alternatives"]["status"], "feasible_full")
        self.assertAlmostEqual(original["audit"]["verified"]["frontier"]["full_zst_max"], .02631671476)
        self.assertEqual(changed["alternatives"]["status"], "no_feasible")
        self.assertTrue(changed["audit"]["verified"]["no_feasible_confirmed"])
        self.assertTrue(any("2.63" in item.value for item in self.app.markdown))

    def test_reserve_floor_switches_the_binding_rule(self):
        original, changed = self.compare("Robert · reserve floor")
        self.verify_only_rule_change(original, changed, "reserve_floor", .15, .18)
        original_range = original["alternatives"]["frontier"]
        changed_range = changed["alternatives"]["frontier"]
        self.assertEqual(original_range["full_zst_max_binding"], "terminal_loss")
        self.assertEqual(changed_range["full_zst_max_binding"], "reserve_floor")
        self.assertAlmostEqual(changed["audit"]["verified"]["frontier"]["full_zst_max"], .02)

    def test_smaller_purchase_is_eligible_only_when_allowed(self):
        original, changed = self.compare("Robert · purchase size")
        self.verify_only_rule_change(original, changed, "allow_smaller", False, True)
        exact = original["audit"]["verified"]
        smaller = changed["audit"]["verified"]
        self.assertEqual(exact["solver_status"], "requested_size_infeasible")
        self.assertIsNone(exact["frontier"]["max_total"])
        self.assertAlmostEqual(exact["frontier"]["diagnostic_max_total"], .05)
        self.assertNotIn("maximum", exact)
        self.assertEqual(smaller["solver_status"], "feasible_partial")
        self.assertAlmostEqual(smaller["frontier"]["max_total"], .05)
        self.assertTrue(smaller["maximum"]["passes"])

    def test_amira_displays_a_breach_and_withholds_an_unresolved_alternative(self):
        self.select("selectbox", "Scenario", "Amira · issuer exposure")
        self.click(CONFIRM)
        report = self.app.session_state["preset_result"]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["alternatives"]["status"], "insufficient_issuer_evidence")
        self.assertNotIn("maximum", report["audit"]["verified"])
        self.assertTrue(any(item.value == "Alternative remains unresolved" for item in self.app.warning))
        self.assertTrue(any("13.39%" in item.value for item in self.app.markdown))
        self.assertTrue(any("Maximum drawdown" in table.value.columns for table in self.app.table))

    def test_live_clarification_waits_for_confirmation(self):
        calls = []
        ambiguous = {
            **preset_profile(examples("robert", stress=True)[-1]),
            "limit_bps": 1400,
            "clarification_field": "loss_metric",
            "summary": "Does the loss cap apply to terminal loss or maximum drawdown?",
        }

        async def simulate_bedrock(runtime, role, payload, tools=(), *, run_id=None):
            calls.append(role)
            if role == "profile":
                return AgentRun("needs_input", ambiguous)
            for tool in tools:
                tool.handler()
            return AgentRun("ok", {"status": "ok", "summary": "Test reply", "evidence_ids": []})

        with patch.object(StrandsAgents, "run", autospec=True, side_effect=simulate_bedrock):
            self.select("radio", "Input", "Write a request")
            self.assertFalse(self.has_button(CONFIRM))
            self.click(INTERPRET)
            self.assertEqual(calls, ["profile"])
            self.assertFalse(self.has_button(CONFIRM))
            self.assertFalse(self.app.session_state["request_results"])

            self.select("radio", "The cap measures", "terminal_loss")
            self.assertTrue(self.has_button(CONFIRM))
            self.assertEqual(calls, ["profile"])
            self.assertFalse(self.app.session_state["request_results"])

            self.click(CONFIRM)
            result = self.app.session_state["request_results"]["terminal_loss"]
            self.assertEqual(result["policy"]["metric"], "terminal_loss")
            self.assertEqual(result["alternatives"]["status"], "feasible_full")
            self.assertIn("review", calls)

            calls.clear()
            self.select("radio", "The cap measures", "max_drawdown")
            self.assertEqual(calls, [])
            self.assertNotIn("max_drawdown", self.app.session_state["request_results"])
            self.assertFalse(self.app.get("download_button"))
            self.click(CONFIRM)
            result = self.app.session_state["request_results"]["max_drawdown"]
            self.assertEqual(result["policy"]["metric"], "max_drawdown")
            self.assertTrue(result["audit"]["verified"]["no_feasible_confirmed"])
            self.assertIn("Compare the two confirmed rules", [label.value for label in self.app.subheader])

            request = self.widget("text_area", "Fictional investment request").value
            self.select("text_area", "Fictional investment request", f"{request} A new instruction.")
            self.assertFalse(self.has_button(CONFIRM))
            self.assertFalse(self.app.get("download_button"))
            self.select("text_area", "Fictional investment request", request)
            self.assertFalse(self.has_button(CONFIRM))
            self.assertNotIn("request_results", self.app.session_state)
