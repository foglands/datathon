"""Load the competition's frozen CSV snapshot without network access."""

from __future__ import annotations

import csv
import io
import math
import os
import zipfile
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .finance import StressWindow


DATA_CSVS = ("prices_daily.csv", "fx_usdcad_daily.csv", "sources_metadata.csv")
ISSUER_EVIDENCE = {
    "issuer": "NVIDIA Corp.",
    "issuer_id": "CUSIP:67066G104",
    "as_of": "2026-06-30",
    "scope": "NVIDIA common equity as a fraction of fund net assets",
    "holdings": {
        "SPY": {
            "weight": 0.07517011844111,
            "published_on": "2026-08-28",
            "url": "https://www.sec.gov/Archives/edgar/data/884394/000141036826089410/primary_doc.html",
            "source": "SPDR S&P 500 ETF Trust, SEC Form N-PORT, NVIDIA common stock, percentage of fund net assets",
            "status": "disclosed",
        },
        "QQQ": {
            "weight": 0.07596756593966,
            "published_on": "2026-08-28",
            "url": "https://www.sec.gov/Archives/edgar/data/1067839/000106783926000030/primary_doc.html",
            "source": "Invesco QQQ Trust, SEC Form N-PORT, NVIDIA common stock, percentage of fund net assets",
            "status": "disclosed",
        },
        "XIU.TO": {
            "weight": 0.0,
            "published_on": None,
            "url": "https://www.blackrock.com/ca/investors/en/literature/semi-annual-mrfp/sa-mrfp-xiu-en-ca.pdf",
            "source": "BlackRock June 30, 2026 interim report: S&P/TSX 60 strategy, primarily Canadian equities. Zero NVIDIA common stock is a scope assumption.",
            "status": "scope_assumption",
        },
        "ZST.TO": {
            "weight": 0.0,
            "published_on": None,
            "url": "https://bmo.bynder.com/m/649f11fac077a423/original/SA_MRFP_ZST_E.pdf",
            "source": "BMO June 30, 2026 interim report: short-term fixed income portfolio. Zero NVIDIA common stock is a scope assumption.",
            "status": "scope_assumption",
        },
        "NVDA": {
            "weight": 1.0,
            "published_on": None,
            "url": None,
            "source": "Direct NVIDIA common-equity position in the simulated portfolio",
            "status": "direct",
        },
    },
}


@dataclass(frozen=True)
class MarketData:
    """Common-currency prices with observation dates and source metadata."""

    prices: dict[str, dict[str, float]]
    fx: dict[str, float]
    metadata: tuple[dict[str, str], ...] = ()
    source_path: str = ""
    official_starter: bool = False
    source_csvs: tuple[tuple[str, str], ...] = field(default=(), repr=False)


class MarketProvenanceError(ValueError):
    """A CAD price or its source cannot be reconciled with the frozen input."""


def issuer_evidence() -> dict:
    """Return the dated inputs separately from historical market observations."""
    return deepcopy(ISSUER_EVIDENCE)


def issuer_exposure_weights(*, allow_scope_assumptions: bool = False) -> dict[str, float | None]:
    return {
        ticker: (
            row["weight"]
            if row["status"] != "scope_assumption" or allow_scope_assumptions
            else None
        )
        for ticker, row in ISSUER_EVIDENCE["holdings"].items()
    }


def _starter_path(path: str | Path | None) -> Path:
    configured = path if path is not None else os.environ.get("DATATHON_STARTER_PATH")
    if configured is not None:
        resolved = Path(configured).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Starter ZIP or directory not found: {resolved}")
        return resolved

    workspace = Path(__file__).resolve().parent.parent
    candidates = (workspace / "data" / "alphaforge_starter", workspace / "data" / "Datathon2026.zip",
                  workspace / "Datathon2026" / "alphaforge_starter", workspace / "Datathon2026.zip")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Set DATATHON_STARTER_PATH to the official Datathon2026.zip or alphaforge_starter directory."
    )


def _starter_csv_directory(path: Path) -> Path:
    directories = (path, path / "alphaforge_starter", path / "Datathon2026" / "alphaforge_starter")
    for directory in directories:
        if all((directory / file).is_file() for file in DATA_CSVS):
            return directory
    raise FileNotFoundError(f"Missing starter CSVs in {path}")


