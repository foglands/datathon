"""Inventory the official starter and describe its coverage without running an audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from .data import _starter_path
from .finance import BASE_WEIGHTS, STRESS_WINDOWS


_TABLE_COLUMNS = {
    "assets_universe.csv": ("asset_id", "ticker", "name", "asset_class", "market", "currency", "sector"),
    "prices_daily.csv": ("date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "currency"),
    "fx_usdcad_daily.csv": ("date", "usdcad", "cadusd"),
    "corporate_actions.csv": ("ex_date", "ticker", "action", "value", "unit"),
    "macro_rates.csv": ("date", "series_id", "value", "unit", "frequency", "label", "source"),
    "sources_metadata.csv": ("file", "content", "source", "source_url", "retrieved_on", "coverage", "frequency",
                             "processing", "limitations", "terms_of_use"),
}
_WARNING_FILE = "data_quality_warnings.txt"
_RAW_FILES = (*_TABLE_COLUMNS, _WARNING_FILE)


def _documents(path):
    if path.is_dir():
        candidates = (path, path / "alphaforge_starter", path / "Datathon2026" / "alphaforge_starter")
        directory = next((item for item in candidates if all((item / name).is_file() for name in _TABLE_COLUMNS)), None)
        if directory is None:
            raise ValueError("Use the full official starter distribution containing all six CSV tables.")
        return {name: (directory / name).read_bytes().decode("utf-8-sig")
                for name in _RAW_FILES if (directory / name).is_file()}

    with zipfile.ZipFile(path) as archive:
        by_name = defaultdict(list)
        for entry in archive.namelist():
            member = PurePosixPath(entry)
            if member.parent.name == "alphaforge_starter" and member.name in _RAW_FILES:
                by_name[member.name].append(entry)
        if any(len(by_name[name]) != 1 for name in _TABLE_COLUMNS) or len(by_name[_WARNING_FILE]) > 1:
            raise ValueError("Expected exactly one copy of each official starter CSV under alphaforge_starter.")
        return {name: archive.read(entries[0]).decode("utf-8-sig") for name, entries in by_name.items() if entries}


def _tables(documents):
    parsed = {}
    metadata = {}
    for name, required in _TABLE_COLUMNS.items():
        text = documents[name]
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"{name} is missing required columns.")
        rows = list(reader)
        if any(None in row or any(row[key] is None for key in required) for row in rows):
            raise ValueError(f"{name} contains a malformed CSV row.")
        parsed[name] = rows
        metadata[name] = {
            "rows": len(rows), "columns": reader.fieldnames,
            "decoded_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    return parsed, metadata


def _range(values):
    return {"first": min(values, default=None), "last": max(values, default=None)}


def _number(value):
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _positive(value):
    number = _number(value)
    return number is not None and number > 0


def _duplicates(rows, fields):
    counts = Counter(tuple(row[key] for key in fields) for row in rows)
    return sum(count - 1 for count in counts.values())


def _counts(rows, key):
    return dict(sorted(Counter(row[key] for row in rows).items()))


def _window_alignment(price_days, fx_days, events):
    windows = []
    for window in STRESS_WINDOWS:
        def covered(day):
            return window.start <= day <= window.end

        per_asset = {ticker: {day for day in price_days[ticker] if covered(day)} for ticker in BASE_WEIGHTS}
        common = set.intersection(*per_asset.values())
        window_fx = {day for day in fx_days if covered(day)}
        aligned = common & window_fx
        dividends = Counter(row["ticker"] for row in events
                            if row["action"] == "dividend" and covered(row["ex_date"]))
        windows.append({
            "id": window.id, "start": window.start, "end": window.end,
            "price_days_by_asset": {ticker: len(days) for ticker, days in per_asset.items()},
            "available_fx_days": len(window_fx),
            "common_price_days": len(common),
            "common_price_and_fx_days": len(aligned),
            "common_price_dates_without_fx": sorted(common - window_fx),
            "endpoints_present_after_alignment": {day: day in aligned for day in (window.start, window.end)},
            "portfolio_dividend_rows_by_asset": dict(sorted(dividends.items())),
            "portfolio_split_rows": [row for row in events if row["action"] == "split" and covered(row["ex_date"])],
        })
    return windows


def inventory_starter(path=None):
    """Return a descriptive inventory of an organizer ZIP or its extracted starter directory."""
    documents = _documents(_starter_path(path))
    tables, metadata = _tables(documents)
    assets = tables["assets_universe.csv"]
    prices = tables["prices_daily.csv"]
    fx = tables["fx_usdcad_daily.csv"]
    actions = tables["corporate_actions.csv"]
    macro = tables["macro_rates.csv"]
    sources = tables["sources_metadata.csv"]

    universe = {row["ticker"]: row for row in assets}
    prices_by_asset = defaultdict(list)
    price_days = defaultdict(set)
    for row in prices:
        ticker = row["ticker"]
        prices_by_asset[ticker].append(row)
        if _positive(row["adj_close"]):
            price_days[ticker].add(row["date"])
    fx_days = {row["date"] for row in fx if _positive(row["usdcad"])}
    zero_volume = [{"ticker": row["ticker"], "date": row["date"]} for row in prices if _number(row["volume"]) == 0]
    inventory = {}
    for ticker, asset in sorted(universe.items()):
        asset_prices = prices_by_asset.get(ticker, ())
        dates = price_days.get(ticker, set())
        inventory[ticker] = {
            "name": asset["name"], "asset_class": asset["asset_class"], "market": asset["market"],
            "currency": asset["currency"], "sector": asset["sector"], "in_audit_portfolio": ticker in BASE_WEIGHTS,
            "price_rows": len(asset_prices), "valid_adjusted_close_dates": len(dates), "coverage": _range(dates),
            "valid_price_dates_without_fx": len(dates - fx_days) if asset["currency"] == "USD" else None,
        }

    portfolio_events = [row for row in actions if row["ticker"] in BASE_WEIGHTS]
    split_events = [row for row in actions if row["action"] == "split"]
    dividend_events = {(row["ticker"], row["ex_date"]): row for row in actions if row["action"] == "dividend"}
    coincident_actions = [{"split_row": row, "dividend_row": dividend_events[row["ticker"], row["ex_date"]]}
                          for row in split_events if (row["ticker"], row["ex_date"]) in dividend_events]
    macro_series = defaultdict(list)
    for row in macro:
        macro_series[row["series_id"]].append(row)

    return {
        "purpose": "Starter inventory and data diagnostics. No investment or audit verdict is calculated.",
        "tables": metadata,
        "universe": {
            "asset_class_counts": _counts(assets, "asset_class"), "listing_currency_counts": _counts(assets, "currency"),
            "market_counts": _counts(assets, "market"), "assets": inventory,
            "universe_tickers_without_valid_prices": sorted(ticker for ticker in universe if not price_days.get(ticker)),
            "price_tickers_outside_universe": sorted(prices_by_asset.keys() - universe.keys()),
            "duplicate_ticker_rows": _duplicates(assets, ("ticker",)),
        },
        "prices": {
            "coverage": _range([row["date"] for row in prices]),
            "currency_row_counts": _counts(prices, "currency"),
            "duplicate_ticker_date_rows": _duplicates(prices, ("ticker", "date")),
            "invalid_adjusted_close_rows": sum(not _positive(row["adj_close"]) for row in prices),
            "currency_mismatch_rows": sum(row["ticker"] in universe and
                                          universe[row["ticker"]]["currency"] != row["currency"] for row in prices),
            "zero_volume_rows": zero_volume,
        },
        "fx": {
            "coverage": _range(fx_days), "valid_fixing_dates": len(fx_days),
            "duplicate_date_rows": _duplicates(fx, ("date",)),
            "invalid_usdcad_rows": sum(not _positive(row["usdcad"]) for row in fx),
            "inverse_mismatch_rows": sum(not _positive(row["cadusd"]) or not _positive(row["usdcad"]) or
                                         abs(float(row["cadusd"]) - 1 / float(row["usdcad"])) > 0.00000051 for row in fx),
            "method": "Exact same-date USD/CAD fixing, with no carry-forward. CAD listing prices are not converted.",
        },
        "replay_windows": _window_alignment(price_days, fx_days, portfolio_events),
        "corporate_actions": {
            "event_type_counts": _counts(actions, "action"), "coverage": _range([row["ex_date"] for row in actions]),
            "duplicate_event_rows": _duplicates(actions, ("ticker", "ex_date", "action")),
            "split_rows": split_events, "same_day_split_and_dividend_rows": coincident_actions,
            "audit_portfolio_event_counts": {
                ticker: _counts([row for row in portfolio_events if row["ticker"] == ticker], "action")
                for ticker in BASE_WEIGHTS
            },
            "treatment": "Adjusted closes already reflect the vendor's treatment of splits and distributions. "
                         "Event rows are context and are not reapplied. ETF distributions may be incomplete.",
        },
        "macro": {
            "use": "Descriptive provenance only. No macro values enter the current audit or its counterfactuals.",
            "series": {
                name: {
                    "rows": len(rows), "coverage": _range([row["date"] for row in rows]),
                    "labels": sorted({row["label"] for row in rows}), "units": sorted({row["unit"] for row in rows}),
                    "frequencies": sorted({row["frequency"] for row in rows}),
                    "sources": sorted({row["source"] for row in rows}),
                }
                for name, rows in sorted(macro_series.items())
            },
            "duplicate_series_date_rows": _duplicates(macro, ("series_id", "date")),
            "invalid_value_rows": sum(_number(row["value"]) is None for row in macro),
            "caution": "Observation period and release date differ, and source values can be revised. "
                       "The starter lacks the publication-vintage history needed for historical signals.",
        },
        "source_metadata": sources,
        "organizer_build_warnings": {"available": _WARNING_FILE in documents,
                                     "text": documents.get(_WARNING_FILE, "").strip() or None},
        "limitations": [
            "The organizer-curated 2026 asset universe may embed survivorship bias. It is a seeded sample.",
            "Price and corporate-action records use a vendor snapshot. Back-adjusted historical values can change "
            "on subsequent downloads. See the source metadata terms before redistributing data.",
            "Exchange and currency-fixing dates differ. Crypto rows are UTC calendar dates and are not "
            "synchronized with exchange-close quotes.",
            "The organizer notes that the CNQ.TO 1.021 split-like event flagged on 2022-08-22 may instead "
            "reflect a special distribution. It is retained as a vendor record without reclassification.",
            "This inventory describes availability and coverage. It supplies no ESG ratings, news, "
            "company fundamentals or look-through fund holdings.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Official starter ZIP or extracted directory.")
    parser.add_argument("--report", type=Path, help="Write JSON to this path. Defaults to stdout.")
    args = parser.parse_args()
    try:
        report = inventory_starter(args.data)
    except (FileNotFoundError, UnicodeError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
