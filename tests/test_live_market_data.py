import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from datathon.live_market_data import AlpacaMarketData, MarketDataError, normalize_symbol


_NOW = datetime(2026, 11, 15, 21, tzinfo=timezone.utc)
_START = date(2026, 11, 12)
_END = date(2026, 11, 13)


class AlpacaMarketDataTests(unittest.TestCase):
    def _client(self, transport, **settings):
        return AlpacaMarketData("fixture-key", "fixture-secret", transport=transport, clock=lambda: _NOW, **settings)

    def test_latest_trade_carries_provenance_and_actual_timestamp(self):
        transport = Mock(return_value={
            "symbol": "AMD", "trade": {"t": "2026-11-13T19:54:06.123456789Z", "p": Decimal("145.60")},
        })
        quote = self._client(transport, feed="delayed_sip").latest_quote(" $amd ")
        self.assertEqual(quote.symbol, "AMD")
        self.assertEqual(quote.price, Decimal("145.60"))
        self.assertEqual(quote.currency, "USD")
        self.assertEqual(quote.as_of, datetime(2026, 11, 13, 19, 54, 6, 123456, tzinfo=timezone.utc))
        self.assertEqual(quote.retrieved_at, _NOW)
        self.assertEqual(quote.feed, "delayed_sip")

        request, timeout = transport.call_args.args
        url = urlsplit(request.full_url)
        self.assertEqual((url.scheme, url.hostname, url.path), ("https", "data.alpaca.markets", "/v2/stocks/AMD/trades/latest"))
        self.assertEqual(parse_qs(url.query), {"feed": ["delayed_sip"], "currency": ["USD"]})
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Apca-api-key-id"), "fixture-key")
        self.assertEqual(request.get_header("Apca-api-secret-key"), "fixture-secret")
        self.assertNotIn("fixture", request.full_url)
        self.assertLessEqual(timeout, 8)

    def test_wrong_symbol_currency_future_or_invalid_price_is_rejected(self):
        good = {"symbol": "AMD", "trade": {"t": "2026-11-13T19:54:06Z", "p": 145}}
        cases = (
            {**good, "symbol": "NVDA"}, {**good, "currency": "CAD"},
            {**good, "trade": {**good["trade"], "t": "2026-11-16T19:54:06Z"}},
            {**good, "trade": {**good["trade"], "t": "2026-11-13"}},
            {**good, "trade": {**good["trade"], "p": float("nan")}},
            {**good, "trade": {**good["trade"], "p": Decimal("1e1000000000")}},
            {**good, "trade": {**good["trade"], "p": Decimal("1e-1000000000")}},
            {**good, "trade": {**good["trade"], "p": 0}},
            {**good, "trade": {**good["trade"], "p": True}},
        )
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(MarketDataError) as exc:
                self._client(Mock(return_value=payload)).latest_quote("AMD")
            self.assertEqual(exc.exception.code, "invalid_data")

    def test_history_collects_pages_and_validates_against_separate_market_calendar(self):
        transport = Mock(side_effect=[
            {"symbol": "AMD", "bars": [{"t": "2026-11-12T05:00:00Z", "c": 140}], "next_page_token": "fixture+token"},
            {"symbol": "AMD", "bars": [{"t": "2026-11-13T05:00:00Z", "c": Decimal("145.60")}]},
            [{"date": "2026-11-12"}, {"date": "2026-11-13"}],
        ])
        history = self._client(transport, feed="delayed_sip").daily_history("AMD", start=_START, end=_END)
        self.assertEqual(tuple(row.session for row in history.closes), (_START, _END))
        self.assertEqual(tuple(row.close for row in history.closes), (Decimal("140"), Decimal("145.60")))
        self.assertEqual(history.expected_sessions, (_START, _END))
        self.assertIsNone(history.calendar_error)
        self.assertEqual(history.adjustment, "split")
        self.assertEqual(history.feed, "sip")
        urls = [urlsplit(call.args[0].full_url) for call in transport.call_args_list]
        self.assertEqual((urls[0].hostname, urls[0].path), ("data.alpaca.markets", "/v2/stocks/AMD/bars"))
        self.assertEqual(parse_qs(urls[0].query)["timeframe"], ["1Day"])
        self.assertEqual(parse_qs(urls[0].query)["start"], ["2026-11-12T00:00:00-05:00"])
        self.assertEqual(parse_qs(urls[1].query)["page_token"], ["fixture+token"])
        self.assertEqual((urls[2].hostname, urls[2].path), ("paper-api.alpaca.markets", "/v2/calendar"))

    def test_calendar_failure_does_not_claim_complete_history(self):
        transport = Mock(side_effect=[
            {"symbol": "AMD", "bars": [{"t": "2026-11-13T05:00:00Z", "c": 145}]},
            URLError("private diagnostic"),
        ])
        history = self._client(transport).daily_history("AMD", start=_START, end=_END)
        self.assertIsNone(history.expected_sessions)
        self.assertEqual(history.calendar_error, "connection_error")
        self.assertEqual(len(history.closes), 1)

    def test_duplicate_dates_or_repeated_page_token_are_rejected(self):
        bar = {"t": "2026-11-13T05:00:00Z", "c": 145}
        cases = (
            [{"symbol": "AMD", "bars": [bar, bar]}],
            [{"symbol": "AMD", "bars": [], "next_page_token": "same"}] * 2,
        )
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(MarketDataError) as exc:
                self._client(Mock(side_effect=pages)).daily_history("AMD", start=_START, end=_END)
            self.assertEqual(exc.exception.code, "invalid_data")

    def test_bad_input_and_missing_credentials_do_not_call_network(self):
        transport = Mock()
        for symbol in ("https://example.com", "../orders", "ÄMD", "AMD,TSLA"):
            with self.subTest(symbol=symbol), self.assertRaises(MarketDataError) as exc:
                self._client(transport).latest_quote(symbol)
            self.assertEqual(exc.exception.code, "invalid_symbol")
        self.assertEqual(normalize_symbol("brk.b"), "BRK.B")
        with self.assertRaises(MarketDataError) as exc:
            self._client(transport).daily_history("AMD", start=_START, end=_NOW.date())
        self.assertEqual(exc.exception.code, "invalid_history_range")
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(MarketDataError) as exc:
            AlpacaMarketData.from_environment()
        self.assertEqual(exc.exception.code, "not_configured")
        transport.assert_not_called()

    def test_secret_and_provider_error_body_are_not_exposed(self):
        codes = {401: "unauthorized", 403: "unauthorized", 429: "rate_limited", 500: "provider_unavailable"}
        for http_code, code in codes.items():
            failure = HTTPError("https://example.com", http_code, "private diagnostic", None, None)
            with self.subTest(http_code=http_code), self.assertRaises(MarketDataError) as exc:
                self._client(Mock(side_effect=failure)).latest_quote("AMD")
            self.assertEqual(exc.exception.code, code)
            self.assertNotIn("private diagnostic", str(exc.exception))
            self.assertNotIn("fixture-secret", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
