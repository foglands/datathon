"""Check that live routing follows quantities and symbols supported by the request."""

import unittest
from unittest.mock import AsyncMock

from datathon.agents import AgentRun
from datathon.live_market_intake import interpret_live_market_request, local_live_market_intake


class LiveMarketIntakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_ended_investment_opinion_keeps_planning_when_model_disagrees(self):
        question = "I have CAD 50,000 and want low-risk investments. Stock shares or Bitcoin, what's your opinion"
        self.assertEqual(local_live_market_intake(question)["status"], "planning")
        for model_status in ("planning", "needs_input", "unsupported"):
            with self.subTest(model_status=model_status):
                runtime = AsyncMock()

                async def run(_role, _payload, *, tools, stop_after_tool):
                    tools[0].handler(intent=model_status, scope="none", data_source="none", source="clause_1")
                    return AgentRun("ok", {})

                runtime.run.side_effect = run
                result = await interpret_live_market_request(question, runtime)
                self.assertEqual(result["status"], "planning")
                self.assertEqual(result["origin"], "bedrock" if model_status == "planning" else "local")
                self.assertIsNone(result["data_source"])
                runtime.run.assert_awaited_once()

    async def test_model_selects_an_evidenced_lookup_for_a_naturally_worded_proposal(self):
        request = "I can see myself purchasing just 200 AMD shares this year."
        runtime = AsyncMock()

        async def run(role, payload, *, tools, stop_after_tool):
            self.assertEqual(role, "live_market_intake")
            self.assertEqual(payload["user_request"], request)
            self.assertEqual(payload["candidate_clauses"], {"clause_1": request})
            tool, = tools
            self.assertEqual(stop_after_tool, tool.name)
            result = tool.handler(intent="share_purchase", scope="quote_and_history", data_source="alpaca",
                                  source="clause_1", ticker="AMD", share_count="200")
            self.assertEqual(result, {"status": "ok"})
            return AgentRun("ok", {}, ({"event": "tool", "status": "success", "input": request},))

        runtime.run.side_effect = run
        result = await interpret_live_market_request(request, runtime)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["intent"], "share_purchase")
        self.assertEqual(result["scope"], "quote_and_history")
        self.assertEqual(result["data_source"], "alpaca")
        self.assertEqual(result["symbol"], "AMD")
        self.assertEqual(result["shares"], "200")
        self.assertEqual(result["wording"], request)
        self.assertEqual(result["origin"], "bedrock")
        self.assertNotIn("input", result["trace"][0])
        runtime.run.assert_awaited_once()

    async def test_proxy_failure_preserves_grounded_shares_and_uses_the_approved_provider(self):
        runtime = AsyncMock()
        runtime.run.return_value = AgentRun("error", {}, ({
            "event": "agent_exception", "error_type": "ProxyConnectionError", "exception": "private details",
        },))
        request = "i want to invest 200 share of AMD stock"
        result = await interpret_live_market_request(request, runtime)
        self.assertEqual((result["status"], result["symbol"], result["shares"]), ("ready", "AMD", "200"))
        self.assertEqual(result["origin"], "local")
        self.assertEqual(result["data_source"], "alpaca")
        self.assertEqual(result["wording"], request)
        self.assertEqual(result["trace"], ({"event": "agent_exception", "error_type": "ProxyConnectionError"},))

    async def test_rejects_invented_inputs_and_arbitrary_network_sources(self):
        request = "I can see myself purchasing just 200 AMD shares this year."
        valid = {"intent": "share_purchase", "scope": "quote_and_history", "data_source": "alpaca",
                 "source": "clause_1", "ticker": "AMD", "share_count": "200"}
        for changed in ({"ticker": "NVDA"}, {"share_count": "201"}, {"source": "clause_8"},
                        {"scope": "latest_quote"}, {"data_source": "https://untrusted.example"}):
            with self.subTest(changed=changed):
                runtime = AsyncMock()

                async def run(_role, _payload, *, tools, stop_after_tool):
                    tool, = tools
                    self.assertEqual(stop_after_tool, tool.name)
                    with self.assertRaises(ValueError):
                        tool.handler(**{**valid, **changed})
                    return AgentRun("ok", {})

                runtime.run.side_effect = run
                result = await interpret_live_market_request(request, runtime)
                self.assertNotEqual(result["status"], "ready")
                self.assertIsNone(result["scope"])

    async def test_local_scope_selects_latest_quote_history_or_clarification(self):
        cases = (
            ("What is the latest quote for AMD?", ("ready", "quote", "latest_quote", "AMD", None)),
            ("What is the recent history of AMD?", ("ready", "market_history", "quote_and_history", "AMD", None)),
            ("I'd like to buy $spy.", ("ready", "market_history", "quote_and_history", "SPY", None)),
            ("We plan to purchase 1,200 SPY shares.", ("ready", "share_purchase", "quote_and_history", "SPY", "1200")),
            ("I want to buy 2000 shares of AMD.", ("ready", "share_purchase", "quote_and_history", "AMD", "2000")),
            ("What is the current price of Apple?", ("needs_input", None, None, None, None)),
            ("Compare current prices of AMD and NVDA.", ("needs_input", None, None, None, None)),
            ("I want to buy 200 shares of Apple.", ("needs_input", None, None, None, None)),
            ("I already own 200 shares of AMD.", ("not_applicable", None, None, None, None)),
            ("Replay AMD in the archived stress window.", ("not_applicable", None, None, None, None)),
        )
        for request, expected in cases:
            with self.subTest(request=request):
                result = await interpret_live_market_request(request, None)
                self.assertEqual(tuple(result[key] for key in ("status", "intent", "scope", "symbol", "shares")), expected)

    async def test_no_lookup_for_orders_forecasts_or_misattributed_purchase_size(self):
        runtime = AsyncMock()
        for request in ("Buy 200 shares of AMD now.", "Place a market order for AMD.",
                        "Predict the price of AMD next week."):
            with self.subTest(request=request):
                result = await interpret_live_market_request(request, runtime)
                self.assertEqual(result["status"], "unsupported")
                self.assertIsNone(result["data_source"])
        runtime.run.assert_not_awaited()
        for request in ("I do not want to buy 200 shares of AMD.", "My colleague wants to buy 200 AMD shares.",
                        "I want to buy -200 shares of AMD.", '"I want to buy 200 shares of AMD."',
                        "I want to buy 200 shares of AMD or NVDA."):
            with self.subTest(request=request):
                result = await interpret_live_market_request(request, None)
                self.assertNotEqual(result["status"], "ready")
                self.assertIsNone(result["symbol"])

    async def test_conflicting_purchase_sizes_are_held_even_if_model_selects_one(self):
        request = "I plan to buy 200 AMD shares. I plan to buy 300 shares of AMD."
        runtime = AsyncMock()

        async def run(_role, _payload, *, tools, stop_after_tool):
            tool, = tools
            self.assertEqual(tool.name, stop_after_tool)
            tool.handler(intent="share_purchase", scope="quote_and_history", data_source="alpaca",
                         source="clause_1", ticker="AMD", share_count="200")
            return AgentRun("ok", {})

        runtime.run.side_effect = run
        for result in (local_live_market_intake(request), await interpret_live_market_request(request, runtime)):
            self.assertEqual(result["status"], "needs_input")
            self.assertIn("share count", result["message"])
            self.assertIsNone(result["symbol"])

    async def test_unsupported_dates_currency_and_interval_cannot_be_discarded(self):
        for request in ("Show recent history for AMD over the past six months.",
                        "What was the AMD stock price on November 12, 2025?",
                        "What is AMD's latest quote in CAD?",
                        "Show recent intraday history for AMD."):
            with self.subTest(request=request):
                result = local_live_market_intake(request)
                self.assertEqual(result["status"], "unsupported")
                self.assertIn("90 calendar days", result["message"])
                self.assertIsNone(result["scope"])
        for request in ("Show AMD recent history over the last 90 calendar days.",
                        "Show the AMD stock price over the last 90 days."):
            valid = local_live_market_intake(request)
            self.assertEqual((valid["status"], valid["scope"]), ("ready", "quote_and_history"))

    async def test_model_cannot_turn_an_approximation_or_share_range_into_an_exact_count(self):
        for request in ("I plan to purchase about 200 AMD shares.", "I want to buy 150 to 200 AMD shares."):
            with self.subTest(request=request):
                runtime = AsyncMock()

                async def run(_role, _payload, *, tools, stop_after_tool):
                    tool, = tools
                    self.assertEqual(tool.name, stop_after_tool)
                    with self.assertRaises(ValueError):
                        tool.handler(intent="share_purchase", scope="quote_and_history", data_source="alpaca",
                                     source="clause_1", ticker="AMD", share_count="200")
                    return AgentRun("ok", {})

                runtime.run.side_effect = run
                result = await interpret_live_market_request(request, runtime)
                self.assertIsNone(result["shares"])
