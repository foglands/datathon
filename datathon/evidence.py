"""Qualify the frozen issuer disclosures for a dated portfolio audit."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit


ISSUER_SCOPE = "NVIDIA common equity as a fraction of fund net assets"
DEFAULT_HOLDINGS_MAX_AGE_DAYS = 180
_ISSUER_ID = "CUSIP:67066G104"
_DIRECT_TICKER = "NVDA"
_MAX_CATALOG_BYTES = 64 * 1024
_HASH = re.compile(r"[a-f0-9]{64}")
_RECORD_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_TICKER = re.compile(r"[A-Z][A-Z0-9.]{0,14}")


@dataclass(frozen=True)
class ReviewedDisclosure:
    id: str
    ticker: str
    as_of: str
    published_on: str
    weight: float
    url: str
    source: str
    source_document_sha256: str
    source_locator: str
    catalog_sha256: str

    def row(self):
        return {
            "status": "disclosed", "as_of": self.as_of, "published_on": self.published_on,
            "weight": self.weight, "url": self.url, "source": self.source, "reviewed_disclosure_id": self.id,
            "source_document_sha256": self.source_document_sha256, "source_locator": self.source_locator,
            "catalog_sha256": self.catalog_sha256,
        }


def load_issuer_catalog() -> dict[str, ReviewedDisclosure]:
    """Load operator-reviewed disclosures from a content-pinned, local catalog."""
    location = os.environ.get("DATATHON_ISSUER_CATALOG")
    expected_hash = os.environ.get("DATATHON_ISSUER_CATALOG_SHA256")
    if location is None and expected_hash is None:
        return {}
    if not location or not expected_hash or not _HASH.fullmatch(expected_hash):
        raise ValueError("The reviewed issuer catalog needs a local path and a valid SHA-256 pin.")
    try:
        with Path(location).open("rb") as source:
            payload = source.read(_MAX_CATALOG_BYTES + 1)
    except OSError as exc:
        raise ValueError("The reviewed issuer catalog is unavailable.") from exc
    if len(payload) > _MAX_CATALOG_BYTES or sha256(payload).hexdigest() != expected_hash:
        raise ValueError("The reviewed issuer catalog failed its size or content check.")

    def unique_keys(pairs):
        result = dict(pairs)
        if len(pairs) != len(result):
            raise ValueError("Duplicate reviewed issuer catalog keys.")
        return result

    try:
        manifest = json.loads(payload, object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("The reviewed issuer catalog is not valid JSON.") from exc
    if (not isinstance(manifest, dict) or set(manifest) != {"issuer_id", "scope", "disclosures"} or
            manifest["issuer_id"] != _ISSUER_ID or manifest["scope"] != ISSUER_SCOPE):
        raise ValueError("The reviewed issuer catalog has an incompatible issuer or scope.")
    records = manifest["disclosures"]
    if not isinstance(records, list) or len(records) > 64:
        raise ValueError("The reviewed issuer catalog must contain at most 64 disclosures.")

    catalog = {}
    dates = set()
    fields = set(ReviewedDisclosure.__annotations__) - {"catalog_sha256"}
    for record in records:
        if not isinstance(record, dict) or record.keys() != fields:
            raise ValueError("A reviewed disclosure has invalid fields.")
        disclosure = ReviewedDisclosure(**record, catalog_sha256=expected_hash)
        observed = _calendar_date(disclosure.as_of)
        publication = _calendar_date(disclosure.published_on)
        url = _text(disclosure.url)
        if (
            not _RECORD_ID.fullmatch(_text(disclosure.id) or "") or
            not _TICKER.fullmatch(_text(disclosure.ticker) or "") or disclosure.ticker == _DIRECT_TICKER or
            not _HASH.fullmatch(_text(disclosure.source_document_sha256) or "") or
            not all(isinstance(value, str) and 0 < len(value.strip()) <= 300
                    for value in (disclosure.source, disclosure.source_locator)) or
            not _public_url(url) or not url.startswith("https://") or len(url) > 1000 or
            not observed or not publication or publication < observed or
            type(disclosure.weight) not in (float, int) or not 0 <= disclosure.weight <= 1
        ):
            raise ValueError("A reviewed disclosure has invalid values.")
        key = (disclosure.ticker, observed)
        if disclosure.id in catalog or key in dates:
            raise ValueError("The reviewed issuer catalog contains conflicting disclosure records.")
        dates.add(key)
        catalog[disclosure.id] = disclosure
    return catalog


def eligible_issuer_disclosures(snapshot, catalog):
    """Return pinned records usable for holdings that are still unresolved."""
    reference = _calendar_date(snapshot.get("reference_date"))
    cutoff = _calendar_date(snapshot.get("publication_cutoff"))
    age = snapshot.get("max_age_days")
    if not reference or not cutoff or type(age) is not int or age < 0:
        return {}
    return {
        record.id: record for record in catalog.values()
        if record.ticker in snapshot["holdings"] and snapshot["holdings"][record.ticker]["weight"] is None
        and _qualify(record.row(), _calendar_date(record.as_of), reference, cutoff, age, True)[0] == "disclosed"
    }


def add_issuer_disclosures(snapshot, disclosure_ids, *, assets, **context):
    """Extend only unqualified rows with one eligible pinned disclosure per fund."""
    if not isinstance(disclosure_ids, (list, tuple)) or not disclosure_ids or len(disclosure_ids) > 64:
        raise ValueError("Select one or more reviewed disclosures.")
    if any(not isinstance(item, str) or not _RECORD_ID.fullmatch(item) for item in disclosure_ids):
        raise ValueError("Select reviewed disclosure identifiers.")
    qualified = validate_issuer_snapshot(snapshot, assets=assets, **context)
    catalog = load_issuer_catalog()
    holdings = qualified["holdings"]
    if any(item not in catalog or catalog[item].ticker not in holdings or
           holdings[catalog[item].ticker]["weight"] is not None for item in disclosure_ids):
        raise ValueError("A disclosure is unavailable or its holding is already covered.")
    selected = [catalog[item] for item in disclosure_ids]
    if len({record.ticker for record in selected}) != len(selected):
        raise ValueError("Select one reviewed disclosure per fund.")
    supplemented = deepcopy(snapshot)
    for record in selected:
        supplemented["holdings"][record.ticker] = record.row()
    return supplemented


def _calendar_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _public_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.username is None
    except ValueError:
        return False


def _qualify(
    row: Mapping,
    observed: date | None,
    reference: date,
    cutoff: date,
    max_age_days: int,
    scope_valid: bool,
) -> tuple[str, str]:
    status = row.get("status")
    if status is None or status == "unknown":
        return "unknown", "missing_holding_disclosure"
    if status == "scope_assumption":
        return "scope_assumption", "scope_assumption_is_unverified"
    if status != "disclosed":
        return "invalid", "unsupported_disclosure_status"
    if not scope_valid or row.get("scope", ISSUER_SCOPE) != ISSUER_SCOPE or row.get("issuer_id", _ISSUER_ID) != _ISSUER_ID:
        return "invalid", "incompatible_issuer_scope"
    if observed is None or ("as_of" in row and _calendar_date(row["as_of"]) != observed):
        return "invalid", "invalid_or_inconsistent_holdings_date"
    if observed > reference:
        return "future", "holdings_after_reference_date"
    if row.get("published_on") in (None, ""):
        return "unknown", "missing_publication_date"
    published = _calendar_date(row["published_on"])
    if not published or published < observed:
        return "invalid", "invalid_publication_date"
    if published > min(reference, cutoff):
        return "future", "publication_after_knowledge_cutoff"
    if (reference - observed).days > max_age_days:
        return "stale", "holdings_older_than_max_age"
    if not _public_url(_text(row.get("url"))):
        return "invalid", "missing_or_invalid_source_url"
    weight = row.get("weight")
    if type(weight) not in (int, float) or not 0 <= weight <= 1:
        return "invalid", "invalid_exposure_fraction"
    return "disclosed", "verified_disclosure"


def validate_issuer_snapshot(
    snapshot: Mapping | None,
    *,
    reference_date: str,
    publication_cutoff: str,
    max_age_days: int = DEFAULT_HOLDINGS_MAX_AGE_DAYS,
    assets: Iterable[str] | None = None,
) -> dict:
    """Return effective issuer weights and an auditable record of unusable holdings.

    Dates are calendar dates in YYYY-MM-DD format. A disclosure must be known
    by both the reference date and publication cutoff. The freshness limit
    compares the holdings observation date with the reference date, inclusively.
    Missing or unqualified ETF disclosures have an unknown effective weight.
    The direct NVDA position is defined by the simulation portfolio.
    """
    reference = _calendar_date(reference_date)
    cutoff = _calendar_date(publication_cutoff)
    if reference is None or cutoff is None:
        raise ValueError("Issuer reference date and publication cutoff must be YYYY-MM-DD dates.")
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValueError("Issuer disclosure maximum age must be a nonnegative number of days.")

    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    raw_holdings = snapshot.get("holdings")
    raw_holdings = raw_holdings if isinstance(raw_holdings, Mapping) else {}
    scope_valid = snapshot.get("scope") == ISSUER_SCOPE and snapshot.get("issuer_id", _ISSUER_ID) == _ISSUER_ID
    observed = _calendar_date(snapshot.get("as_of"))
    tickers = dict.fromkeys(raw_holdings if assets is None else assets)
    tickers[_DIRECT_TICKER] = None
    holdings = {}
    catalog = (
        load_issuer_catalog()
        if any(isinstance(row, Mapping) and "reviewed_disclosure_id" in row for row in raw_holdings.values()) else {}
    )

    for ticker in tickers:
        if ticker == _DIRECT_TICKER:
            holdings[ticker] = {
                "as_of": None, "published_on": None, "age_days": None, "url": None,
                "source": "Direct NVIDIA common-equity position in the simulated portfolio",
                "status": "direct", "reason": "direct_equity", "weight": 1.0,
                "reported_status": None, "reported_weight": None,
            }
            continue

        raw_row = raw_holdings.get(ticker)
        row = raw_row if isinstance(raw_row, Mapping) else {}
        supplement_id = row.get("reviewed_disclosure_id")
        record = catalog.get(supplement_id) if isinstance(supplement_id, str) else None
        supplement_matches = record is not None and record.ticker == ticker and row == record.row()
        if "reviewed_disclosure_id" in row and not supplement_matches:
            status, reason = "invalid", "unrecognized_reviewed_disclosure"
        else:
            fund_observed = _calendar_date(record.as_of) if supplement_matches else observed
            status, reason = _qualify(row, fund_observed, reference, cutoff, max_age_days, scope_valid)
        row_as_of = row.get("as_of", snapshot.get("as_of")) if isinstance(raw_row, Mapping) else None
        row_date = _calendar_date(row_as_of)
        url = _text(row.get("url"))
        reported_weight = row.get("weight")
        # Keep malformed scalar records useful for review without writing NaN or infinity to JSON.
        if type(reported_weight) not in (int, float, str, bool) or (
            type(reported_weight) is float and not isfinite(reported_weight)
        ):
            reported_weight = None
        holdings[ticker] = {
            "as_of": _text(row_as_of), "published_on": _text(row.get("published_on")),
            "age_days": (reference - row_date).days if row_date is not None else None,
            "url": url if _public_url(url) else None, "source": _text(row.get("source")),
            "status": status, "reason": reason,
            "reported_status": _text(row.get("status")), "reported_weight": reported_weight,
            "weight": float(reported_weight) if status == "disclosed" else None,
        }
        if supplement_matches:
            for field in ("reviewed_disclosure_id", "source_document_sha256", "source_locator", "catalog_sha256"):
                holdings[ticker][field] = row[field]

    return {
        "issuer": _text(snapshot.get("issuer")), "issuer_id": _text(snapshot.get("issuer_id")),
        "scope": _text(snapshot.get("scope")), "as_of": observed.isoformat() if observed else None,
        "reference_date": reference_date, "publication_cutoff": publication_cutoff,
        "max_age_days": max_age_days, "holdings": holdings,
        "issuer_weights": {ticker: row["weight"] for ticker, row in holdings.items()},
    }
