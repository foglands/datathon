"""Read-only, time-stamped U.S. equity data from the Alpaca Market Data API."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from os import environ
import re
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


_MARKET_HOST = "https://data.alpaca.markets"
_CALENDAR_HOSTS = {"paper": "https://paper-api.alpaca.markets", "live": "https://api.alpaca.markets"}
_FEEDS = frozenset({"iex", "sip", "delayed_sip"})
_SOURCE = "Alpaca Market Data"
_CURRENCY = "USD"
_ADJUSTMENT = "split"
_NEW_YORK = ZoneInfo("America/New_York")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,7}(?:\.[A-Z][A-Z0-9]{0,2})?", re.ASCII)
_TIMESTAMP = re.compile(
    r"(?P<second>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?(?P<offset>Z|[+-][0-9]{2}:[0-9]{2})"
)
_MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
_MAX_HISTORY_DAYS = 366
_MAX_BAR_PAGES = 4


class MarketDataError(Exception):
    """A stable category and a message that excludes authentication and response details."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class MarketQuote:
    """The last eligible executed trade on the selected feed."""

    symbol: str
    price: Decimal
    currency: str
    as_of: datetime
    retrieved_at: datetime
    source: str
    source_url: str
    feed: str


@dataclass(frozen=True)
class DailyClose:
    session: date
    close: Decimal


@dataclass(frozen=True)
class DailyHistory:
    symbol: str
    currency: str
    closes: tuple[DailyClose, ...]
    start: date
    end: date
    retrieved_at: datetime
    source: str
    source_url: str
    feed: str
    adjustment: str
    expected_sessions: tuple[date, ...] | None = None
    calendar_source_url: str | None = None
    calendar_error: str | None = None


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize_symbol(value: str) -> str:
    if not isinstance(value, str) or not value.isascii():
        raise MarketDataError("invalid_symbol", "Enter a U.S. equity ticker such as AMD or BRK.B.")
    symbol = value.strip().removeprefix("$").upper()
    if not _SYMBOL.fullmatch(symbol):
        raise MarketDataError("invalid_symbol", "Enter a U.S. equity ticker such as AMD or BRK.B.")
    return symbol


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid_data() -> MarketDataError:
    return MarketDataError("invalid_data", "The market data response did not pass validation.")


def _timestamp(value) -> datetime:
    match = _TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise _invalid_data()
    fraction = (match["fraction"] or "").ljust(6, "0")[:6]
    offset = "+00:00" if match["offset"] == "Z" else match["offset"]
    try:
        return datetime.fromisoformat(f"{match['second']}.{fraction}{offset}").astimezone(timezone.utc)
    except ValueError:
        raise _invalid_data() from None


def _price(value) -> Decimal:
    if type(value) not in (int, float, Decimal):
        raise _invalid_data()
    price = Decimal(str(value))
    if not price.is_finite() or price <= 0:
        raise _invalid_data()
    representation = price.as_tuple()
    if not -32 <= representation.exponent <= 16 or len(representation.digits) > 34 or price.adjusted() > 16:
        raise _invalid_data()
    return price


def _checked_payload(payload, symbol):
    if not isinstance(payload, dict) or payload.get("symbol") != symbol or payload.get("currency", _CURRENCY) != _CURRENCY:
        raise _invalid_data()
    return payload


def _read_json(request: Request, timeout: float):
    with build_opener(_NoRedirects()).open(request, timeout=timeout) as response:
        raw = response.read(_MAX_PAYLOAD_BYTES + 1)
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise _invalid_data()
    return json.loads(raw, parse_float=Decimal)


def _http_error(status: int) -> MarketDataError:
    if status in {401, 403}:
        return MarketDataError("unauthorized", "Alpaca rejected the API credentials or access to the selected feed.")
    if status == 429:
        return MarketDataError("rate_limited", "Alpaca reached its request limit. Try again later.")
    if status == 404:
        return MarketDataError("no_data", "Alpaca returned no matching data for this request.")
    return MarketDataError("provider_unavailable", "Alpaca did not return usable market data.")


def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=_NEW_YORK)


