"""Interpret, retrieve, verify, and explain a current market-data request."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .live_market_analysis import analyze_share_purchase
from .live_market_data import AlpacaMarketData, MarketDataError
from .live_market_intake import configured_live_market_intake_runtime, interpret_live_market_request
from .live_market_summary import summarize_live_market
from .model_settings import configured_bedrock_runtime


async def run_live_market_workflow(question, *, intake_runtime=None, summary_runtime=None,
                                   provider_factory=None, today: date | None = None):
    """Run the data and summary stages only for a source-grounded market request."""
    intake = await interpret_live_market_request(question, intake_runtime or configured_live_market_intake_runtime())
    result = {"intake": intake, "analysis": None, "market_error": None, "history_error": None, "summary": None}
    if intake["status"] != "ready":
        return result

    try:
        provider = (provider_factory or AlpacaMarketData.from_environment)()
        quote = await asyncio.to_thread(provider.latest_quote, intake["symbol"])
    except MarketDataError as exc:
        result["market_error"] = str(exc)
        return result

    history = None
    if intake["scope"] == "quote_and_history":
        # Request complete New York sessions through yesterday. Today's close may still be forming.
        today = today or datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date()
        try:
            history = await asyncio.to_thread(provider.daily_history, intake["symbol"],
                                              start=today - timedelta(days=90), end=today - timedelta(days=1))
        except MarketDataError as exc:
            result["history_error"] = str(exc)

    try:
        analysis = analyze_share_purchase(intake["symbol"], intake.get("shares"), quote, history)
    except ValueError:
        result["market_error"] = "The market observation did not pass verification."
        return result
    result["analysis"] = analysis
    result["summary"] = await summarize_live_market(analysis, summary_runtime or configured_bedrock_runtime(profile=True))
    return result
