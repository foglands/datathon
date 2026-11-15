"""Independently verify the optional sector and issuer exposure calculations."""

from collections.abc import Mapping
from datetime import date
from decimal import Context, Decimal, localcontext
from math import isclose

from .evidence import validate_issuer_snapshot
from .sector import REFERENCE_DATE, load_sector_catalog


_ZERO = Decimal(0)
_ONE = Decimal(1)
_TOLERANCE = 1e-10


def _is_fraction(value):
    return type(value) in (int, float) and 0 <= value <= 1


def _weights(weights):
    if not isinstance(weights, Mapping) or not all(
        isinstance(ticker, str) and ticker and _is_fraction(weight) for ticker, weight in weights.items()
    ):
        raise ValueError("Exposure weights must be finite long-only fractions.")
    fractions = {ticker: Decimal(str(weight)) for ticker, weight in weights.items()}
    if abs(sum(fractions.values()) - _ONE) > Decimal(str(_TOLERANCE)):
        raise ValueError("Exposure weights must total one.")
    return fractions


def _date(value):
    if not isinstance(value, str):
        raise ValueError("Exposure dates must be YYYY-MM-DD.")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Exposure dates must be YYYY-MM-DD.")
    return parsed


def _matches(expected, claimed):
    if isinstance(expected, dict):
        return (isinstance(claimed, Mapping) and expected.keys() == claimed.keys()
                and all(_matches(value, claimed[key]) for key, value in expected.items()))
    if isinstance(expected, float):
        return (type(claimed) in (int, float) and -1 - _TOLERANCE <= claimed <= 1 + _TOLERANCE
                and isclose(expected, claimed, rel_tol=0, abs_tol=_TOLERANCE))
    return type(expected) is type(claimed) and expected == claimed


def _ordered(bounds):
    return (isinstance(bounds, Mapping) and {"lower", "upper"} == bounds.keys()
            and type(bounds["lower"]) in (int, float) and type(bounds["upper"]) in (int, float)
            and -1 - _TOLERANCE <= bounds["lower"] <= bounds["upper"] <= 1 + _TOLERANCE)


def _sum_weighted(portfolio, values):
    return sum(portfolio.get(ticker, _ZERO) * value for ticker, value in values.items())


def _difference(before, after, intervals):
    # Select endpoints after applying the signed position change. An unchanged
    # position's uncertain exposure cancels because its coefficient is shared.
    terms_low, terms_high = [], []
    for ticker, (lower, upper) in intervals.items():
        delta = after.get(ticker, _ZERO) - before.get(ticker, _ZERO)
        ends = (delta * lower, delta * upper)
        terms_low.append(min(ends))
        terms_high.append(max(ends))
    return {"lower": float(sum(terms_low)), "upper": float(sum(terms_high))}


