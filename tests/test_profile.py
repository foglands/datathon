"""Verify explicit intent and failure states at the typed Profile boundary."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    from strands import Agent
    from strands.hooks import AfterToolCallEvent, AfterToolsEvent
except ImportError:
    Agent = None

from datathon.agents import StrandsAgents, _profile_handoff
from datathon.workflow import profile_policy


FIELDS = dict(
    status="ok", summary="Goal and rules extracted", metric="terminal_loss", limit_bps=1400,
    target_bps=500, reserve_floor_bps=1500, initial_source="QQQ", allowed_sources="QQQ",
    allow_smaller=0,
)
REQUEST = (
    "Shift 5 percentage points to NVDA from QQQ. Do not reduce the purchase amount. "
    "Keep 15% in ZST.TO. Limit start-to-end loss to 14%."
)


class ProfileHandoffTests(unittest.TestCase):
    def test_supported_numbers_and_exact_excerpts_stay_separate(self):
        request = REQUEST + " I have a nine-year horizon. This is for a class simulation."
        draft = _profile_handoff(request, **FIELDS, loss_excerpt="Limit start-to-end loss to 14%.",
                                 initial_source_excerpt="from QQQ", funding_excerpt="from SPY")
        self.assertTrue(StrandsAgents._valid_data(draft, "profile"))
        self.assertEqual(profile_policy(draft)["target"], .05)
        self.assertEqual(draft["source_excerpts"], {
            "metric": "Limit start-to-end loss to 14%.", "limit_bps": "Limit start-to-end loss to 14%.",
            "initial_source": "from QQQ",
        })
        self.assertIsNone(draft["issuer_cap_bps"])

    def test_original_source_defaults_only_when_separate_permission_is_omitted(self):
        fields = {**FIELDS, "allowed_sources": ""}
        draft = _profile_handoff(REQUEST, **fields)
        self.assertEqual(profile_policy(draft)["allowed_sources"], ("QQQ",))
        for funding_rule in ("only", "ambiguous"):
            with self.subTest(funding_rule=funding_rule):
                unresolved = _profile_handoff(REQUEST, **fields, funding_rule=funding_rule)
                self.assertEqual(unresolved["clarification_field"], "allowed_sources")
                with self.assertRaises(ValueError):
                    profile_policy(unresolved)

    def test_additive_permission_and_exhaustive_conflict_stay_separate(self):
        fields = {**FIELDS, "initial_source": "ZST", "allowed_sources": "QQQ"}
        additive = _profile_handoff(REQUEST, **fields, funding_rule="add")
        self.assertEqual(profile_policy(additive)["allowed_sources"], ("QQQ", "ZST.TO"))
        exclusive = _profile_handoff(REQUEST, **fields, funding_rule="only")
        self.assertEqual(exclusive["clarification_field"], "conflict")
        self.assertEqual(exclusive["allowed_sources"], ["QQQ"])

    def test_bare_loss_cap_preserves_number_with_specific_clarification(self):
        fields = {**FIELDS, "allowed_sources": "", "metric": ""}
        draft = _profile_handoff("The simulated maximum loss is fourteen percent.", **fields)
        self.assertEqual(draft["clarification_field"], "loss_metric")
        self.assertEqual(draft["limit_bps"], 1400)
        self.assertIsNone(draft["metric"])

    def test_exact_equal_priority_metric_conflict_takes_precedence(self):
        draft = _profile_handoff(REQUEST, **FIELDS, clarification_field="conflict", additional_loss_limit_bps=1400)
        self.assertEqual(draft["clarification_field"], "conflict")

    def test_dual_caps_cannot_be_approved_by_a_single_metric_handoff(self):
        request = REQUEST + " For every replay also cap the earlier-peak decline at 12%."
        draft = _profile_handoff(request, **FIELDS, additional_loss_limit_bps=1200)
        self.assertTrue(StrandsAgents._valid_data(draft, "profile"))
        self.assertEqual(draft["clarification_field"], "multiple_loss_limits")
        with self.assertRaisesRegex(ValueError, "one historical loss rule"):
            profile_policy(draft)

    def test_unsupported_direct_constraint_blocks_even_a_complete_draft(self):
        bound = "Direct NVDA shares must represent at most 7% of the portfolio."
        draft = _profile_handoff(REQUEST + " " + bound, **FIELDS,
                                 clarification_field="unsupported_constraint", unsupported_excerpt=bound)
        self.assertTrue(StrandsAgents._valid_data(draft, "profile"))
        self.assertEqual(draft["clarification_field"], "unsupported_constraint")
        self.assertEqual(draft["unsupported_excerpt"], bound)
        self.assertIsNone(draft["issuer_cap_bps"])
        with self.assertRaisesRegex(ValueError, "binding rule"):
            profile_policy(draft)

    def test_conflicting_funding_takes_precedence_over_editable_loss_ambiguity(self):
        draft = _profile_handoff(REQUEST, **{**FIELDS, "allowed_sources": "ZST", "metric": ""},
                                 clarification_field="loss_metric")
        self.assertTrue(StrandsAgents._valid_data(draft, "profile"))
        self.assertEqual(draft["clarification_field"], "conflict")
        self.assertEqual((draft["initial_source"], draft["allowed_sources"]), ("QQQ", ["ZST.TO"]))

    def test_terminal_sentence_does_not_override_model_hold(self):
        request = REQUEST + " The maximum drawdown in either historical window is 14%."
        draft = _profile_handoff(request, **{**FIELDS, "status": "needs_input", "metric": ""},
                                 clarification_field="loss_metric")
        self.assertEqual(draft["status"], "needs_input")
        self.assertIsNone(draft["metric"])
        self.assertEqual(draft["limit_bps"], 1400)


@unittest.skipIf(Agent is None, "Install the pinned Strands SDK to verify its Profile tool schema.")
class ProfileSDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_handoff_excludes_verbatim_excerpts_and_failed_tool_values_from_trace(self):
        test = self
        excerpt = "Limit start-to-end loss to 14%."
        canary = "Fictional private request text"
        request = f"{REQUEST} {canary}"
        arguments = {
            "target_bps": 500, "initial_source": " qqq ", "allow_smaller": 0,
            "metric": "terminal_loss", "limit_bps": 1400, "reserve_floor_bps": 1500,
            "loss_excerpt": excerpt,
        }

        class RecordedAgent:
            def __init__(self, *, tools, system_prompt, **_):
                self.tool = tools[0]
                self.callbacks = {}
                self.hooks = SimpleNamespace(add_callback=self.callbacks.__setitem__)
                test.assertIn("explicitly adopts", system_prompt)
                schema = self.tool.tool_spec["inputSchema"]["json"]
                test.assertEqual(schema["properties"]["funding_rule"]["enum"], ["", "add", "only", "ambiguous"])
                test.assertNotIn("summary", schema["properties"])
                test.assertNotIn("source_excerpts", schema["properties"])

            async def invoke_async(self, prompt, *, structured_output_model, **_):
                test.assertIsNone(structured_output_model)
                test.assertEqual(json.loads(prompt.split("\n", 1)[1]), {"user_request": request})
                failed = {"name": "submit_profile", "toolUseId": "failed-profile-test",
                          "input": {**arguments, "metric": canary}}
                invalid = [part async for part in self.tool.stream(failed, {})][-1].tool_result
                test.assertIn(canary, str(invalid))
                self.callbacks[AfterToolCallEvent](SimpleNamespace(tool_use=failed, result=invalid, duration=.001))
                unfinished = SimpleNamespace(end_turn=False)
                self.callbacks[AfterToolsEvent](unfinished)
                test.assertFalse(unfinished.end_turn)

                use = {"name": "submit_profile", "toolUseId": "profile-test", "input": arguments}
                result = [part async for part in self.tool.stream(use, {})][-1].tool_result
                self.callbacks[AfterToolCallEvent](SimpleNamespace(tool_use=use, result=result, duration=.001))
                finished = SimpleNamespace(end_turn=False)
                self.callbacks[AfterToolsEvent](finished)
                test.assertTrue(finished.end_turn)
                return SimpleNamespace(stop_reason="tool_use")

        client = SimpleNamespace(meta=SimpleNamespace(events=SimpleNamespace(register=lambda *_: None)))
        with patch("strands.Agent", RecordedAgent), patch("strands.models.BedrockModel", return_value=SimpleNamespace(client=client)):
            handoff = await StrandsAgents().run("profile", {"user_request": request})
        self.assertEqual(handoff.status, "ok")
        self.assertEqual(profile_policy(handoff.data)["allowed_sources"], ("QQQ",))
        self.assertEqual(handoff.data["source_excerpts"]["limit_bps"], excerpt)
        self.assertNotIn(excerpt, json.dumps(handoff.trace))
        self.assertNotIn(canary, json.dumps(handoff.trace))
        failed_tool, checked_tool = [event for event in handoff.trace if event["event"] == "tool"]
        self.assertEqual((failed_tool["status"], failed_tool["input"], failed_tool["output"]), ("error", {}, None))
        self.assertEqual(checked_tool["input"]["initial_source"], "QQQ")
        self.assertEqual(checked_tool["input"]["allowed_sources"], ["QQQ"])
