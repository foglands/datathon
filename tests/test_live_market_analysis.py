"""The online analysis publishes only evidence-backed local calculations."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import json
import unittest
from unittest.mock import patch

from datathon.live_market_analysis import analyze_share_purchase
from datathon.live_market_data import DailyClose, DailyHistory, MarketQuote


class LiveMarketAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.sessions = tuple(date(2025, 6, day) for day in (2, 3, 4, 5))
        self.now = datetime(2025, 6, 6, 17, 0, 5, tzinfo=timezone.utc)
        self.quote = MarketQuote(
            symbol="AMD", price=Decimal("145.31"), currency="USD", as_of=self.now.replace(second=0),
            retrieved_at=self.now, source="Alpaca", source_url="https://data.alpaca.markets/v2/stocks/AMD/trades/latest",
            feed="iex",
        )
        self.history = DailyHistory(
            symbol="AMD", currency="USD",
            closes=tuple(DailyClose(day, Decimal(value)) for day, value in zip(self.sessions, ("100", "125", "100", "112"))),
            start=self.sessions[0], end=self.sessions[-1], retrieved_at=self.now, source="Alpaca",
            source_url="https://data.alpaca.markets/v2/stocks/AMD/bars", feed="iex", adjustment="split",
            expected_sessions=self.sessions, calendar_source_url="https://paper-api.alpaca.markets/v2/calendar",
        )

    def test_last_trade_notional_and_independently_checked_adjusted_history(self):
        with localcontext() as ctx:
            ctx.prec = 4
            result = analyze_share_purchase("AMD", "1,200.5", self.quote, self.history)

        self.assertEqual(result.shares, Decimal("1200.5"))
        self.assertEqual(result.indicative_notional, Decimal("174444.655"))
        self.assertEqual(result.trailing.price_return, Decimal("0.12"))
        self.assertEqual(result.trailing.max_drawdown, Decimal("0.20"))
        self.assertEqual((result.trailing.start, result.trailing.end), (self.sessions[0], self.sessions[3]))
        self.assertEqual((result.trailing.peak_date, result.trailing.trough_date), (self.sessions[1], self.sessions[2]))

        evidence = json.loads(json.dumps(result.as_model_evidence(), allow_nan=False))
        self.assertEqual(evidence["quote"]["price"], "145.31")
        self.assertEqual(evidence["quote"]["currency"], "USD")
        self.assertEqual(evidence["quote"]["as_of"], self.quote.as_of.isoformat())
        self.assertEqual(evidence["quote"]["feed"], "iex")
        self.assertEqual(evidence["trailing"]["adjustment"], "split")
        self.assertEqual(evidence["trailing"]["observations"], 4)
        self.assertEqual(evidence["trailing"]["calendar_source_url"], self.history.calendar_source_url)
        self.assertEqual(evidence["scope"]["portfolio_impact"], "unassessed")
        self.assertIsNone(evidence["history_withheld_reason"])

    def test_research_without_quantity_or_history_has_no_inferred_amount(self):
        result = analyze_share_purchase("AMD", None, self.quote)
        self.assertIsNone(result.shares)
        self.assertIsNone(result.indicative_notional)
        self.assertIsNone(result.trailing)
        self.assertIn("unavailable", result.history_withheld_reason)

    def test_missing_invalid_and_unnormalized_history_cannot_produce_risk_metrics(self):
        for change in (
            {"expected_sessions": None},
            {"calendar_source_url": None},
            {"closes": self.history.closes[::2]},
            {"closes": tuple(reversed(self.history.closes))},
            {"closes": (*self.history.closes[:2], self.history.closes[1], self.history.closes[-1])},
            {"closes": (DailyClose(self.sessions[0], Decimal("NaN")), *self.history.closes[1:])},
            {"adjustment": "raw"},
            {"currency": "CAD"},
            {"symbol": "MSFT"},
        ):
            with self.subTest(change=change):
                result = analyze_share_purchase("AMD", "200", self.quote, replace(self.history, **change))
                self.assertEqual(result.indicative_notional, Decimal("29062.00"))
                self.assertIsNone(result.trailing)
                self.assertTrue(result.history_withheld_reason)

    def test_invalid_quantities_and_quotes_are_rejected_before_calculation(self):
        for quantity in ("0", "-2", "1,27", "2e3", "12 shares"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                analyze_share_purchase("AMD", quantity, self.quote)
        for change in ({"symbol": "MSFT"}, {"price": Decimal("Infinity")}, {"price": Decimal("1e1000000000")},
                       {"as_of": self.now.replace(second=6)}, {"as_of": self.now.replace(tzinfo=None)}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                analyze_share_purchase("AMD", "200", replace(self.quote, **change))

    def test_history_is_withheld_when_independent_check_fails(self):
        with patch("datathon.live_market_analysis._review_trailing", return_value=False):
            result = analyze_share_purchase("AMD", "200", self.quote, self.history)
        self.assertIsNone(result.trailing)
        self.assertIn("independent", result.history_withheld_reason)
