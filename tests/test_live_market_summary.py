"""Keep the conclusion grounded even if the final model returns unsupported claims."""

import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib.util import find_spec
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun, DEFAULT_MODEL, DEFAULT_REGION, StrandsAgents
from datathon.live_market_summary import summarize_live_market
from datathon.runtime_budget import RuntimeBudgetExceeded


_TOOL = "select_market_summary"


def _report(*, shares=Decimal("200"), trailing=None):
    as_of = datetime(2026, 11, 13, 19, 30, tzinfo=timezone.utc)
    quote = SimpleNamespace(price=Decimal("122.30"), currency="USD", source="Alpaca", feed="iex", as_of=as_of)
    notional = quote.price * shares if shares is not None else None
    evidence = {
        "ticker": "AMD", "shares": str(shares) if shares is not None else None,
        "quote": {"price": "122.30", "currency": "USD", "as_of": as_of.isoformat(), "feed": "iex"},
        "indicative_notional": str(notional) if notional is not None else None,
    }
    return SimpleNamespace(ticker="AMD", shares=shares, quote=quote, indicative_notional=notional,
                           trailing=trailing, as_model_evidence=lambda: evidence)


class LiveMarketSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_conclusion_uses_verified_calculation_and_filters_trace_and_model_text(self):
        report = _report()
        runtime = AsyncMock()

        async def run(role, payload, *, tools, stop_after_tool):
            self.assertEqual(role, "live_market_summary")
            self.assertEqual(payload["verified_market_evidence"], report.as_model_evidence())
            self.assertEqual(stop_after_tool, _TOOL)
            self.assertNotIn("user_request", payload)
            tool, = tools
            tool.handler(emphasis="purchase_cost", next_input="portfolio_context")
            return AgentRun("ok", {"summary": "The stock is guaranteed to double."}, (
                {"event": "tool", "tool_name": _TOOL, "status": "success", "output": "Invented quote"},
            ))

        runtime.run.side_effect = run
        result = await summarize_live_market(report, runtime)
        self.assertEqual(result["status"], "ready")
        self.assertIn("USD 24,460.00", result["conclusion"])
        self.assertIn("200 shares", result["conclusion"])
        self.assertIn("existing position", result["conclusion"])
        self.assertNotIn("double", json.dumps(result))
        self.assertNotIn("Invented quote", json.dumps(result))

    async def test_missing_quote_and_history_do_not_publish_unverified_conclusions(self):
        runtime = AsyncMock()
        self.assertEqual((await summarize_live_market(None, runtime))["status"], "not_run")
        self.assertEqual((await summarize_live_market(_report(), None))["status"], "not_run")
        runtime.run.assert_not_called()

        async def run(_role, payload, *, tools, stop_after_tool):
            self.assertEqual(payload["allowed_emphases"], ("quote_timing",))
            self.assertEqual(set(payload["allowed_next_inputs"]), {"none", "share_count", "portfolio_context"})
            for rejected in ("purchase_cost", "historical_risk"):
                with self.assertRaises(ValueError):
                    tools[0].handler(emphasis=rejected, next_input="share_count")
            with self.assertRaises(ValueError):
                tools[0].handler(emphasis="quote_timing", next_input="execution_price")
            tools[0].handler(emphasis="quote_timing", next_input="share_count")
            return AgentRun("ok", {})

        runtime.run.side_effect = run
        result = await summarize_live_market(_report(shares=None), runtime)
        self.assertEqual(result["status"], "ready")
        self.assertIn("available AMD trade was USD 122.30 at 2026-11-13T19:30:00+00:00", result["conclusion"])
        self.assertIn("proposed share count", result["conclusion"])
        self.assertNotIn("24,460", result["conclusion"])

    async def test_duplicate_handoff_and_runtime_budget_hold_summary(self):
        runtime = AsyncMock()

        async def run(_role, _payload, *, tools, stop_after_tool):
            tools[0].handler(emphasis="purchase_cost", next_input="portfolio_context")
            with self.assertRaises(ValueError):
                tools[0].handler(emphasis="quote_timing", next_input="execution_price")
            return AgentRun("ok", {})

        runtime.run.side_effect = run
        result = await summarize_live_market(_report(), runtime)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["conclusion"])
        runtime.run.side_effect = RuntimeBudgetExceeded("deadline", {"limit_reached": "deadline"})
        result = await summarize_live_market(_report(), runtime)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["usage"]["limit_reached"], "deadline")
        self.assertEqual(result["stop_reason"], "deadline")

    @unittest.skipIf(find_spec("strands") is None, "Install the pinned Strands SDK to exercise the Bedrock tool.")
    async def test_strands_tool_generates_checked_historical_conclusion(self):
        import boto3
        from botocore.stub import Stubber
        from strands.models import BedrockModel

        trailing = SimpleNamespace(start=date(2026, 8, 17), end=date(2026, 11, 13),
                                   price_return=Decimal("0.12"), max_drawdown=Decimal("0.18"))
        session = boto3.Session(aws_access_key_id="test", aws_secret_access_key="test", region_name=DEFAULT_REGION)
        model = BedrockModel(model_id=DEFAULT_MODEL, streaming=False, boto_session=session)
        with Stubber(model.client) as stub, patch("strands.models.BedrockModel", return_value=model):
            stub.add_response("converse", {
                "output": {"message": {"role": "assistant", "content": [{"toolUse": {
                    "toolUseId": "summary-test", "name": _TOOL, "input": {
                        "emphasis": "historical_risk", "next_input": "portfolio_context", "price_return": 40.0,
                    },
                }}]}},
                "stopReason": "tool_use", "usage": {"inputTokens": 90, "outputTokens": 12, "totalTokens": 102},
                "metrics": {"latencyMs": 2}, "ResponseMetadata": {"RequestId": "summary-test", "HTTPStatusCode": 200},
            })
            result = await summarize_live_market(_report(trailing=trailing), StrandsAgents())
            stub.assert_no_pending_responses()

        self.assertEqual(result["status"], "ready")
        self.assertIn("2026-08-17 through 2026-11-13", result["conclusion"])
        self.assertIn("price return of 12.00%", result["conclusion"])
        self.assertIn("drawdown of 18.00%", result["conclusion"])
        self.assertNotIn("40.0", json.dumps(result))
