"""Verify that offline trade drafting keeps only supported, grounded inputs."""

import unittest

from datathon.agents import ground_profile_request
from datathon.runtime_budget import PROFILE_MAX_REQUEST_BYTES


class OfflineProfileGroundingTests(unittest.TestCase):
    def test_grounded_draft_has_verbatim_fields_and_private_trace(self):
        request = (
            "Add five percentage points of NVDA by selling only QQQ. "
            "The maximum historical drawdown must not exceed 20%."
        )
        draft = ground_profile_request(request, "grounded", search_alternatives=True)
        self.assertEqual(draft.status, "ok")
        self.assertEqual(draft.data["target_bps"], 500)
        self.assertEqual(draft.data["initial_source"], "QQQ")
        self.assertEqual(draft.data["metric"], "max_drawdown")
        self.assertEqual(draft.data["limit_bps"], 2000)
        self.assertEqual(draft.data["allowed_sources"], ["QQQ"])
        self.assertIsNone(draft.data["allow_smaller"])
        self.assertTrue(all(excerpt in request for excerpt in draft.data["source_excerpts"].values()))
        self.assertEqual(draft.trace, ({"role": "profile", "event": "local_profile_draft", "run_id": "grounded"},))

    def test_missing_metric_is_not_invented(self):
        draft = ground_profile_request(
            "Add six percentage points of NVDA, funded only from ZST.TO. The loss cap is 7%.", "metric",
        )
        self.assertEqual(draft.status, "needs_input")
        self.assertEqual(draft.data["initial_source"], "ZST.TO")
        self.assertEqual(draft.data["limit_bps"], 700)
        self.assertIsNone(draft.data["metric"])
        self.assertEqual(draft.data["clarification_field"], "loss_metric")

    def test_competing_or_rejected_funding_is_unresolved(self):
        cases = (
            "Add five percentage points of NVDA by selling QQQ or ZST.TO.",
            "Add five percentage points of NVDA by selling only QQQ. Never sell QQQ.",
            "Add five percentage points of NVDA by selling QQQ alone. Sell SPY instead.",
            "My adviser suggested I add five percentage points of NVDA by selling only QQQ.",
        )
        for request in cases:
            with self.subTest(request=request):
                draft = ground_profile_request(request, "conflict")
                self.assertEqual(draft.status, "needs_input")
                self.assertIsNone(draft.data["initial_source"])
                self.assertFalse(draft.data["funding_grounded"])

    def test_explicit_unsupported_trade_never_proposes_a_replacement(self):
        cases = (
            ("Increase MSFT by five percentage points from QQQ.", "simulated purchases of NVDA"),
            ("Add five percentage points of NVDA funded from SPY.", "QQQ or ZST.TO as funding"),
            ("Add five percentage points of NVDA from cash.", "QQQ or ZST.TO as funding"),
        )
        for request, summary in cases:
            with self.subTest(request=request):
                draft = ground_profile_request(request, "unsupported")
                self.assertEqual(draft.status, "needs_input")
                self.assertEqual(draft.data["clarification_field"], "unsupported_scope")
                self.assertIsNone(draft.data.get("target_bps"))
                self.assertIsNone(draft.data.get("initial_source"))
                self.assertIn(draft.data["unsupported_excerpt"], request)
                self.assertIn(summary, draft.data["summary"])

    def test_existing_binding_checks_preserve_unsupported_requirements(self):
        draft = ground_profile_request(
            "Add five percentage points of NVDA from QQQ. Never hold more than 4% of the direct NVDA position. "
            "Use only the years when rates were falling.", "scope",
        )
        self.assertEqual(draft.status, "needs_input")
        self.assertEqual(draft.data["clarification_field"], "unsupported_constraint")
        self.assertEqual({entry["code"] for entry in draft.data["unassessed_requirements"]},
                         {"direct_issuer_cap", "other_binding"})

    def test_byte_limit_and_non_text_remain_safe(self):
        for request in (" ", None, "é" * (PROFILE_MAX_REQUEST_BYTES // 2 + 1)):
            with self.subTest(request_type=type(request)):
                draft = ground_profile_request(request, "invalid")
                self.assertEqual(draft.status, "error")
                self.assertEqual(draft.stop_reason, "invalid_input")


if __name__ == "__main__":
    unittest.main()
