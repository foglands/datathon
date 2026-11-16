"""Generic calculations over dated issuer disclosures, never persona defaults."""

from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path


def qualified_bond_disclosures(symbols, today, *, records=None):
    raw = Path(__file__).with_name("bond_disclosures.json").read_bytes()
    catalog = json.loads(raw)
    records = catalog["records"] if records is None else records
    cutoff = date.fromisoformat(today)
    qualified, gaps = {}, {}
    for symbol in symbols:
        candidates = [record for record in records if record.get("symbol") == symbol]
        if len(candidates) != 1:
            gaps[symbol] = "No uniquely identified issuer disclosure is available."
            continue
        record = candidates[0]
        as_of, observed = date.fromisoformat(record["as_of"]), date.fromisoformat(record["observed_on"])
        if not as_of <= observed <= cutoff or (cutoff - as_of).days > 31:
            gaps[symbol] = "The issuer disclosure is stale or was not available by this research date."
            continue
        duration = record.get("effective_duration_years")
        ratings = record.get("rating_weights", {})
        if (type(duration) not in (float, int) or not isfinite(duration) or not 0 <= duration <= 100
                or not ratings or any(type(value) not in (float, int) or not isfinite(value) or not 0 <= value <= 1 for value in ratings.values())
                or sum(ratings.values()) > 1.001 or not record.get("source_url", "").startswith("https://")):
            gaps[symbol] = "The issuer disclosure did not pass value and coverage checks."
            continue
        qualified[symbol] = {**record, "catalog_sha256": sha256(raw).hexdigest()}
    return qualified, gaps


def duration_scenarios(record):
    scenarios = []
    for shock in (-.01, .01):
        change = -record["effective_duration_years"] * shock
        reference = -Fraction(str(record["effective_duration_years"])) * Fraction(str(shock))
        if not isclose(change, float(reference), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Duration sensitivity failed independent review.")
        scenarios.append({"yield_change": shock, "approximate_price_change": change})
    return {"symbol": record["symbol"], "duration_years": record["effective_duration_years"], "as_of": record["as_of"],
            "observed_on": record["observed_on"], "source_url": record["source_url"], "scenarios": scenarios,
            "assumption": "System illustration: parallel minus/plus 100 basis-point yield changes, with credit spread, FX and other conditions held fixed.",
            "limitation": "First-order price sensitivity; ignores convexity, changing duration, cash flows and credit-spread changes. Not a forecast or historical replay."}


def credit_breakdown(record):
    weights = record["rating_weights"]
    total = sum(Fraction(str(value)) for value in weights.values())
    unknown = max(Fraction(0), 1 - total)
    below = sum(Fraction(str(value)) for category, value in weights.items() if category in {"BB", "B", "CCC", "CC", "C", "D"})
    return {"symbol": record["symbol"], "as_of": record["as_of"], "observed_on": record["observed_on"],
            "source_url": record["source_url"], "rating_weights": weights, "sector_weights": record["sector_weights"],
            "reported_below_investment_grade": float(below), "unrated_weight": weights.get("not_rated", 0),
            "unclassified_or_rounding_weight": float(unknown), "rating_method": record["rating_method"],
            "limitation": record["limitation"]}