def _sector_result(before, after, catalog, reference, cutoff, max_age_days):
    taxonomy, records, digest = catalog
    tickers = sorted(ticker for ticker in before.keys() | after.keys() if before.get(ticker) or after.get(ticker))
    eligible, ignored = {}, {}
    for ticker in tickers:
        rows = sorted((row for row in records if row.ticker == ticker),
                      key=lambda row: (row.as_of, row.available_by), reverse=True)
        for row in rows:
            observed = _date(row.as_of)
            if (row.taxonomy, row.version) != taxonomy:
                reason = "taxonomy_mismatch"
            elif observed > reference or _date(row.available_by) > cutoff:
                reason = "outside_evidence_cutoff"
            elif (reference - observed).days > max_age_days:
                reason = "stale_evidence"
            else:
                eligible[ticker] = row
                break
            ignored.setdefault(ticker, reason)
        if ticker in eligible:
            ignored.pop(ticker, None)
        else:
            ignored.setdefault(ticker, "unavailable")

    known, non_equity, missing, evidence = {}, {}, {}, {}
    for ticker in tickers:
        row = eligible.get(ticker)
        known[ticker], non_equity[ticker] = {}, _ZERO
        if row is not None:
            scale = Decimal(str(row.equity_fraction)) if row.denominator == "equity_sleeve" else _ONE
            known[ticker] = {name: Decimal(str(weight)) * scale for name, weight in row.weights.items()}
            non_equity[ticker] = (_ONE - scale if row.denominator == "equity_sleeve"
                            else Decimal(str(row.non_equity_min)))
            evidence[ticker] = {
                "as_of": row.as_of, "available_by": row.available_by, "url": row.source_url,
                "locator": row.source_locator, "source_denominator": row.denominator,
                "sector_nav_lower": {name: float(value) for name, value in known[ticker].items()},
                "non_equity_nav_lower": float(non_equity[ticker]),
            }
        missing[ticker] = max(_ZERO, _ONE - sum(known[ticker].values()) - non_equity[ticker])

    sectors = {}
    for name in sorted({name for breakdown in known.values() for name in breakdown}):
        lows = {ticker: known[ticker].get(name, _ZERO) for ticker in tickers}
        highs = {ticker: min(_ONE, lows[ticker] + missing[ticker]) for ticker in tickers}
        sectors[name] = {
            "before": {"lower": float(_sum_weighted(before, lows)), "upper": float(_sum_weighted(before, highs))},
            "after": {"lower": float(_sum_weighted(after, lows)), "upper": float(_sum_weighted(after, highs))},
            "change": _difference(before, after, {ticker: (lows[ticker], highs[ticker]) for ticker in tickers}),
        }
    unmapped = {"before": float(_sum_weighted(before, missing)), "after": float(_sum_weighted(after, missing))}
    if not eligible:
        coverage = "unavailable"
    else:
        coverage = "partial" if any(weight > _TOLERANCE for weight in unmapped.values()) else "complete"
    verified = {
        "taxonomy": {"name": taxonomy[0], "level": "sector", "version": taxonomy[1]},
        "denominator": "portfolio_value", "status": coverage,
        "reference_date": reference.isoformat(), "publication_cutoff": cutoff.isoformat(),
        "sectors": sectors, "unmapped": unmapped,
        "known_non_equity_min": {"before": float(_sum_weighted(before, non_equity)),
                                 "after": float(_sum_weighted(after, non_equity))},
        "evidence": evidence, "ignored": ignored,
    }
    if digest is not None:
        verified["catalog_sha256"] = digest
    return verified


def review_sector_analysis(
    claimed, before, after, *, reference_date=REFERENCE_DATE, publication_cutoff=None,
    max_age_days=180, catalog=None,
):
    """Check all sector fields against an independent reconstruction from frozen records."""
    try:
        catalog = load_sector_catalog() if catalog is None else catalog
        reference = _date(reference_date)
        cutoff = reference if publication_cutoff is None else min(reference, _date(publication_cutoff))
        if type(max_age_days) is not int or max_age_days < 0:
            raise ValueError("Invalid sector evidence freshness limit.")
        with localcontext(Context(prec=36)):
            expected = _sector_result(_weights(before), _weights(after), catalog, reference, cutoff, max_age_days)
    except (OSError, ValueError):
        return {"status": "unavailable", "reason": "sector_evidence_unusable"}
    if not _matches(expected, claimed) or any(
        not _ordered(bound) for sector in claimed["sectors"].values() for bound in sector.values()
    ):
        return {"status": "invalid", "reason": "sector_calculation_mismatch"}
    if expected["status"] == "unavailable":
        return {"status": "unavailable", "reason": "no_qualifying_sector_evidence"}
    return {"status": "verified", "verified": expected}


def review_issuer_change(claimed, before, after, *, raw_snapshot, issuer_context):
    """Check exposure change using independently qualified issuer disclosure weights."""
    try:
        with localcontext(Context(prec=36)):
            before = _weights(before)
            after = _weights(after)
            coefficients = validate_issuer_snapshot(
                raw_snapshot, assets=sorted(before.keys() | after.keys()), **issuer_context
            )["issuer_weights"]
            intervals = {}
            for ticker, weight in coefficients.items():
                if weight is None:
                    intervals[ticker] = (_ZERO, _ONE)
                else:
                    fraction = Decimal(str(weight))
                    intervals[ticker] = (fraction, fraction)
            expected = _difference(before, after, intervals)
    except (OSError, TypeError, ValueError):
        return {"status": "unavailable", "reason": "issuer_evidence_unusable"}
    if not _ordered(claimed) or not _matches(expected, claimed):
        return {"status": "invalid", "reason": "issuer_change_mismatch"}
    return {"status": "verified", "verified": expected}
