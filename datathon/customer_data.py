"""Bounded market-data research for the conversational investment workspace.

The organizer's frozen dataset is the first source for every instrument it
covers: dated, hashed, reproducible by the judges, and valued with the Bank of
Canada fixings shipped in the same archive. Yahoo's public chart endpoint is an
unofficial fallback for instruments outside that dataset. It can be delayed,
changed, or unavailable. Never relabel either as an execution quote.
"""

from datetime import datetime, timedelta, timezone
import hashlib
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


PRICE_BASES = {
    "split_adjusted_price": "split-adjusted prices, excluding cash distributions",
    "split_and_cash_distribution_adjusted": "prices adjusted for splits and cash distributions",
}


class ResearchAmbiguous(ValueError):
    """A security name needs a listing choice, with traceable candidates."""
    def __init__(self, query, candidates, source_url):
        super().__init__("Confirm the ticker and exchange: this name does not identify a unique supported security.")
        self.query, self.candidates, self.source_url = query, candidates, source_url


class ResearchUnavailable(ValueError):
    """A public, credential-free explanation of missing research evidence."""

    def __init__(self, message, *, action="Try again if the data service is temporarily unavailable."):
        super().__init__(message)
        self.action = action


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

    def resolve_security(self, query, *, search=False):
        from difflib import SequenceMatcher
        query = query.strip().removeprefix("$")
        if not search and re.fullmatch(r"[A-Za-z][A-Za-z0-9.^=\-]{0,11}", query) and (query.isupper() or query.islower()):
            return {"symbol": query.upper(), "query": query, "method": "ticker hypothesis; chart identity must confirm", "candidates": []}
        url = "https://query1.finance.yahoo.com/v1/finance/search?" + urlencode({"q": query, "quotesCount": 8, "newsCount": 0})
        payload = self.transport(url)
        if not isinstance(payload, dict) or not isinstance(payload.get("quotes", []), list):
            raise ResearchUnavailable("The instrument search returned an invalid response. Add a ticker to your question.")
        choices = [{"symbol": item["symbol"], "name": item.get("longname") or item.get("shortname", ""),
                    "exchange": item.get("exchDisp") or item.get("exchange"), "currency": item.get("currency"),
                    "product_type": item["quoteType"], "source_url": url}
                   for item in payload.get("quotes", []) if isinstance(item, dict)
                   and item.get("quoteType") in {"EQUITY", "ETF", "CRYPTOCURRENCY", "MUTUALFUND"}
                   and re.fullmatch(r"[A-Z0-9.^=\-]{1,16}", item.get("symbol", ""))]
        exact_symbol = [item for item in choices if query.casefold() == item["symbol"].casefold()]
        def normalized(text):
            return re.sub(r"\b(?:inc|corporation|corp|ltd|limited|plc|company)\b|[^a-z0-9 ]", "", text.casefold()).strip()
        def plausible(item):
            name, asked = normalized(item["name"]), normalized(query)
            return (asked == name or (len(asked) >= 4 and name.startswith(asked + " ")) or asked == "".join(x[0] for x in name.split() if x)
                    or (len(asked) >= 5 and SequenceMatcher(None, asked, name).ratio() >= .78))
        matches = exact_symbol or [item for item in choices if plausible(item)]
        if len(matches) != 1:
            raise ResearchAmbiguous(query, choices, url)
        return {"symbol": matches[0]["symbol"], "query": query, "method": "public security search; chart identity must confirm",
                "candidates": choices, "source_url": url, "retrieved_at": self.clock().isoformat()}

    def resolve(self, query, *, search=False):
        try:
            return self.resolve_security(query, search=search)["symbol"]
        except ResearchAmbiguous as exc:
            raise ResearchUnavailable(str(exc)) from None

    def asset(self, query):
        resolution = self.resolve_security(query)
        symbol = resolution["symbol"]
        entered = query.strip().removeprefix("$")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?" + urlencode(
            {"range": "5y", "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})
        try:
            payload = self.transport(url)
        except ResearchUnavailable as exc:
            if "did not return this instrument" not in str(exc):
                raise
            searched = self.resolve_security(query, search=True)
            if searched["symbol"] == symbol:
                raise
            if entered == symbol:
                raise ResearchAmbiguous(query, searched["candidates"], searched["source_url"]) from None
            result = self.asset(searched["symbol"])
            result["resolution"] = {**searched, "verified_exchange": result["exchange"], "verified_currency": result["currency"], "verified_type": result["instrument_type"]}
            result["digest"] = fingerprint({k: v for k, v in result.items() if k != "digest"})
            return result
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
                "price_basis": "split_and_cash_distribution_adjusted",
                "terms_url": "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
                "limitations": "Unofficial research interface; prices may be delayed. Exchange-calendar completeness has not been certified.",
            }
            result["resolution"] = {**resolution, "verified_exchange": result["exchange"],
                "verified_currency": result["currency"], "verified_type": result["instrument_type"]}
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


