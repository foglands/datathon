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
        first = {"status": "fail", "needs_smaller_authorization": True}
        second = {"status": "fail", "needs_smaller_authorization": False}
        with (patch("datathon.__main__.interpret_request", return_value=(self.draft, {"prefer_reserve": None}, None)) as intake,
              patch("datathon.__main__.read_input", side_effect=["YES", "YES"]) as prompt,
              patch("datathon.__main__.print_policy"), patch("datathon.__main__.load_market_data"),
              patch("datathon.__main__.run_case", new_callable=AsyncMock, side_effect=[first, second]) as audit,
              patch("datathon.__main__.publish_report", side_effect=lambda result: result),
              patch("builtins.print")):
            self.assertEqual(await run_request(self.args), 0)

        self.assertTrue(intake.await_args.kwargs["search_alternatives"])
        self.assertTrue(intake.await_args.kwargs["defer_smaller_authorization"])
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(audit.await_count, 2)
        self.assertTrue(all(entry.args[1].search_alternatives for entry in audit.await_args_list))
        first_profile, second_profile = (entry.kwargs["confirmed_profile"] for entry in audit.await_args_list)
        self.assertIsNone(first_profile.data["allow_smaller"])
        self.assertTrue(second_profile.data["allow_smaller"])
        self.assertEqual(second_profile.trace[-1]["event"], "smaller_purchase_authorized")