def market_data_source(path: str | Path | None = None) -> tuple[Path, tuple[tuple[str, int, int, int, int, int], ...]]:
    """Resolve the source and detect replacement for local caching."""
    source = _starter_path(path).resolve()
    if source.is_dir():
        source = _starter_csv_directory(source).resolve()
        files = [source / name for name in DATA_CSVS]
    else:
        files = [source]
    versions = []
    for file in files:
        observed = file.stat()
        versions.append((file.name, observed.st_dev, observed.st_ino, observed.st_size,
                         observed.st_mtime_ns, observed.st_ctime_ns))
    return source, tuple(versions)


def _csv_texts(path: Path) -> dict[str, str]:
    if path.is_dir():
        directory = _starter_csv_directory(path)
        return {file: (directory / file).read_text(encoding="utf-8-sig") for file in DATA_CSVS}

    with zipfile.ZipFile(path) as archive:
        paths = [PurePosixPath(member) for member in archive.namelist()]
        texts = {}
        for file in DATA_CSVS:
            matches = [member for member in paths if member.name == file and member.parent.name == "alphaforge_starter"]
            if len(matches) != 1:
                raise ValueError(f"Expected one alphaforge_starter/{file} in the official ZIP")
            texts[file] = archive.read(str(matches[0])).decode("utf-8-sig")
        return texts


def _csv_rows(text: str, expected: set[str]):
    rows = csv.DictReader(io.StringIO(text), strict=True)
    try:
        columns = rows.fieldnames or []
        if missing := expected - set(columns):
            raise ValueError(f"Missing required CSV columns: {', '.join(sorted(missing))}")
        if len(columns) != len(set(columns)):
            raise ValueError("Duplicate CSV columns.")
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row {rows.line_num}.")
            yield row
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV record at line {rows.line_num}.") from exc


