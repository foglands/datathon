"""Verify explicit intent and failure states at the typed Profile boundary."""

import json
import unittest

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
        excerpts = json.dumps({
            "target_bps": "5 percentage points", "limit_bps": "Limit start-to-end loss to 14%.",
            "allow_smaller": "Do not reduce the purchase amount.", "issuer_cap_bps": "nine-year horizon",
            "reserve_floor_bps": "Always keep 99% in ZST.TO.", "unknown_field": "a nine-year horizon",
        })
        draft = _profile_handoff(request, **FIELDS, source_excerpts=excerpts)
        self.assertTrue(StrandsAgents._valid_data(draft, "profile"))
        self.assertEqual(profile_policy(draft)["target"], .05)
        self.assertEqual(draft["source_excerpts"], {
            "target_bps": "5 percentage points", "limit_bps": "Limit start-to-end loss to 14%.",
            "allow_smaller": "Do not reduce the purchase amount.",
        })
        self.assertIsNone(draft["issuer_cap_bps"])

    def test_dual_caps_cannot_be_approved_by_a_single_metric_handoff(self):
        request = REQUEST + " For every replay also cap the earlier-peak decline at 12%."
        draft = _profile_handoff(request, **FIELDS, additional_loss_limit_bps=1200)
        self.assertTrue(StrandsAgents._valid_data(draft, "profile"))
        self.assertEqual(draft["clarification_field"], "multiple_loss_limits")
        with self.assertRaisesRegex(ValueError, "one historical loss rule"):
            profile_policy(draft)

    def test_unsupported_direct_constraint_blocks_even_a_complete_draft(self):
        bound = "Direct NVDA shares must represent at most 7% of the portfolio."
        draft = _profile_handoff(REQUEST + " " + bound, **FIELDS, unsupported_excerpt=bound)
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
