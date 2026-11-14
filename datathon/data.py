"""Load the competition's frozen CSV snapshot without network access."""

from __future__ import annotations

import csv
import io
import math
import os
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath


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


def _csv_texts(path: Path) -> dict[str, str]:
    if path.is_dir():
        directories = (path, path / "alphaforge_starter", path / "Datathon2026" / "alphaforge_starter")
        for directory in directories:
            if all((directory / file).is_file() for file in DATA_CSVS):
                return {file: (directory / file).read_text(encoding="utf-8-sig") for file in DATA_CSVS}
        raise FileNotFoundError(f"Missing starter CSVs in {path}")

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
    rows = csv.DictReader(io.StringIO(text))
    if not rows.fieldnames or not expected.issubset(rows.fieldnames):
        raise ValueError(f"Missing required CSV columns: {', '.join(sorted(expected - set(rows.fieldnames or ())))}")
    return rows


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
        prices.setdefault(ticker, {})[day] = price * fx[day] if currency == "USD" else price

    metadata_rows = _csv_rows(texts["sources_metadata.csv"], {"file", "source", "source_url", "retrieved_on"})
    return MarketData(prices, fx, tuple(metadata_rows), str(source.resolve()))
