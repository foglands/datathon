"""Qualify the frozen issuer disclosures for a dated portfolio audit."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from math import isfinite
from urllib.parse import urlsplit


ISSUER_SCOPE = "NVIDIA common equity as a fraction of fund net assets"
DEFAULT_HOLDINGS_MAX_AGE_DAYS = 180
_ISSUER_ID = "CUSIP:67066G104"
_DIRECT_TICKER = "NVDA"


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
        status, reason = _qualify(row, observed, reference, cutoff, max_age_days, scope_valid)
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

    return {
        "issuer": _text(snapshot.get("issuer")), "issuer_id": _text(snapshot.get("issuer_id")),
        "scope": _text(snapshot.get("scope")), "as_of": observed.isoformat() if observed else None,
        "reference_date": reference_date, "publication_cutoff": publication_cutoff,
        "max_age_days": max_age_days, "holdings": holdings,
        "issuer_weights": {ticker: row["weight"] for ticker, row in holdings.items()},
    }
