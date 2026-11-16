"""Bounded public-data research for the conversational investment workspace.

Yahoo's public chart endpoint is an unofficial research interface. It can be
delayed, changed, or unavailable. Never relabel it as an execution quote.
"""

from datetime import datetime, timedelta, timezone
import json
from math import isfinite
import re
import ssl
import certifi
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPSHandler, Request, build_opener
from zoneinfo import ZoneInfo

from .live_market_data import _NoRedirects
from .review_snapshot import fingerprint


class ResearchUnavailable(ValueError):
    """A public, credential-free explanation of missing research evidence."""


def read_public_json(url):
    request = Request(url, headers={"User-Agent": "AlphaForge-Research/1.0", "Accept": "application/json"})
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with build_opener(_NoRedirects(), HTTPSHandler(context=context)).open(request, timeout=8) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ResearchUnavailable("The data response exceeded the research size limit.")
        return json.loads(raw)
    except HTTPError as exc:
        message = "The source is temporarily limiting requests." if exc.code == 429 else "The source did not return this instrument."
        raise ResearchUnavailable(message) from None
    except URLError as exc:
        category = type(exc.reason).__name__
        if category == "SSLCertVerificationError":
            raise ResearchUnavailable("The source's HTTPS certificate could not be verified. The request was stopped.") from None
        if category == "gaierror":
            raise ResearchUnavailable("The application could not resolve the public data host. Check the server's network connection.") from None
        raise ResearchUnavailable("The application could not connect to the public data source.") from None
    except (OSError, ValueError, RecursionError):
        raise ResearchUnavailable("The public data source is unavailable. No replacement prices were invented.") from None


def positive(value):
    if type(value) not in (float, int) or not isfinite(value) or not 0 < value < 1e12:
        raise ResearchUnavailable("The source returned an invalid price or exchange rate.")
    return float(value)