class StarterResearch:
    """Organizer dataset first; a fallback source only for instruments outside it.

    Every instrument in the frozen archive is served from the archive: the raw
    adjusted close in its listing currency, the same-date Bank of Canada USD/CAD
    fixing, the SHA-256 of the source CSV and the row count. The result keeps the
    public-source shape so the calculators and the report do not change.
    """

    SOURCE = "Organizer dataset (PolyFinances Datathon 2026 starter)"

    def __init__(self, market_data, fallback=None, clock=None):
        from .data import _csv_rows
        self.market_data = market_data
        self.fallback = fallback
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        texts = dict(getattr(market_data, "source_csvs", ()) or ())
        prices_text = texts.get("prices_daily.csv", "")
        self.dataset_sha256 = hashlib.sha256(prices_text.encode("utf-8")).hexdigest() if prices_text else None
        self.series = {}
        self.names = {}
        if prices_text:
            for row in _csv_rows(prices_text, {"ticker", "date", "adj_close", "currency"}):
                record = {"date": row["date"], "price": float(row["adj_close"]), "currency": row["currency"]}
                close, volume = row.get("close"), row.get("volume")
                try:
                    if close not in (None, "") and volume not in (None, ""):
                        record["close"], record["volume"] = float(close), float(volume)
                except ValueError:
                    pass
                if row.get("name"):
                    self.names[row["ticker"]] = row["name"]
                self.series.setdefault(row["ticker"], []).append(record)
        for rows in self.series.values():
            rows.sort(key=lambda item: item["date"])
        self.source_name = getattr(market_data, "source_name", "") or self.SOURCE
        self.archive_label = "configured market snapshot" if getattr(market_data, "source_name", "") else "organizer dataset"
        source = next((row for row in getattr(market_data, "metadata", ()) if row.get("file") == "prices_daily.csv"), {})
        self.source_url = source.get("source_url")
        self.source_retrieved_on = source.get("retrieved_on")
        self.processing = source.get("processing")
        self.source_limitations = source.get("limitations")
        self.price_basis = source.get("price_basis") or (
            "split_and_cash_distribution_adjusted" if self.archive_label == "organizer dataset" else None)
        terms = re.search(r"https?://[^\s)]+", source.get("terms_of_use", "") or "")
        self.terms_url = terms[0] if terms else None

    def covers(self, query):
        return query.strip().removeprefix("$").upper() in self.series

    def resolve_security(self, query, *, search=False):
        if self.covers(query):
            symbol = query.strip().removeprefix("$").upper()
            return {"symbol": symbol, "query": query, "method": self.archive_label + " ticker", "candidates": [],
                    "source_url": self.source_url, "retrieved_at": self.clock().isoformat()}
        if self.fallback is None:
            raise self._outside(query)
        return self.fallback.resolve_security(query, search=search)

    def resolve(self, query, *, search=False):
        try:
            return self.resolve_security(query, search=search)["symbol"]
        except ResearchAmbiguous as exc:
            raise ResearchUnavailable(str(exc)) from None

    def _outside(self, query):
        covered = ", ".join(sorted(self.series))
        return ResearchUnavailable(
            f"{query.strip()} is outside the daily price coverage of the {self.archive_label} ({covered}).",
            action="Use a covered instrument for daily analysis, or ask the app operator to extend price coverage.")

    def asset(self, query):
        if not self.covers(query):
            if self.fallback is None:
                raise self._outside(query)
            resolution = self.fallback.resolve_security(query)
            if self.covers(resolution["symbol"]):
                result = self.asset(resolution["symbol"])
                result["resolution"].update(query=query, method=f"public name resolution; {self.archive_label} prices")
                result["digest"] = fingerprint({k: v for k, v in result.items() if k != "digest"})
                return result
            result = self.fallback.asset(resolution["symbol"])
            result["resolution"] = {**resolution, "verified_exchange": result["exchange"],
                                    "verified_currency": result["currency"], "verified_type": result["instrument_type"]}
            result["coverage"] = f"outside {self.archive_label}; public fallback source"
            result["digest"] = fingerprint({k: v for k, v in result.items() if k != "digest"})
            return result
        symbol = query.strip().removeprefix("$").upper()
        rows = self.series[symbol]
        currency = rows[-1]["currency"]
        if any(row["currency"] != currency for row in rows):
            raise ResearchUnavailable(f"The {self.archive_label} lists {symbol} in more than one currency.")
        retrieved = self.clock()
        last = rows[-1]
        as_of = datetime.fromisoformat(last["date"]).replace(tzinfo=timezone.utc)
        trading = [{"date": row["date"], "close": row["close"], "volume": row["volume"]} for row in rows if "close" in row]
        result = {
            "symbol": symbol, "name": self.names.get(symbol, symbol)[:120], "currency": currency,
            "exchange": self.archive_label, "price": positive(last.get("close", last["price"])), "price_as_of": as_of.isoformat(),
            "price_field": "close" if "close" in last else "adj_close",
            "retrieved_at": retrieved.isoformat(), "price_age_days": max(0, (retrieved - as_of).total_seconds() / 86400),
            "rows": [{"date": row["date"], "price": positive(row["price"])} for row in rows],
            "omitted_rows": 0, "trading": trading, "instrument_type": self.archive_label + " instrument",
            "source": self.source_name, "source_url": self.source_url or "https://polyfinances.ca/datathon",
            "request_url": "alphaforge_starter/prices_daily.csv", "dataset_sha256": self.dataset_sha256,
            "adjustment": self.processing or ("archive adj_close; adjustments are defined by the source metadata"
                          if self.archive_label != "organizer dataset" else "organizer adj_close; dividends and splits reflected by the organizer"),
            "price_basis": self.price_basis,
            "source_retrieved_on": self.source_retrieved_on,
            "terms_url": self.terms_url,
            "coverage": self.archive_label,
            "limitations": f"Frozen dataset; last observation {last['date']}. Historical observation. "
                           + (self.source_limitations or ""),
        }
        result["resolution"] = {"symbol": symbol, "query": query, "method": self.archive_label + " ticker", "candidates": [],
                                "verified_exchange": result["exchange"], "verified_currency": currency, "verified_type": result["instrument_type"]}
        result["digest"] = fingerprint(result)
        return result

    def fx(self):
        now = self.clock()
        fixings = getattr(self.market_data, "fx", {}) or {}
        rows = [{"date": day, "rate": positive(rate)} for day, rate in sorted(fixings.items())]
        if not rows:
            if self.fallback is None:
                raise ResearchUnavailable("The organizer dataset has no USD/CAD fixings. CAD conversion is withheld.")
            return self.fallback.fx()
        return {"rows": rows, "retrieved_at": now.isoformat(), "source": "Bank of Canada (organizer dataset fx_usdcad_daily.csv)",
                "source_url": "https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/", "unit": "CAD per USD",
                "terms_url": "https://www.bankofcanada.ca/terms/"}

    def cpi(self):
        if self.fallback is None:
            raise ResearchUnavailable("Canadian CPI is not part of the organizer price archive and no public source is enabled. Purchasing-power results are withheld.")
        return self.fallback.cpi()


