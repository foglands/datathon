"""Exercise the Streamlit confirmation and comparison flow on the official snapshot."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
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
from tests.test_issuer_reaudit import configured_catalog, synthetic_disclosure
from tests.test_tool_routing import select_tool_arguments


APP = Path(__file__).resolve().parents[1] / "app.py"
CONFIRM = "Confirm inputs and run audit"
COMPARE = "Confirm this change and compare"
INTERPRET = "Interpret request with Bedrock"
MANUAL_SCOPE = "These inputs include every binding rule for this simulation."
SEARCH = "Search alternative funding"
LIMITED_SCOPE = "Audit only supported rules and mark the other requirements as not assessed."
AUTHORIZE = "Authorize a smaller purchase and rerun"


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
        self.assertTrue(any("Historical risk drivers" in item.value for item in self.app.markdown))
        self.assertTrue(any("Peak 2022-01-04" in item.value and "Trough 2022-10-12" in item.value
                            for item in self.app.caption))

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

    def test_counterfactual_keeps_the_original_audited_policy(self):
        self.click(CONFIRM)
        original = self.app.session_state["preset_result"]
        self.select("selectbox", "Check to run", "toggle_loss_metric")
        self.click("Check once")

        challenge = self.app.session_state["active_challenge"][-1]
        self.assertEqual(challenge["changed_fields"], ["metric"])
        self.assertEqual(challenge["comparison"]["baseline"]["solver_status"], "feasible_full")
        self.assertEqual(challenge["comparison"]["replay"]["solver_status"], "no_feasible")
        self.assertEqual(self.app.session_state["preset_result"], original)
        self.assertTrue(any("One hypothetical change" in item.value for item in self.app.markdown))

    def test_reserve_challenge_accepts_one_explicit_precision_threshold(self):
        self.click(CONFIRM)
        original = self.app.session_state["preset_result"]
        self.select("selectbox", "Check to run", "tighten_reserve_floor")
        self.select("number_input", "Hypothetical minimum ZST.TO weight (%)", 19.5)
        self.click("Check once")
        challenge = self.app.session_state["active_challenge"][-1]
        self.assertTrue(challenge["verified"])
        self.assertEqual(challenge["changed_fields"], ["reserve_floor"])
        self.assertEqual(challenge["confirmed_threshold"], {"value": 1950, "unit": "basis_points"})
        self.assertAlmostEqual(challenge["comparison"]["replay"]["full_zst_max"], .005)
        self.assertEqual(self.app.session_state["preset_result"], original)
        self.select("number_input", "Hypothetical minimum ZST.TO weight (%)", 18.5)
        self.assertFalse(any("One hypothetical change" in element.value for element in self.app.markdown))

    def test_amira_challenge_names_the_remaining_evidence_and_headroom(self):
        self.select("selectbox", "Scenario", "Amira · issuer exposure")
        self.click(CONFIRM)
        self.click("Check once")

        challenge = self.app.session_state["active_challenge"][-1]
        self.assertEqual(challenge["reason"], "issuer_evidence_required")
        self.assertEqual(set(challenge["action"]["holdings"]), {"XIU.TO", "ZST.TO"})
        self.assertIsNone(challenge["replay"])
        self.assertTrue(any("0.60937 percentage points" in item.value for item in self.app.markdown))

    def test_amira_reaudits_reviewed_disclosures_in_a_separate_result(self):
        with TemporaryDirectory() as folder:
            records = [synthetic_disclosure("xiu", "XIU.TO"), synthetic_disclosure("zst", "ZST.TO")]
            with configured_catalog(Path(folder) / "catalog.json", records):
                self.select("selectbox", "Scenario", "Amira · issuer exposure")
                self.click(CONFIRM)
                original = self.app.session_state["preset_result"]
                self.select("selectbox", "Check to run", "request_issuer_evidence")
                self.select("multiselect", "Reviewed holdings disclosures to apply", ["xiu", "zst"])
                self.click("Re-audit reviewed disclosures")

        challenge = self.app.session_state["active_challenge"][-1]
        self.assertEqual(challenge["reason"], "issuer_reaudit_verified")
        self.assertEqual(challenge["replay"]["policy"], original["policy"])
        self.assertTrue(challenge["comparison"]["replay"]["alternative_eligible"])
        self.assertEqual(self.app.session_state["preset_result"], original)
        self.assertTrue(any("Independent re-audit with reviewed disclosures" in item.value for item in self.app.markdown))

    def test_live_clarification_waits_for_confirmation(self):
        calls = []
        ambiguous = {
            **preset_profile(examples("robert", stress=True)[-1]),
            "limit_bps": 1400,
            "clarification_field": "loss_metric",
            "source_excerpts": {"limit_bps": "I cannot lose more than 14%."},
            "summary": "Does the loss cap apply to terminal loss or maximum drawdown?",
        }

        async def simulate_bedrock(runtime, role, payload, tools=(), *, run_id=None):
            calls.append(role)
            if role == "profile":
                return AgentRun("needs_input", ambiguous)
            for tool in tools:
                tool.handler(**select_tool_arguments(role, payload))
            return AgentRun("ok", {"status": "ok", "summary": "Test reply", "evidence_ids": []})

        with patch.object(StrandsAgents, "run", autospec=True, side_effect=simulate_bedrock):
            self.select("radio", "Input", "Write a request")
            self.select("radio", "Profile input", "Interpret text with Bedrock")
            self.select("checkbox", SEARCH, True)
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
            key = self.app.session_state["request_confirmed"]
            result = self.app.session_state["request_results"][key]
            self.assertEqual(result["policy"]["metric"], "terminal_loss")
            self.assertEqual(result["alternatives"]["status"], "feasible_full")
            self.assertIn("review", calls)
            self.assertNotIn("user_request", result)
            self.assertNotIn("source_excerpts", result["agent_outputs"]["profile"])

            calls.clear()
            self.select("radio", "The cap measures", "max_drawdown")
            self.assertEqual(calls, [])
            self.assertNotIn("request_confirmed", self.app.session_state)
            self.assertFalse(self.app.get("download_button"))
            self.click(CONFIRM)
            key = self.app.session_state["request_confirmed"]
            result = self.app.session_state["request_results"][key]
            self.assertEqual(result["policy"]["metric"], "max_drawdown")
            self.assertTrue(result["audit"]["verified"]["no_feasible_confirmed"])
            self.assertIn("Compare the two confirmed rules", [label.value for label in self.app.subheader])

            calls.clear()
            self.select("number_input", "Minimum ZST.TO weight (%)", 18.0)
            self.assertEqual(calls, [])
            self.assertNotIn("request_confirmed", self.app.session_state)
            self.assertFalse(self.app.get("download_button"))
            self.click(CONFIRM)
            edited_key = self.app.session_state["request_confirmed"]
            edited = self.app.session_state["request_results"][edited_key]
            self.assertEqual(edited["policy"], {**result["policy"], "reserve_floor": .18})
            self.assertTrue(any(event.get("changes", {}).get("reserve_floor_bps") == {"from": 1500, "to": 1800}
                                for event in edited["trace"]))
            self.assertNotIn("Compare the two confirmed rules", [label.value for label in self.app.subheader])

            self.select("number_input", "Minimum ZST.TO weight (%)", 15.0)
            self.assertNotIn("request_confirmed", self.app.session_state)
            self.assertFalse(self.app.get("download_button"))
            self.click(CONFIRM)
            self.assertEqual(self.app.session_state["request_confirmed"], key)

            request = self.widget("text_area", "Fictional investment request").value
            self.select("text_area", "Fictional investment request", f"{request} A new instruction.")
            self.assertFalse(self.has_button(CONFIRM))
            self.assertFalse(self.app.get("download_button"))
            self.select("text_area", "Fictional investment request", request)
            self.assertFalse(self.has_button(CONFIRM))
            self.assertNotIn("request_results", self.app.session_state)

    def test_unsupported_binding_rule_blocks_confirmation(self):
        excerpt = "Never hold more than 5% in the direct NVDA position."
        blocked = {
            **preset_profile(examples("robert")[0]),
            "status": "needs_input", "summary": "This hard rule needs clarification.",
            "clarification_field": "unsupported_constraint", "unsupported_excerpt": excerpt,
        }
        with patch.object(StrandsAgents, "run", return_value=AgentRun("needs_input", blocked)) as run:
            self.select("radio", "Input", "Write a request")
            self.select("radio", "Profile input", "Interpret text with Bedrock")
            self.select("text_area", "Fictional investment request", excerpt)
            self.click(INTERPRET)
            run.assert_awaited_once()
            self.assertFalse(self.has_button(CONFIRM))
            self.assertFalse(self.app.get("download_button"))
            self.assertTrue(any(item.value == excerpt for item in self.app.text))

    def fill_manual_profile(self):
        self.select("number_input", "NVDA purchase size (percentage points)", 5.0)
        self.select("selectbox", "Funding for the original proposal", "QQQ")
        self.select("checkbox", "Apply a historical loss cap", True)
        self.select("radio", "The cap measures", "terminal_loss")
        self.select("number_input", "Historical loss cap (%)", 14.0)

    def test_manual_entry_works_without_bedrock_and_requires_confirmation_after_edits(self):
        with patch.object(StrandsAgents, "run", side_effect=AssertionError("Manual workflow must not call Bedrock")) as run:
            self.select("radio", "Input", "Write a request")
            self.assertEqual(self.widget("radio", "Profile input").value, "Enter inputs directly")
            self.assertEqual(self.widget("radio", "Audit execution").value, "Bedrock")
            self.select("radio", "Audit execution", "Offline")
            self.assertFalse(self.has_button(INTERPRET))
            self.assertFalse(self.has_button(CONFIRM))
            self.assertFalse(any(item.label == "Funding allowed for alternatives" for item in self.app.multiselect))
            self.assertFalse(any(item.label == "Allow a smaller purchase" for item in self.app.selectbox))
            self.fill_manual_profile()
            self.assertTrue(self.widget("button", CONFIRM).disabled)
            self.select("checkbox", MANUAL_SCOPE, True)
            self.assertFalse(self.widget("button", CONFIRM).disabled)
            self.assertFalse(self.app.session_state["request_results"])

            self.click(CONFIRM)
            key = self.app.session_state["request_confirmed"]
            report = self.app.session_state["request_results"][key]
            self.assertEqual(report["mode"], "offline")
            self.assertEqual(report["policy"]["loss_limit"], .14)
            self.assertFalse(report["search_alternatives"])
            self.assertNotIn("alternatives", report)
            self.assertNotIn("frontier", report["audit"]["verified"])
            self.assertFalse(any(event["role"] == "alternatives" for event in report["trace"]))
            self.assertTrue(any(event["event"] == "manual_profile_entered" for event in report["trace"]))
            self.assertNotIn("source_excerpts", report["agent_outputs"]["profile"])
            self.select("number_input", "Historical loss cap (%)", 15.0)
            self.assertNotIn("request_confirmed", self.app.session_state)
            self.assertFalse(self.app.get("download_button"))
            self.assertTrue(self.widget("button", CONFIRM).disabled)
            self.select("checkbox", MANUAL_SCOPE, True)
            self.click(CONFIRM)
            key = self.app.session_state["request_confirmed"]
            self.assertEqual(self.app.session_state["request_results"][key]["policy"]["loss_limit"], .15)
            run.assert_not_awaited()

    def test_manual_search_defers_smaller_permission_until_exact_size_fails(self):
        self.select("radio", "Input", "Write a request")
        self.select("radio", "Audit execution", "Offline")
        self.select("checkbox", SEARCH, True)
        self.select("number_input", "NVDA purchase size (percentage points)", 10.0)
        self.select("selectbox", "Funding for the original proposal", "ZST.TO")
        self.select("multiselect", "Funding allowed for alternatives", ["ZST.TO"])
        self.select("number_input", "Minimum ZST.TO weight (%)", 15.0)
        self.assertFalse(any(item.label == "Allow a smaller purchase" for item in self.app.selectbox))
        self.assertFalse(self.has_button(AUTHORIZE))
        self.select("checkbox", MANUAL_SCOPE, True)
        self.click(CONFIRM)
        before = self.app.session_state["request_confirmed"]
        first = self.app.session_state["request_results"][before]
        self.assertTrue(first["search_alternatives"])
        self.assertTrue(first["needs_smaller_authorization"])
        self.assertNotIn("maximum", first["audit"]["verified"])
        self.assertTrue(self.has_button(AUTHORIZE))

        self.click(AUTHORIZE)
        after = self.app.session_state["request_confirmed"]
        second = self.app.session_state["request_results"][after]
        self.assertNotEqual(before, after)
        self.assertTrue(second["policy"]["allow_smaller"])
        self.assertEqual(second["alternatives"]["status"], "feasible_partial")
        self.assertAlmostEqual(second["audit"]["verified"]["maximum"]["total"], .05)
        self.assertFalse(self.has_button(AUTHORIZE))
        self.assertEqual(self.app.session_state["request_results"][before], first)

        self.select("checkbox", SEARCH, False)
        self.assertNotIn("request_confirmed", self.app.session_state)
        self.assertFalse(self.app.get("download_button"))

    def test_clarified_unsupported_constraint_limits_public_result(self):
        calls = []
        excerpt = "Only buy stocks rated AAA for ESG."
        blocked = {
            **preset_profile(examples("robert")[0]),
            "status": "needs_input", "summary": "This hard rule cannot be assessed.",
            "clarification_field": "unsupported_constraint", "unsupported_excerpt": excerpt,
            "unassessed_requirements": [{"code": "esg", "excerpt": excerpt}],
        }

        async def simulate_bedrock(runtime, role, payload, tools=(), *, run_id=None):
            calls.append(role)
            if role == "profile":
                return AgentRun("needs_input", blocked)
            for tool in tools:
                tool.handler(**select_tool_arguments(role, payload))
            return AgentRun("ok", {"status": "ok", "summary": "Test reply", "evidence_ids": []})

        with patch.object(StrandsAgents, "run", autospec=True, side_effect=simulate_bedrock):
            self.select("radio", "Input", "Write a request")
            self.select("radio", "Profile input", "Interpret text with Bedrock")
            self.select("checkbox", SEARCH, True)
            self.click(INTERPRET)
            self.assertFalse(self.has_button(CONFIRM))
            self.assertEqual(calls, ["profile"])
            self.select("checkbox", LIMITED_SCOPE, True)
            self.assertTrue(self.has_button(CONFIRM))
            self.click(CONFIRM)

        key = self.app.session_state["request_confirmed"]
        report = self.app.session_state["request_results"][key]
        self.assertFalse(report["search_alternatives"])
        self.assertNotIn("alternatives", calls)
        self.assertIn("review", calls)
        self.assertNotIn(excerpt, str(report))
        self.assertIn("esg", str(report["requirements"]).lower())

    def test_manual_audit_confirms_custom_weights_and_keeps_the_scope_on_replay(self):
        self.select("radio", "Input", "Write a request")
        self.select("radio", "Audit execution", "Offline")
        self.fill_manual_profile()
        self.select("checkbox", "Use custom starting weights", True)
        self.select("number_input", "SPY starting weight (%)", 30.0)
        self.assertFalse(self.has_button(CONFIRM))
        self.assertTrue(any("totaling exactly 100%" in item.value for item in self.app.warning))
        self.select("number_input", "ZST.TO starting weight (%)", 25.0)
        self.select("checkbox", "Include the fixed 2023 replay", True)
        self.select("selectbox", "Fictional investment objective", "Growth")
        self.select("selectbox", "Timing of next meaningful withdrawal", "More than 5 years")
        self.select("checkbox", MANUAL_SCOPE, True)
        self.click(CONFIRM)

        key = self.app.session_state["request_confirmed"]
        result = self.app.session_state["request_results"][key]
        scope = result["confirmed_scope"]
        self.assertEqual(scope["planning_context"], {"objective": "Growth", "withdrawal_time": "More than 5 years"})
        self.assertEqual(scope["starting_weights"]["ZST.TO"], .25)
        self.assertEqual(result["audit"]["verified"]["baseline"]["windows"]["2023"]["observations"], 63)

        self.select("selectbox", "Check to run", "toggle_loss_metric")
        self.click("Check once")
        check = self.app.session_state["active_challenge"][-1]
        self.assertTrue(check["verified"])
        self.assertEqual(check["replay"]["confirmed_scope"], scope)
        self.select("checkbox", "Include the fixed 2023 replay", False)
        self.assertNotIn("request_confirmed", self.app.session_state)

    def test_bedrock_failure_can_recover_through_manual_entry(self):
        with patch.object(StrandsAgents, "run", return_value=AgentRun("error", {}, stop_reason="unavailable")) as run:
            self.select("radio", "Input", "Write a request")
            self.select("radio", "Profile input", "Interpret text with Bedrock")
            self.click(INTERPRET)
            self.assertFalse(self.has_button(CONFIRM))
            self.assertTrue(any("unavailable" in item.value for item in self.app.error))
            self.select("radio", "Profile input", "Enter inputs directly")
            self.select("radio", "Audit execution", "Offline")
            self.fill_manual_profile()
            self.select("checkbox", MANUAL_SCOPE, True)
            self.click(CONFIRM)
            self.assertIn("request_confirmed", self.app.session_state)
            run.assert_awaited_once()