class PublicResearch:
    """Fetch up to five years of observations, dated prices, and official macro data."""

    def __init__(self, transport=read_public_json, clock=None):
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(self, query, *, search=False):
        query = query.strip().removeprefix("$")
        if not search and re.fullmatch(r"[A-Za-z][A-Za-z0-9.^=\-]{0,11}", query) and (query.isupper() or query.islower()):
            return query.upper()
        url = "https://query1.finance.yahoo.com/v1/finance/search?" + urlencode({"q": query, "quotesCount": 4, "newsCount": 0})
        payload = self.transport(url)
        if not isinstance(payload, dict) or not isinstance(payload.get("quotes", []), list):
            raise ResearchUnavailable("The instrument search returned an invalid response. Add a ticker to your question.")
        choices = [item for item in payload.get("quotes", [])
                   if isinstance(item, dict) and item.get("quoteType") in {"EQUITY", "ETF", "CRYPTOCURRENCY", "MUTUALFUND"}
                   and re.fullmatch(r"[A-Z0-9.^=\-]{1,16}", item.get("symbol", ""))]
        # Prefer an exact company-name/ticker match. Ambiguous names need a ticker.
        exact = [item for item in choices if query.casefold() in
                 {str(item.get(key, "")).casefold() for key in ("symbol", "shortname", "longname")}]
        if len(exact) == 1:
            return exact[0]["symbol"]
        if len(choices) == 1:
            return choices[0]["symbol"]
        raise ResearchUnavailable("This name has multiple listings or no clear match. Add the ticker and exchange to your question.")

    def asset(self, query):
        symbol = self.resolve(query)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?" + urlencode(
            {"range": "5y", "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})
        try:
            payload = self.transport(url)
        except ResearchUnavailable as exc:
            if "did not return this instrument" not in str(exc) or query.isupper():
                raise
            resolved = self.resolve(query, search=True)
            if resolved == symbol:
                raise
            return self.asset(resolved)
        retrieved = self.clock()
        try:
            result = payload["chart"]["result"][0]
            meta = result["meta"]
            if meta["symbol"].upper() != symbol or not re.fullmatch(r"[A-Z]{3}", meta["currency"]):
                raise ValueError("instrument mismatch")
            tz = ZoneInfo(meta["exchangeTimezoneName"])
            as_of = datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc)
            if as_of > retrieved + timedelta(minutes=1):
                raise ValueError("future observation")
            latest = positive(meta["regularMarketPrice"])
            timestamps = result.get("timestamp", [])
            adjusted = result["indicators"]["adjclose"][0]["adjclose"]
            if len(timestamps) != len(adjusted) or len(timestamps) > 2000:
                raise ValueError("inconsistent history")
            today = retrieved.astimezone(tz).date()
            rows, omitted, trading = [], 0, []
            quote_rows = result["indicators"].get("quote", [{}])[0]
            closes, volumes = quote_rows.get("close", []), quote_rows.get("volume", [])
            for index, (timestamp, value) in enumerate(zip(timestamps, adjusted)):
                day = datetime.fromtimestamp(timestamp, tz).date()
                # The current session may still be forming: use completed dates only.
                if day >= today:
                    continue
                if value is None:
                    omitted += 1
                    continue
                if rows and day.isoformat() <= rows[-1]["date"]:
                    raise ValueError("unordered history")
                rows.append({"date": day.isoformat(), "price": positive(value)})
                if index < len(closes) and index < len(volumes) and closes[index] is not None and type(volumes[index]) in (int, float) and 0 <= volumes[index] < 1e14:
                    trading.append({"date": day.isoformat(), "close": positive(closes[index]), "volume": volumes[index]})
            if len(rows) < 20:
                raise ResearchUnavailable("Fewer than twenty completed daily observations were available. A risk report needs a longer sample.")
            result = {
                "symbol": symbol, "name": str(meta.get("longName") or meta.get("shortName") or symbol)[:120],
                "currency": meta["currency"], "exchange": str(meta.get("exchangeName", ""))[:40],
                "price": latest, "price_as_of": as_of.isoformat(), "retrieved_at": retrieved.isoformat(),
                "price_age_days": max(0, (retrieved - as_of).total_seconds() / 86400),
                "rows": rows, "omitted_rows": omitted, "trading": trading,
                "instrument_type": str(meta.get("instrumentType", "unknown")),
                "source": "Yahoo Finance", "source_url": f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/",
                "request_url": url, "adjustment": "provider adjusted close; distributions and splits reflected by provider",
                "terms_url": "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
                "limitations": "Unofficial research interface; prices may be delayed. Exchange-calendar completeness has not been certified.",
            }
            result["digest"] = fingerprint(result)
            return result
        except (AttributeError, KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
            if isinstance(exc, ResearchUnavailable):
                raise
            raise ResearchUnavailable("The price response did not pass instrument, date, and value checks.") from None

    def fx(self):
        now = self.clock()
        url = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?" + urlencode(
            {"start_date": (now.date() - timedelta(days=1850)).isoformat()})
        payload = self.transport(url)
        rows = []
        try:
            for row in payload["observations"]:
                if "FXUSDCAD" not in row:
                    continue
                day = datetime.strptime(row["d"], "%Y-%m-%d").date()
                if day > now.date() or (rows and row["d"] <= rows[-1]["date"]):
                    raise ValueError("invalid FX date")
                rows.append({"date": row["d"], "rate": positive(float(row["FXUSDCAD"]["v"]))})
            if not rows:
                raise ValueError("no FX")
            return {"rows": rows, "retrieved_at": now.isoformat(), "source": "Bank of Canada",
                    "source_url": url, "unit": "CAD per USD", "terms_url": "https://www.bankofcanada.ca/terms/"}
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            raise ResearchUnavailable("A dated Bank of Canada USD/CAD rate was unavailable. CAD conversion is withheld.") from None

    def cpi(self):
        now = self.clock()
        url = "https://www.bankofcanada.ca/valet/observations/V41690973/json?" + urlencode(
            {"start_date": (now.date() - timedelta(days=1900)).isoformat()})
        payload = self.transport(url)
        rows = []
        try:
            for row in payload["observations"]:
                value = row.get("V41690973", {}).get("v")
                if value is None:
                    continue
                month = row["d"][:7]
                datetime.strptime(month, "%Y-%m")
                if month >= now.strftime("%Y-%m") or (rows and month <= rows[-1]["month"]):
                    raise ValueError("invalid CPI month")
                rows.append({"month": month, "index": positive(float(value))})
            if len(rows) < 2:
                raise ValueError("insufficient CPI")
            return {"rows": rows, "retrieved_at": now.isoformat(), "source_url": url,
                    "source": "Statistics Canada all-items CPI via Bank of Canada", "series": "V41690973",
                    "basis": "Monthly all-items Canada CPI, not seasonally adjusted; reference months, not release dates",
                    "vintage": "latest available; publication vintages unavailable"}
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ResearchUnavailable("Usable Canadian CPI observations were unavailable. Purchasing-power results are withheld.") from None
