"""Freeze and independently reconcile market prices for a hypothetical decision."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
import io
from itertools import pairwise
import math
import re
from urllib.parse import urlsplit

from .data import DATA_CSVS, MarketData, MarketProvenanceError
from .finance import STRESS_WINDOWS
from .market_calendar import STARTER_CALENDAR_ASSETS, starter_calendar_coverage, starter_replay_sessions
from .review_snapshot import fingerprint
from .scope import EXTRA_WINDOW


_PRICE_FILE, _FX_FILE, _METADATA_FILE = DATA_CSVS
_UPLOAD_FILE = "uploaded_prices.csv"
_PRICE_COLUMNS = {"ticker", "date", "adj_close", "currency"}
_SYMBOL = re.compile(r"[A-Z^][A-Z0-9_.=^-]{0,23}")
_NUMBER = re.compile(r"[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_CRYPTO = frozenset({"BTC-USD", "ETH-USD"})
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class MarketDecisionEvidenceError(MarketProvenanceError):
    """Frozen inputs are invalid or provide no usable common window."""

    def __init__(self, reason, message, **details):
        super().__init__(message)
        self.reason = reason
        self.details = details


@dataclass(frozen=True)
class _Observation:
    text: str
    number: float
    line: int


@dataclass(frozen=True)
class _PriceSeries:
    source_file: str
    currency: str
    rows: dict[str, _Observation]


def _day(value):
    if type(value) is date:
        return value.isoformat()
    parsed = date.fromisoformat(value).isoformat()
    if value != parsed:
        raise ValueError("Use a calendar date in YYYY-MM-DD format.")
    return parsed


def _positive(value):
    if len(value) > 100 or not _NUMBER.fullmatch(value):
        raise ValueError("Expected a positive decimal number.")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Expected a finite positive number.")
    return number


def _rows(contents, columns, *, exact=False):
    reader = csv.reader(io.StringIO(contents, newline=""), strict=True)
    try:
        header = next(reader, [])
        if len(header) != len(set(header)) or not columns <= set(header) or (exact and set(header) != columns):
            raise ValueError(f"Expected columns {', '.join(sorted(columns))} without duplicates.")
        while True:
            first_line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                return
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(f"Malformed CSV row at line {first_line}.")
            yield first_line, dict(zip(header, row))
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV record near line {reader.line_num}.") from exc


def _read_prices(contents, source_file, tickers, *, available_on):
    series = {}
    keys = set()
    currencies = {}
    for line, row in _rows(contents, _PRICE_COLUMNS, exact=source_file == _UPLOAD_FILE):
        ticker = row["ticker"]
        currency = row["currency"]
        try:
            day = _day(row["date"])
            number = _positive(row["adj_close"])
            if not _SYMBOL.fullmatch(ticker) or (ticker, day) in keys:
                raise ValueError(f"Invalid or duplicate price key {ticker} on {day}.")
            if currency not in {"CAD", "USD"} or currency != currencies.setdefault(ticker, currency):
                raise ValueError(f"Invalid or inconsistent currency for {ticker}.")
            if day > available_on:
                raise ValueError(f"Price on {day} is later than the source's availability date.")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{source_file} line {line}: {exc}") from exc
        keys.add((ticker, day))
        if ticker in tickers:
            item = series.setdefault(ticker, _PriceSeries(source_file, currency, {}))
            item.rows[day] = _Observation(row["adj_close"], number, line)
    if not keys:
        raise ValueError(f"{source_file} has no price records.")
    return series


def _read_fixings(contents, *, retrieved_on):
    result = {}
    for line, row in _rows(contents, {"date", "usdcad"}):
        try:
            day = _day(row["date"])
            if day in result:
                raise ValueError(f"Duplicate USD/CAD fixing on {day}.")
            if day > retrieved_on:
                raise ValueError(f"Fixing on {day} is later than the source's retrieval date.")
            result[day] = _Observation(row["usdcad"], _positive(row["usdcad"]), line)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{_FX_FILE} line {line}: {exc}") from exc
    return result


def _public_url(value):
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise ValueError("Provide a source URL using HTTP or HTTPS.")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None:
        raise ValueError("Provide a source URL using HTTP or HTTPS without embedded credentials.")
    return value


def _official_sources(data, tickers):
    try:
        source = dict(data.source_csvs)
        if set(source) != set(DATA_CSVS) or len(data.source_csvs) != len(source):
            raise ValueError("The official snapshot requires frozen price, FX and metadata CSVs.")
        records = tuple(row for _, row in _rows(source[_METADATA_FILE],
                                               {"file", "source", "source_url", "retrieved_on"}))
        if records != data.metadata:
            raise ValueError("The loaded source metadata differ from the frozen metadata CSV.")
        metadata = {}
        for row in records:
            name = row["file"]
            if name not in {_PRICE_FILE, _FX_FILE}:
                continue
            if name in metadata or not row["source"].strip():
                raise ValueError(f"Missing or duplicate source attribution for {name}.")
            _public_url(row["source_url"])
            _day(row["retrieved_on"])
            metadata[name] = row
        if set(metadata) != {_PRICE_FILE, _FX_FILE}:
            raise ValueError("The price and FX CSVs both require dated source metadata.")
        prices = _read_prices(source[_PRICE_FILE], _PRICE_FILE, tickers,
                              available_on=metadata[_PRICE_FILE]["retrieved_on"])
        fixings = _read_fixings(source[_FX_FILE], retrieved_on=metadata[_FX_FILE]["retrieved_on"])
        hashes = {name: sha256(value.encode("utf-8")).hexdigest() for name, value in source.items()}
    except (AttributeError, TypeError, ValueError) as exc:
        raise MarketDecisionEvidenceError("corrupt_official_evidence", str(exc)) from exc
    return prices, fixings, metadata, hashes


def _uploaded_sources(upload, upload_source, upload_published_on, tickers):
    if upload is None:
        if upload_source is not None or upload_published_on is not None:
            raise MarketDecisionEvidenceError("invalid_upload", "Supply the CSV along with its source and publication date.")
        return {}, {}, {}
    try:
        source_url = _public_url(upload_source)
        publication = _day(upload_published_on)
        if isinstance(upload, str):
            upload = upload.encode("utf-8")
        elif isinstance(upload, (bytearray, memoryview)):
            upload = bytes(upload)
        if not isinstance(upload, bytes) or not 0 < len(upload) <= _MAX_UPLOAD_BYTES:
            raise ValueError("Supply a UTF-8 price CSV of up to 5 MiB.")
        content = upload.decode("utf-8-sig")
        prices = _read_prices(content, _UPLOAD_FILE, tickers, available_on=publication)
    except (TypeError, ValueError) as exc:
        raise MarketDecisionEvidenceError("invalid_upload", f"Invalid price CSV upload: {exc}") from exc
    metadata = {_UPLOAD_FILE: {
        "file": _UPLOAD_FILE, "source": "User-supplied adjusted-close CSV", "source_url": source_url,
        "published_on": publication, "limitations": "Source and publication date provided by the user.",
    }}
    return prices, metadata, {_UPLOAD_FILE: sha256(upload).hexdigest()}


def _converted_prices(series, fixings, knowledge_date):
    converted = {}
    for ticker, price in series.items():
        result = {}
        for day, close in price.rows.items():
            if day > knowledge_date or (price.currency == "USD" and day not in fixings):
                continue
            value = close.number * fixings[day].number if price.currency == "USD" else close.number
            if not math.isfinite(value) or value <= 0:
                raise MarketDecisionEvidenceError("invalid_cad_price", f"Invalid CAD adjusted close for {ticker} on {day}.")
            result[day] = value
        converted[ticker] = result
    return converted


def _matches(observed, expected):
    try:
        return (type(observed) in {int, float} and math.isfinite(observed) and observed > 0
                and math.isfinite(expected) and expected > 0 and abs(observed - expected) <= 4 * math.ulp(expected))
    except OverflowError:
        return False


def _check_conversions(data, series, converted, fixings, knowledge_date):
    """Rebuild eligible dates and CAD values from source strings using Decimal."""
    needs_fx = any(price.currency == "USD" for price in series.values())
    fx_reference = {day: Decimal(row.text) for day, row in fixings.items()} if needs_fx else {}
    if needs_fx and fixings:
        loaded = {day for day in data.fx if day <= knowledge_date}
        if loaded != fx_reference.keys():
            raise MarketDecisionEvidenceError("fx_mismatch", "The loaded FX dates differ from the frozen source.")
        for day, rate in fx_reference.items():
            if not _matches(data.fx[day], float(rate)):
                raise MarketDecisionEvidenceError("fx_mismatch", f"The loaded USD/CAD fixing on {day} differs from its source.")

    with localcontext() as context:
        context.prec = 240
        for ticker, price in series.items():
            raw_days = {day for day in price.rows if day <= knowledge_date}
            expected_days = raw_days & fx_reference.keys() if price.currency == "USD" else raw_days
            if expected_days != converted[ticker].keys():
                raise MarketDecisionEvidenceError("price_mismatch", f"The CAD price dates for {ticker} differ from the source.")
            loaded = data.prices.get(ticker, {}) if price.source_file == _PRICE_FILE else None
            if loaded is not None and (fixings or price.currency == "CAD"):
                if {day for day in loaded if day <= knowledge_date} != expected_days:
                    raise MarketDecisionEvidenceError("price_mismatch", f"The loaded price dates for {ticker} differ from the source.")
            else:
                loaded = None
            for day in expected_days:
                close = Decimal(price.rows[day].text)
                expected = float(close * fx_reference[day] if price.currency == "USD" else close)
                if (not _matches(converted[ticker][day], expected)
                        or (loaded is not None and not _matches(loaded[day], expected))):
                    raise MarketDecisionEvidenceError(
                        "price_mismatch", f"The CAD adjusted close for {ticker} on {day} differs from its source."
                    )


def _in_range(days, start, end):
    return {day for day in days if start <= day <= end}


def _calendar_days(start, end):
    first = date.fromisoformat(start)
    count = (date.fromisoformat(end) - first).days + 1
    return (first + timedelta(days=offset) for offset in range(count))


def _unverified_weekday_gaps(price_days):
    """Report interior weekday absences without treating them as exchange sessions."""
    gaps = []
    for before, after in pairwise(date.fromisoformat(day) for day in sorted(price_days)):
        first, last = before + timedelta(days=1), after - timedelta(days=1)
        if first.weekday() >= 5:
            first += timedelta(days=7 - first.weekday())
        if last.weekday() >= 5:
            last -= timedelta(days=last.weekday() - 4)
        if first <= last:
            weeks, remainder = divmod((last - first).days + 1, 7)
            weekdays = weeks * 5 + sum((first.weekday() + offset) % 7 < 5 for offset in range(remainder))
            gaps.append({"start": first.isoformat(), "end": last.isoformat(), "weekdays": weekdays})
    return gaps


def _calendar_reference(start, end, series):
    # The pinned joint calendar excludes US holidays. CAD-only portfolios have
    # different trading sessions and cannot inherit this reference.
    if not (set(series) <= STARTER_CALENDAR_ASSETS and any(p.currency == "USD" for p in series.values())
            and all(p.source_file == _PRICE_FILE for p in series.values())):
        return None
    try:
        return starter_replay_sessions(start, end)
    except KeyError:
        return None


def _coverage(start, end, dates, series, raw, converted, fixings, official, crypto_range):
    expected = _calendar_reference(start, end, series) if official else None
    common_raw = set.intersection(*raw.values())
    needs_fx = any(p.currency == "USD" for p in series.values())
    coverage = starter_calendar_coverage(
        start, end, dates, applicable=expected is not None, price_dates=common_raw,
        fixing_dates=fixings if needs_fx else None,
    )
    coverage["observations"] = len(dates)
    coverage["missing_fx_dates"] = sorted({day for ticker, price in series.items() if price.currency == "USD"
                                           for day in raw[ticker] if day not in fixings})
    coverage["by_ticker"] = {}
    observed_other = set.union(*raw.values())
    for ticker, price in series.items():
        price_days = raw[ticker]
        usable_days = _in_range(converted[ticker], start, end)
        per_asset_expected = expected
        calendar = coverage["calendar_id"]
        if ticker in _CRYPTO and price.source_file == _PRICE_FILE and crypto_range:
            left, right = max(start, crypto_range[0]), min(end, crypto_range[1])
            per_asset_expected = {day.isoformat() for day in _calendar_days(left, right)}
            calendar = "official-starter-crypto-utc-daily"
        missing = sorted(per_asset_expected - price_days) if per_asset_expected is not None else []
        coverage["by_ticker"][ticker] = {
            "expected_raw_calendar": calendar,
            "raw_observations": len(price_days), "cad_observations": len(usable_days),
            "first_raw_date": min(price_days, default=None), "last_raw_date": max(price_days, default=None),
            "missing_expected_raw_dates": missing,
            "unverified_weekday_gaps": _unverified_weekday_gaps(price_days) if per_asset_expected is None else [],
            "other_observed_dates_without_price": sorted(observed_other - price_days),
            "missing_fx_dates": sorted(price_days - fixings.keys()) if price.currency == "USD" else [],
        }
    if any(row["missing_expected_raw_dates"] for row in coverage["by_ticker"].values()):
        coverage["status"] = "incomplete"
    if coverage["status"] == "coverage_not_verified":
        coverage["reason"] = "independent_joint_session_calendar_unavailable"
    return coverage


def _window_specs(eligible, include_2023, custom_start, custom_end, excluded):
    price_days = set.union(*eligible.values())
    specs = {"full_history": (min(price_days), max(price_days))} if price_days else {}
    if not price_days:
        excluded["full_history"] = "No eligible adjusted closes in the supplied sources."
    specs.update({window.id: (window.start, window.end) for window in STRESS_WINDOWS})
    if include_2023:
        specs[EXTRA_WINDOW.id] = (EXTRA_WINDOW.start, EXTRA_WINDOW.end)
    if custom_start is not None or custom_end is not None:
        try:
            start, end = _day(custom_start), _day(custom_end)
            if start >= end:
                raise ValueError("End must be later than start.")
        except (TypeError, ValueError):
            excluded["custom"] = "Enter a valid start and later end date for the custom window."
        else:
            specs["custom"] = (start, end)
    return specs


def _window_data(series, converted, fixings, knowledge_date, specs, excluded, eligible, official, crypto_range):
    result = {}
    common = set.intersection(*(set(days) for days in converted.values()))
    for name, (start, end) in specs.items():
        dates = sorted(_in_range(common, start, end))
        if end > knowledge_date:
            excluded[name] = f"The requested window ends after the {knowledge_date} knowledge date."
        elif len(dates) < 2:
            excluded[name] = "Fewer than two shared adjusted closes with required same-day FX."
        elif name in {"2022", "2023", "2025"} and (dates[0] != start or dates[-1] != end):
            excluded[name] = "A fixed replay endpoint lacks a shared adjusted close or required same-day FX."
        else:
            raw = {ticker: _in_range(days, start, end) for ticker, days in eligible.items()}
            result[name] = {
                "start": start, "end": end,
                "dates": dates,
                "cad_prices": {ticker: [converted[ticker][day] for day in dates] for ticker in series},
                "local_prices": {ticker: [price.rows[day].number for day in dates] for ticker, price in series.items()},
                "coverage": _coverage(start, end, dates, series, raw, converted, fixings, official, crypto_range),
            }
    return result


def _row_lookups(windows, series, fixings):
    dates = sorted({day for window in windows.values() for day in window["dates"]})
    result = {}
    for ticker, price in series.items():
        result[ticker] = {}
        for day in dates:
            close = price.rows[day]
            row = {"source_file": price.source_file, "line": close.line, "adj_close": close.text,
                   "currency": price.currency}
            if price.currency == "USD":
                fixing = fixings[day]
                row.update(fx_source_file=_FX_FILE, fx_line=fixing.line, usdcad=fixing.text)
            result[ticker][day] = row
    return result


def prepare_market(data: MarketData, tickers, *, knowledge_date=None, custom_start=None, custom_end=None,
                   include_2023=False, upload=None, upload_source=None, upload_published_on=None) -> dict:
    """Build aligned CAD and listing-currency panels from dated frozen evidence.

    Organizer prices are a retrospective snapshot. They become eligible on
    their retrieval date. An uploaded series supplements symbols absent from
    eligible organizer data and its availability is the declared publication
    date. USD quotes are multiplied by same-date Bank of Canada USD/CAD.
    """
    if isinstance(tickers, str):
        tickers = (tickers,)
    try:
        tickers = tuple(tickers)
    except TypeError as exc:
        raise MarketDecisionEvidenceError("invalid_tickers", "Select valid market symbols to compare.") from exc
    if any(not isinstance(t, str) or not _SYMBOL.fullmatch(t) for t in tickers):
        raise MarketDecisionEvidenceError("invalid_tickers", "Select valid market symbols to compare.")
    tickers = tuple(sorted(set(tickers)))
    if not tickers:
        raise MarketDecisionEvidenceError("invalid_tickers", "Select at least one market symbol to compare.")

    official, all_fixings, metadata, hashes = _official_sources(data, tickers)
    uploaded, upload_meta, upload_hash = _uploaded_sources(upload, upload_source, upload_published_on, tickers)
    price_available = metadata[_PRICE_FILE]["retrieved_on"]
    fx_available = metadata[_FX_FILE]["retrieved_on"]
    upload_available = upload_meta.get(_UPLOAD_FILE, {}).get("published_on")
    try:
        as_of = (_day(knowledge_date) if knowledge_date is not None else
                 max(price_available, fx_available, upload_available or price_available))
    except (TypeError, ValueError) as exc:
        raise MarketDecisionEvidenceError("invalid_knowledge_date", "Enter a valid knowledge date in YYYY-MM-DD format.") from exc

    series = {ticker: official[ticker] for ticker in tickers if ticker in official and price_available <= as_of}
    if upload_available and upload_available <= as_of:
        for ticker, price in uploaded.items():
            series.setdefault(ticker, price)
    missing = sorted(set(tickers) - series.keys())
    if missing:
        later = [ticker for ticker in missing if ticker in official or ticker in uploaded]
        if later:
            raise MarketDecisionEvidenceError("source_after_knowledge_date",
                                             f"No eligible dated price source for {', '.join(missing)} as of {as_of}.",
                                             tickers=missing, knowledge_date=as_of)
        raise MarketDecisionEvidenceError("missing_tickers", f"No frozen adjusted closes for {', '.join(missing)}.",
                                         tickers=missing, knowledge_date=as_of)

    fixings = {day: row for day, row in all_fixings.items() if day <= as_of} if fx_available <= as_of else {}
    converted = _converted_prices(series, fixings, as_of)
    _check_conversions(data, series, converted, fixings, as_of)
    eligible = {ticker: {day for day in price.rows if day <= as_of} for ticker, price in series.items()}
    excluded = {}
    specs = _window_specs(eligible, include_2023, custom_start, custom_end, excluded)
    declared_range = metadata[_PRICE_FILE].get("coverage", "").split(" to ")
    crypto_range = None
    if data.official_starter and len(declared_range) == 2:
        try:
            crypto_range = (_day(declared_range[0]), _day(declared_range[1]))
        except ValueError:
            pass
    windows = _window_data(series, converted, fixings, as_of, specs, excluded, eligible, data.official_starter,
                           crypto_range)
    if not windows:
        message = ("No shared market window. The frozen USD/CAD snapshot was unavailable on the knowledge date."
                   if not fixings and fx_available > as_of and any(p.currency == "USD" for p in series.values())
                   else "No shared market window has enough eligible prices and same-day FX.")
        raise MarketDecisionEvidenceError("no_usable_window", message, excluded=excluded, knowledge_date=as_of)

    limitations = [
        "The organizer price history is a retrieved, back-adjusted snapshot. Earlier periods are retrospective replays.",
        "Shared observations use same-date USD/CAD only. Exchange or FX closures and missing rows can reduce coverage.",
        "Weekday gaps without an independent calendar can include exchange holidays.",
    ]
    if upload_meta:
        limitations.append("The upload source and publication date are user-declared.")
        retained = sorted(t for t in uploaded if series[t].source_file == _PRICE_FILE)
        if retained:
            limitations.append(f"The organizer series was retained for {', '.join(retained)} as one source per ticker.")
    provenance = {
        "status": "verified", "basis": "CAD", "formula_id": "cad_adjusted_close", "formula_version": "1",
        "price_field": "adj_close", "fx_field": "usdcad",
        "source_sha256": {**hashes, **upload_hash}, "source_metadata": {**metadata, **upload_meta},
        "knowledge_date": as_of, "currencies": {ticker: price.currency for ticker, price in series.items()},
        "price_rows": _row_lookups(windows, series, fixings), "limitations": limitations,
        "windows": {name: {"start": row["start"], "end": row["end"], "first_date": row["dates"][0],
                           "last_date": row["dates"][-1], "observations": len(row["dates"])}
                    for name, row in windows.items()},
    }
    provenance["input_digest"] = fingerprint({
        "formula_version": provenance["formula_version"], "source_sha256": provenance["source_sha256"],
        "source_metadata": provenance["source_metadata"], "knowledge_date": as_of,
        "tickers": {ticker: price.source_file for ticker, price in series.items()},
        "window_specs": specs, "excluded": excluded,
    })
    return {"windows": windows, "provenance": provenance, "excluded": excluded, "knowledge_date": as_of}
