"""Verify CLI consent separately from model interpretation and finance review."""

from argparse import Namespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from datathon.__main__ import run_request
from datathon.agents import AgentRun
from datathon.workflow import examples, preset_profile


class RequestEntryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.args = Namespace(
            request="Buy 10 percentage points of NVDA from ZST.TO.",
            data="unused", report=None, search_alternatives=False, include_sector=False,
        )
        self.draft = AgentRun("ok", {**preset_profile(examples("robert")[0]), "allow_smaller": None})

    async def test_default_cli_audits_the_original_without_resize_followup(self):
        with (patch("datathon.__main__.interpret_request", return_value=(self.draft, {"prefer_reserve": None}, None)) as intake,
              patch("datathon.__main__.read_input", side_effect=["YES"]) as prompt,
              patch("datathon.__main__.print_policy"), patch("datathon.__main__.load_market_data"),
              patch("datathon.__main__.run_case", new_callable=AsyncMock, return_value={"status": "fail"}) as audit,
              patch("datathon.__main__.publish_report", side_effect=lambda result: result),
              patch("builtins.print")):
            self.assertEqual(await run_request(self.args), 0)

        self.assertFalse(intake.await_args.kwargs["search_alternatives"])
        self.assertFalse(audit.await_args.args[1].search_alternatives)
        self.assertEqual(prompt.call_count, 1)
        audit.assert_awaited_once()

    async def test_cli_authorizes_resize_after_independent_full_size_check(self):
        self.args.search_alternatives = True
        original = {"status": "fail", "publication": {"independent_review_verified": True}}
        full_size = {"status": "fail", "needs_smaller_authorization": True}
        smaller_size = {"status": "fail", "needs_smaller_authorization": False}
        with (patch("datathon.__main__.interpret_request", return_value=(self.draft, {"prefer_reserve": None}, None)) as intake,
              patch("datathon.__main__.read_input", side_effect=["YES", "SEARCH", "YES"]) as prompt,
              patch("datathon.__main__.print_policy"), patch("datathon.__main__.load_market_data"),
              patch("datathon.__main__.run_case", new_callable=AsyncMock,
                    side_effect=[original, full_size, smaller_size]) as audit,
              patch("datathon.__main__.publish_report", side_effect=lambda result: result),
              patch("builtins.print")):
            self.assertEqual(await run_request(self.args), 0)

        self.assertTrue(intake.await_args.kwargs["search_alternatives"])
        self.assertTrue(intake.await_args.kwargs["defer_smaller_authorization"])
        self.assertEqual(prompt.call_count, 3)
        self.assertEqual([entry.args[1].search_alternatives for entry in audit.await_args_list], [False, True, True])
        original_profile, search_profile, resize_profile = (
            entry.kwargs["confirmed_profile"] for entry in audit.await_args_list
        )
        self.assertIsNone(original_profile.data["allow_smaller"])
        self.assertIsNone(search_profile.data["allow_smaller"])
        self.assertEqual(search_profile.trace[-1]["event"], "alternative_search_authorized")
        self.assertTrue(resize_profile.data["allow_smaller"])
        self.assertEqual(resize_profile.trace[-1]["event"], "smaller_purchase_authorized")

    async def test_cli_shows_unresolved_original_audit_before_optional_search(self):
        self.args.search_alternatives = True
        original = {"status": "insufficient_evidence", "explanation": "Issuer evidence is unresolved.",
                    "publication": {"independent_review_verified": True}}

        def read_answer(message):
            if message.startswith("Type SEARCH"):
                output.assert_any_call("\nAudit of original proposal: insufficient_evidence")
                output.assert_any_call("Issuer evidence is unresolved.")
                return ""
            return "YES"

        with (patch("datathon.__main__.interpret_request", return_value=(self.draft, {"prefer_reserve": None}, None)),
              patch("datathon.__main__.read_input", side_effect=read_answer) as prompt,
              patch("datathon.__main__.print_policy"), patch("datathon.__main__.load_market_data"),
              patch("datathon.__main__.run_case", new_callable=AsyncMock, return_value=original) as audit,
              patch("datathon.__main__.publish_report", side_effect=lambda result: result),
              patch("builtins.print") as output):
            self.assertEqual(await run_request(self.args), 0)

        self.assertEqual(prompt.call_count, 2)
        audit.assert_awaited_once()
        self.assertFalse(audit.await_args.args[1].search_alternatives)

    async def test_cli_skips_search_offer_if_original_has_no_verified_proposal(self):
        self.args.search_alternatives = True
        for status, exit_code in (("invalid", 1), ("execution_error", 1), ("insufficient_evidence", 0)):
            with self.subTest(status=status):
                original = {"status": status, "publication": {"independent_review_verified": False}}
                with (patch("datathon.__main__.interpret_request", return_value=(self.draft, {"prefer_reserve": None}, None)),
                      patch("datathon.__main__.read_input", side_effect=["YES"]) as prompt,
                      patch("datathon.__main__.print_policy"), patch("datathon.__main__.load_market_data"),
                      patch("datathon.__main__.run_case", new_callable=AsyncMock, return_value=original) as audit,
                      patch("datathon.__main__.publish_report", side_effect=lambda result: result),
                      patch("builtins.print")):
                    self.assertEqual(await run_request(self.args), exit_code)

                self.assertEqual(prompt.call_count, 1)
                audit.assert_awaited_once()
                self.assertFalse(audit.await_args.args[1].search_alternatives)