class UnavailableResearch:
    """A provider that explains, for every call, why no market data can be retrieved."""

    def __init__(self, reason):
        self.reason = reason
        self.action = "The app operator needs to configure or repair the daily price source."

    def resolve_security(self, query, *, search=False):
        raise ResearchUnavailable(self.reason, action=self.action)

    def resolve(self, query, *, search=False):
        raise ResearchUnavailable(self.reason, action=self.action)

    def asset(self, query):
        raise ResearchUnavailable(self.reason, action=self.action)

    def fx(self):
        raise ResearchUnavailable(self.reason, action=self.action)

    def cpi(self):
        raise ResearchUnavailable(self.reason, action=self.action)


class BudgetedResearch:
    """Request-local public-data cache and explicit source-call allowance."""
    def __init__(self, source, budget):
        from threading import Lock
        self.source, self.budget = source, budget
        self.cache, self.lock = {}, Lock()

    def _get(self, method, *args):
        from copy import deepcopy
        key = (method, *args)
        with self.lock:
            if key in self.cache:
                return deepcopy(self.cache[key])
            if not self.budget.take("source_calls"):
                raise ResearchUnavailable("The source-call budget was exhausted; existing evidence was retained.")
        result = getattr(self.source, method)(*args)
        with self.lock:
            self.cache[key] = deepcopy(result)
        return result

    def asset(self, query): return self._get("asset", query)
    def fx(self): return self._get("fx")
    def cpi(self): return self._get("cpi")
