"""Describe changes in long-only equity sector exposure with dated evidence."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from math import fsum
from pathlib import Path
from urllib.parse import urlsplit


REFERENCE_DATE = "2026-11-14"
_DEFAULT_TAXONOMY = ("GICS", "2026")
_MAX_CATALOG_BYTES = 64 * 1024
_EPS = 1e-10


def _fraction(value):
    return type(value) in (int, float) and 0 <= value <= 1


def _bounds(value):
    if value is None:
        return 0.0, 1.0
    if _fraction(value):
        return value, value
    if (isinstance(value, (tuple, list)) and len(value) == 2
            and all(_fraction(bound) for bound in value) and value[0] <= value[1]):
        return tuple(value)
    raise ValueError("Exposure coefficients must be fractions or ordered fraction bounds.")


def shared_exposure_change(before_weights, after_weights, exposure_coefficients):
    """Bound after minus before, with the same uncertain coefficient per asset."""
    low, high = [], []
    for ticker in sorted(before_weights.keys() | after_weights.keys()):
        delta = after_weights.get(ticker, 0.0) - before_weights.get(ticker, 0.0)
        if not delta:
            continue
        lower, upper = _bounds(exposure_coefficients.get(ticker))
        first, second = delta * lower, delta * upper
        low.append(min(first, second))
        high.append(max(first, second))
    return {"lower": fsum(low), "upper": fsum(high)}


def _date(value):
    if not isinstance(value, str):
        raise ValueError("Sector evidence dates must use YYYY-MM-DD.")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Sector evidence dates must use YYYY-MM-DD.")
    return parsed


def _source_url(value):
    if not isinstance(value, str) or len(value) > 1000:
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None


@dataclass(frozen=True)
class _SectorEvidence:
    ticker: str
    taxonomy: str
    version: str
    as_of: str
    available_by: str
    source_url: str
    source_locator: str
    denominator: str
    weights: Mapping[str, float]
    non_equity_min: float = 0.0
    equity_fraction: float | None = None

    def __post_init__(self):
        labels = (self.ticker, self.taxonomy, self.version, self.source_locator)
        if (not all(isinstance(value, str) and 0 < len(value.strip()) <= 180 for value in labels)
                or not _source_url(self.source_url) or _date(self.available_by) < _date(self.as_of)
                or not isinstance(self.weights, Mapping) or len(self.weights) > 32
                or not all(isinstance(name, str) and 0 < len(name.strip()) <= 60 and _fraction(value)
                           for name, value in self.weights.items())
                or not _fraction(self.non_equity_min)):
            raise ValueError("Invalid sector evidence record.")
        total = fsum(self.weights.values())
        if self.denominator == "equity_sleeve":
            if not _fraction(self.equity_fraction) or self.non_equity_min > 1 - self.equity_fraction + _EPS:
                raise ValueError("Equity-sleeve weights need an independently evidenced equity fraction.")
            if total > 1 + _EPS:
                raise ValueError("Reported equity-sleeve weights exceed 100%.")
        elif self.denominator == "nav":
            if self.equity_fraction is not None or total + self.non_equity_min > 1 + _EPS:
                raise ValueError("Reported NAV weights and non-equity lower bound exceed the allowed total.")
        elif self.denominator == "position":
            if (self.equity_fraction is not None or self.non_equity_min != 0
                    or len(self.weights) != 1 or total != 1):
                raise ValueError("A direct classification must cover one complete equity position.")
        else:
            raise ValueError("Unsupported sector evidence denominator.")

    def nav_weights(self):
        scale = self.equity_fraction if self.denominator == "equity_sleeve" else 1.0
        return {name: weight * scale for name, weight in self.weights.items()}

    def non_equity(self):
        return 1 - self.equity_fraction if self.denominator == "equity_sleeve" else self.non_equity_min


# Exchange-traded fund exposure differs from the issuer concentration analysis.
# BMO reports 83.8% in its disclosed debt positions. Use 83.7% of NAV as a
# lower bound to leave room for published percentage rounding.
_REFERENCE = (
    _SectorEvidence(
        "NVDA", *_DEFAULT_TAXONOMY, "2026-10-30", REFERENCE_DATE,
        "https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
        "S&P 500 Top 10 Constituents by Index Weight, Oct 30, 2026, NVDA row and GICS footnote",
        "position", {"Information Technology": 1.0},
    ),
    _SectorEvidence(
        "ZST.TO", *_DEFAULT_TAXONOMY, "2026-06-30", REFERENCE_DATE,
        "https://bmo.bynder.com/m/649f11fac077a423/original/SA_MRFP_ZST_E.pdf",
        "June 30, 2026 Summary of Investment Portfolio, Top 25 holdings and NAV total, PDF pp. 4–5",
        "nav", {}, non_equity_min=.837,
    ),
)


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate sector evidence catalog keys.")
    return result


def _load_catalog():
    location = os.environ.get("DATATHON_SECTOR_CATALOG")
    expected_hash = os.environ.get("DATATHON_SECTOR_CATALOG_SHA256")
    if location is None and expected_hash is None:
        return _DEFAULT_TAXONOMY, _REFERENCE, None
    if not location or not expected_hash:
        raise ValueError("The sector catalog requires a local path and SHA-256 pin.")
    try:
        with Path(location).open("rb") as source:
            payload = source.read(_MAX_CATALOG_BYTES + 1)
    except OSError as exc:
        raise ValueError("The reviewed sector catalog is unavailable.") from exc
    if len(payload) > _MAX_CATALOG_BYTES or sha256(payload).hexdigest() != expected_hash:
        raise ValueError("The reviewed sector catalog failed its size or content check.")
    try:
        manifest = json.loads(payload, object_pairs_hook=_unique_object)
        if (not isinstance(manifest, dict) or set(manifest) != {"taxonomy", "version", "records"}
                or not isinstance(manifest["records"], list) or len(manifest["records"]) > 64):
            raise ValueError("Invalid sector catalog shape.")
        taxonomy = (manifest["taxonomy"], manifest["version"])
        if not all(isinstance(value, str) and 0 < len(value.strip()) <= 60 for value in taxonomy):
            raise ValueError("A sector catalog must identify one taxonomy and version.")
        records = tuple(_SectorEvidence(**row) for row in manifest["records"])
        keys = {(row.ticker, row.taxonomy, row.version, row.as_of) for row in records}
        if len(keys) != len(records):
            raise ValueError("Ambiguous duplicate sector records.")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("The reviewed sector catalog is invalid.") from exc
    return taxonomy, records, expected_hash


def _eligible_records(records, taxonomy, tickers, reference, cutoff, max_age_days):
    eligible, ignored = {}, {}
    for row in sorted(records, key=lambda item: (item.as_of, item.available_by)):
        if row.ticker not in tickers:
            continue
        observed = _date(row.as_of)
        if (row.taxonomy, row.version) != taxonomy:
            reason = "taxonomy_mismatch"
        elif observed > reference or _date(row.available_by) > cutoff:
            reason = "outside_evidence_cutoff"
        elif (reference - observed).days > max_age_days:
            reason = "stale_evidence"
        else:
            eligible[row.ticker] = row
            continue
        ignored[row.ticker] = reason
    return eligible, {ticker: ignored.get(ticker, "unavailable") for ticker in sorted(tickers - eligible.keys())}


def sector_analysis(before, after, *, reference_date=REFERENCE_DATE, publication_cutoff=None, max_age_days=180):
    """Describe sector ranges using a shared, bounded, long-only evidence snapshot."""
    for weights in (before, after):
        if (not all(_fraction(weight) for weight in weights.values())
                or abs(fsum(weights.values()) - 1) > _EPS):
            raise ValueError("Sector analysis needs long-only portfolio weights totaling 100%.")
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValueError("Sector evidence age limit must be a nonnegative number of days.")
    reference = _date(reference_date)
    cutoff = min(reference, _date(publication_cutoff)) if publication_cutoff is not None else reference
    tickers = {ticker for weights in (before, after) for ticker, weight in weights.items() if weight}
    taxonomy, records, catalog_hash = _load_catalog()
    evidence, ignored = _eligible_records(records, taxonomy, tickers, reference, cutoff, max_age_days)
    disclosed = {ticker: row.nav_weights() for ticker, row in evidence.items()}
    non_equity = {ticker: row.non_equity() for ticker, row in evidence.items()}
    unknown = {ticker: max(0.0, 1 - fsum(disclosed.get(ticker, {}).values()) - non_equity.get(ticker, 0.0))
               for ticker in tickers}

    def exposure(weights, coefficients):
        return {bound: fsum(weights.get(ticker, 0.0) * values[index] for ticker, values in coefficients.items())
                for index, bound in enumerate(("lower", "upper"))}

    sectors = {}
    for name in sorted({name for weights in disclosed.values() for name in weights}):
        coefficients = {}
        for ticker in tickers:
            lower = disclosed.get(ticker, {}).get(name, 0.0)
            coefficients[ticker] = (lower, min(1.0, lower + unknown[ticker]))
        sectors[name] = {"before": exposure(before, coefficients), "after": exposure(after, coefficients),
                         "change": shared_exposure_change(before, after, coefficients)}
    unmapped = {label: fsum(weights.get(ticker, 0.0) * amount for ticker, amount in unknown.items())
                for label, weights in (("before", before), ("after", after))}
    result = {
        "taxonomy": {"name": taxonomy[0], "level": "sector", "version": taxonomy[1]},
        "denominator": "portfolio_value", "status": ("unavailable" if not evidence else
                                                     "partial" if any(value > _EPS for value in unmapped.values())
                                                     else "complete"),
        "reference_date": reference_date, "publication_cutoff": cutoff.isoformat(), "sectors": sectors,
        "unmapped": unmapped, "known_non_equity_min": {
            label: fsum(weights.get(ticker, 0.0) * amount for ticker, amount in non_equity.items())
            for label, weights in (("before", before), ("after", after))
        },
        "evidence": {ticker: {
            "as_of": row.as_of, "available_by": row.available_by, "url": row.source_url,
            "locator": row.source_locator, "source_denominator": row.denominator,
            "sector_nav_lower": disclosed[ticker], "non_equity_nav_lower": non_equity[ticker],
        } for ticker, row in sorted(evidence.items())},
        "ignored": ignored,
    }
    if catalog_hash is not None:
        result["catalog_sha256"] = catalog_hash
    return result