class AlpacaMarketData:
    """Fetch and validate eligible latest trades, split-adjusted daily bars and market dates."""

    def __init__(
        self, key_id: str, secret_key: str, *, feed: str = "iex", account: str = "paper",
        timeout: float = 8.0, transport: Callable = _read_json, clock: Callable[[], datetime] = _utc_now,
    ):
        if not key_id or not secret_key:
            raise MarketDataError("not_configured", "Configure Alpaca market data credentials on the application server.")
        if feed not in _FEEDS or account not in _CALENDAR_HOSTS:
            raise MarketDataError("invalid_configuration", "The configured Alpaca feed or account environment is unsupported.")
        self._key_id = key_id
        self._secret_key = secret_key
        self.feed = feed
        self._calendar_host = _CALENDAR_HOSTS[account]
        self._timeout = timeout
        self._transport = transport
        self._clock = clock

    @classmethod
    def from_environment(cls):
        return cls(
            environ.get("APCA_API_KEY_ID", "").strip(),
            environ.get("APCA_API_SECRET_KEY", "").strip(),
            feed=environ.get("DATATHON_ALPACA_FEED", "iex").strip().lower(),
            account=environ.get("DATATHON_ALPACA_ACCOUNT", "paper").strip().lower(),
        )

    def _request(self, endpoint: str, params: dict, deadline: float):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise MarketDataError("timeout", "The market data request exceeded its time budget.")
        request = Request(f"{endpoint}?{urlencode(params)}", headers={"Accept": "application/json"})
        request.add_unredirected_header("APCA-API-KEY-ID", self._key_id)
        request.add_unredirected_header("APCA-API-SECRET-KEY", self._secret_key)
        try:
            return self._transport(request, remaining)
        except HTTPError as exc:
            raise _http_error(exc.code) from None
        except TimeoutError:
            raise MarketDataError("timeout", "The market data request exceeded its time budget.") from None
        except (URLError, OSError):
            raise MarketDataError("connection_error", "The application could not connect to Alpaca.") from None
        except (ValueError, RecursionError):
            raise _invalid_data() from None

    def latest_quote(self, symbol: str) -> MarketQuote:
        symbol = normalize_symbol(symbol)
        endpoint = f"{_MARKET_HOST}/v2/stocks/{symbol}/trades/latest"
        payload = self._request(endpoint, {"feed": self.feed, "currency": _CURRENCY}, monotonic() + self._timeout)
        retrieved_at = self._clock()
        trade = _checked_payload(payload, symbol).get("trade")
        if trade is None:
            raise MarketDataError("no_data", "Alpaca returned no eligible trade for this ticker and feed.")
        if not isinstance(trade, dict):
            raise _invalid_data()
        as_of = _timestamp(trade.get("t"))
        if as_of > retrieved_at:
            raise _invalid_data()
        return MarketQuote(symbol, _price(trade.get("p")), _CURRENCY, as_of, retrieved_at, _SOURCE, endpoint, self.feed)

    def daily_history(self, symbol: str, *, start: date, end: date) -> DailyHistory:
        symbol = normalize_symbol(symbol)
        today = self._clock().astimezone(_NEW_YORK).date()
        if (type(start) is not date or type(end) is not date or end >= today or start > end
                or (end - start).days >= _MAX_HISTORY_DAYS):
            raise MarketDataError("invalid_history_range", "Select up to 366 calendar days ending before today in New York.")

        deadline = monotonic() + self._timeout
        endpoint = f"{_MARKET_HOST}/v2/stocks/{symbol}/bars"
        # The delayed SIP feed is a latest-trade option. Completed SIP bars use the SIP feed.
        history_feed = "sip" if self.feed == "delayed_sip" else self.feed
        params = {
            "feed": history_feed, "currency": _CURRENCY, "adjustment": _ADJUSTMENT,
            "timeframe": "1Day", "sort": "asc", "limit": _MAX_HISTORY_DAYS,
            "start": _local_midnight(start).isoformat(),
            "end": (_local_midnight(end + timedelta(days=1)) - timedelta(microseconds=1)).isoformat(),
        }
        closes = self._daily_closes(endpoint, params, start, end, symbol, deadline)
        if not closes:
            raise MarketDataError("no_data", "Alpaca returned no completed daily prices for this ticker and date range.")

        calendar_url = f"{self._calendar_host}/v2/calendar"
        try:
            calendar = self._request(calendar_url, {"start": start.isoformat(), "end": end.isoformat()}, deadline)
            sessions = self._validate_sessions(calendar, start, end)
        except MarketDataError as exc:
            sessions, calendar_error = None, exc.code
        else:
            calendar_error = None
        return DailyHistory(symbol, _CURRENCY, closes, start, end, self._clock(), _SOURCE, endpoint,
                            history_feed, _ADJUSTMENT, sessions, calendar_url, calendar_error)

    def _daily_closes(self, endpoint, params, start, end, symbol, deadline) -> tuple[DailyClose, ...]:
        closes = {}
        used_tokens = set()
        for _ in range(_MAX_BAR_PAGES):
            payload = _checked_payload(self._request(endpoint, params, deadline), symbol)
            bars = payload.get("bars")
            if bars is None:
                bars = []
            if not isinstance(bars, list) or len(bars) > _MAX_HISTORY_DAYS:
                raise _invalid_data()
            for bar in bars:
                if not isinstance(bar, dict):
                    raise _invalid_data()
                session = _timestamp(bar.get("t")).astimezone(_NEW_YORK).date()
                if session in closes or not start <= session <= end:
                    raise _invalid_data()
                closes[session] = _price(bar.get("c"))
            token = payload.get("next_page_token")
            if token is None:
                return tuple(DailyClose(session, closes[session]) for session in sorted(closes))
            if not isinstance(token, str) or not token or len(token) > 1024 or token in used_tokens:
                raise _invalid_data()
            used_tokens.add(token)
            params = {**params, "page_token": token}
        raise MarketDataError("incomplete_history", "Alpaca returned more daily price pages than the application can verify.")

    @staticmethod
    def _validate_sessions(calendar, start, end) -> tuple[date, ...]:
        if not isinstance(calendar, list) or not 1 <= len(calendar) <= _MAX_HISTORY_DAYS:
            raise _invalid_data()
        sessions = set()
        for entry in calendar:
            raw_date = entry.get("date") if isinstance(entry, dict) else None
            try:
                session = date.fromisoformat(raw_date)
            except (ValueError, TypeError):
                raise _invalid_data() from None
            if session in sessions or raw_date != session.isoformat() or not start <= session <= end:
                raise _invalid_data()
            sessions.add(session)
        return tuple(sorted(sessions))