def _positive(value: str, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Invalid {name}: {value}")
    return number


def load_market_data(path: str | Path | None = None) -> MarketData:
    """Read the official ZIP or CSV directory and value all available prices in CAD.

    A USD observation with no same-date Bank of Canada fixing is omitted. The
    stress calculator intersects the remaining price and FX calendars.
    """
    source = _starter_path(path)
    texts = _csv_texts(source)
    fx = {}
    for row in _csv_rows(texts["fx_usdcad_daily.csv"], {"date", "usdcad"}):
        day = date.fromisoformat(row["date"]).isoformat()
        if day in fx:
            raise ValueError(f"Duplicate USD/CAD fixing for {day}")
        fx[day] = _positive(row["usdcad"], "USD/CAD fixing")

    prices: dict[str, dict[str, float]] = {}
    currencies = {}
    seen = set()
    price_rows = _csv_rows(texts["prices_daily.csv"], {"ticker", "date", "adj_close", "currency"})
    for row in price_rows:
        ticker = row["ticker"]
        day = date.fromisoformat(row["date"]).isoformat()
        if not ticker or (ticker, day) in seen:
            raise ValueError(f"Invalid or duplicate price key: {ticker}, {day}")
        seen.add((ticker, day))
        currency = row["currency"]
        if currency not in ("CAD", "USD") or currency != currencies.setdefault(ticker, currency):
            raise ValueError(f"Invalid or inconsistent currency for {ticker}: {currency}")
        price = _positive(row["adj_close"], f"{ticker} adjusted close")
        if currency == "USD" and day not in fx:
            continue
        cad_price = price * fx[day] if currency == "USD" else price
        if not math.isfinite(cad_price) or cad_price <= 0:
            raise ValueError(f"Invalid CAD adjusted close for {ticker} on {day}.")
        prices.setdefault(ticker, {})[day] = cad_price

    metadata_rows = _csv_rows(texts["sources_metadata.csv"], {"file", "source", "source_url", "retrieved_on"})
    return MarketData(prices, fx, tuple(metadata_rows), str(source.resolve()),
                      official_starter=True, source_csvs=tuple(texts.items()))


def _matches_reference(value, reference):
    # The loader rounds source decimals to binary floats before multiplication.
    expected = float(reference)
    return (type(value) in (int, float) and math.isfinite(value) and value > 0
            and math.isfinite(expected) and expected > 0 and abs(value - expected) <= 4 * math.ulp(expected))


def verify_cad_conversion(data: MarketData, *, tickers: Iterable[str], windows: Iterable[StressWindow]) -> dict:
    """Independently rebuild the selected CAD closes from the frozen source CSVs."""
    if not data.source_csvs:
        if data.source_path or data.official_starter:
            raise MarketProvenanceError("The loaded market data have no frozen price and FX records.")
        return {"status": "not_applicable", "reason": "no_raw_price_snapshot"}

    source = dict(data.source_csvs)
    if set(source) != set(DATA_CSVS) or len(source) != len(data.source_csvs):
        raise MarketProvenanceError("The frozen market snapshot does not contain its expected CSVs.")
    tickers = tuple(sorted(set(tickers)))
    windows = tuple(windows)
    if not tickers or not windows:
        raise MarketProvenanceError("Select assets and replay windows before checking CAD conversion.")

    first = min(window.start for window in windows)
    last = max(window.end for window in windows)
    raw_fx = {}
    raw_prices = {ticker: {} for ticker in tickers}
    try:
        for row in _csv_rows(source["fx_usdcad_daily.csv"], {"date", "usdcad"}):
            day = date.fromisoformat(row["date"]).isoformat()
            if first <= day <= last:
                raw_fx[day] = Decimal(row["usdcad"])
        for row in _csv_rows(source["prices_daily.csv"], {"ticker", "date", "adj_close", "currency"}):
            ticker = row["ticker"]
            if ticker in raw_prices:
                day = date.fromisoformat(row["date"]).isoformat()
                if first <= day <= last:
                    raw_prices[ticker][day] = (Decimal(row["adj_close"]), row["currency"])
        recorded_sources = tuple(_csv_rows(source["sources_metadata.csv"], {"file", "source", "source_url", "retrieved_on"}))
    except (ValueError, TypeError, DecimalException) as exc:
        raise MarketProvenanceError("The frozen price or FX records could not be read for checking.") from exc

    if data.metadata != recorded_sources:
        raise MarketProvenanceError("The market source metadata do not match the frozen snapshot.")

    raw_price_days = set.intersection(*(set(raw_prices[ticker]) for ticker in tickers))
    source_days = raw_price_days.intersection(raw_fx)
    missing_fx = raw_price_days - raw_fx.keys()
    converted_days = set(data.fx).intersection(*(data.prices.get(ticker, {}) for ticker in tickers))
    checked_windows = {}
    with localcontext() as context:
        context.prec = 40
        for window in windows:
            source_window = {day for day in source_days if window.start <= day <= window.end}
            converted_window = {day for day in converted_days if window.start <= day <= window.end}
            if not {window.start, window.end}.issubset(source_window) or source_window != converted_window:
                raise MarketProvenanceError(f"The replay dates for {window.id} do not match the frozen price and FX records.")

            for day in sorted(source_window):
                rate = raw_fx[day]
                if not _matches_reference(data.fx[day], rate):
                    raise MarketProvenanceError(f"The USD/CAD fixing for {day} differs from its frozen source.")
                for ticker in tickers:
                    close, currency = raw_prices[ticker][day]
                    if currency not in ("CAD", "USD"):
                        raise MarketProvenanceError(f"The source currency for {ticker} on {day} is unsupported.")
                    expected = close * rate if currency == "USD" else close
                    if not _matches_reference(data.prices[ticker][day], expected):
                        raise MarketProvenanceError(f"The CAD adjusted close for {ticker} on {day} differs from its source.")
            checked_windows[window.id] = {
                "observations": len(source_window),
                "price_observations": len(source_window) * len(tickers),
                "missing_fx_dates": sorted(day for day in missing_fx if window.start <= day <= window.end),
            }

    return {
        "status": "verified", "formula_id": "cad_adjusted_close", "formula_version": "1",
        "price_field": "adj_close", "fx_field": "usdcad", "basis": "CAD",
        "source_sha256": {name: sha256(source[name].encode("utf-8")).hexdigest() for name in DATA_CSVS},
        "windows": checked_windows,
    }
