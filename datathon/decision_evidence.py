"""Qualify dated evidence and independently check long-only exposure bounds."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
from math import fsum, isclose
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from .data import _csv_rows, issuer_evidence
from .evidence import DEFAULT_HOLDINGS_MAX_AGE_DAYS, load_issuer_catalog, validate_issuer_snapshot
from .sector import sector_analysis


AXES = ("issuer", "sector", "controversy", "asset_class")
NVIDIA = "CUSIP:67066G104"
SECTORS = frozenset({
    "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
    "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities",
})
ASSET_CLASSES = frozenset({"equity", "fixed_income", "commodity", "cryptocurrency", "cash"})
WRAPPERS = {"etf_equity": "equity_etf", "etf_bond": "bond_etf", "etf_commodity": "commodity_etf"}
_SUBJECT_ALIASES = {
    "issuer": {name: NVIDIA for name in ("nvda", "nvidia", "nvidia corp", "nvidia corp.", "nvidia corporation",
                                         "cusip:67066g104", "67066g104", "us67066g1040")},
    "sector": {**{name.casefold(): name for name in SECTORS}, "tech": "Information Technology",
               "technology": "Information Technology", "healthcare": "Health Care"},
    "asset_class": {
        "stocks": "equity", "stock": "equity", "equities": "equity", "bond": "fixed_income", "bonds": "fixed_income",
        "fixed income": "fixed_income", "fixed-income": "fixed_income", "crypto": "cryptocurrency",
        "commodities": "commodity", "digital assets": "cryptocurrency",
        **WRAPPERS, "bond etf": "bond_etf", "equity etf": "equity_etf", "commodity etf": "commodity_etf",
    },
    "controversy": {"nbim": "gpfg", "gpfg_exclusion_and_observation": "gpfg",
                    "gpfg exclusion and observation": "gpfg", "gpfg list": "gpfg",
                    "norges bank": "gpfg", "government pension fund global": "gpfg",
                    "gpfg exclusions": "gpfg_exclusions", "gpfg exclusion list": "gpfg_exclusions"},
}
_STARTER_URL = "https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/50-datasets"
_STARTER_AVAILABLE = "2026-11-14"
_STARTER_SHA256 = "f78de8ecb36d914a3448db63498cc9a04a34d805bccb79c481dda1650755467d"
_METADATA_SHA256 = "7ff17052c8235888c4984430830610ae0d81c0df71585afaacb87ba5fe531bdf"
_MAX_MANIFEST_BYTES = 16 * 1024
_EDGAR_PUBLIC_FILING = "Public SEC filing; registrant material"
_SEC_HOLDINGS = {
    "SPY": ("0001410368-26-089410", "7.517011844111"),
    "QQQ": ("0001067839-26-000030", "7.596756593966"),
}
_NVDA_10Q = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/nvda-20260726.htm"
_SP_ILLUSTRATION = (
    "https://www.spglobal.com/spdji/en/documents/education/"
    "education-an-overview-of-gics-and-sp-500-sector-industry-indices.pdf"
)
_GPFG_URL = "https://www.nbim.no/en/responsible-investment/exclusion-of-companies/"
_GPFG_DATE = "2026-08-11"
_GPFG_REVIEWED_ON = "2026-11-15"
_GPFG_LICENSE = "NBIM copyrighted source; https://www.nbim.no/en/disclaimer/"
# Named issuer checks against the complete dated NBIM table, plus the two matching list entries.
# ETF names and unreviewed issuers do not establish a state for their holdings.
_GPFG_CHECKED = {
    "AAPL": ("Apple Inc.", "not_listed"),
    "AMZN": ("Amazon.com, Inc.", "not_listed"),
    "CNQ.TO": ("Canadian Natural Resources Limited", "excluded"),
    "ENB.TO": ("Enbridge Inc.", "not_listed"),
    "GOOGL": ("Alphabet Inc. (including former issuer name Google)", "not_listed"),
    "MSFT": ("Microsoft Corporation", "not_listed"),
    "NVDA": ("NVIDIA Corporation", "not_listed"),
    "TD.TO": ("The Toronto-Dominion Bank", "under_observation"),
    "TSLA": ("Tesla, Inc. (including former name Tesla Motors)", "not_listed"),
    "XOM": ("Exxon Mobil Corporation (including ExxonMobil)", "not_listed"),
}
_FIELDS = {"ticker", "axis", "subject", "lower", "upper", "source_url", "source_id", "as_of", "published_on",
           "kind", "license"}
_CLASSIFICATION_TEXT = {"state", "policy", "name", "level", "version", "denominator", "locator", "limitation",
                        "asset_class", "issuer", "decision_on", "source_document_sha256", "catalog_sha256", "retrieved_on"}
_EPSILON = 1e-12
_INSTRUCTION = re.compile(
    r"\b(?:ignore|bypass|override|disregard)\b.{0,80}\b(?:instructions?|rules?|limits?|floor|policy|checks?)\b"
    r"|\b(?:system|assistant|developer)\s*(?:message|prompt|instruction|:)"
    r"|\bapprove\b.{0,40}\b(?:trade|transaction|request|decision)\b", re.I | re.S,
)


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _contains_instruction(value):
    if isinstance(value, str):
        return bool(_INSTRUCTION.search(value))
    if isinstance(value, Mapping):
        return any(_contains_instruction(item) for item in value.values())
    return False


def normalize_subject(axis, subject):
    """Normalize a supported axis label without treating a fund label as a holding."""
    if axis not in AXES or not isinstance(subject, str) or not 0 < len(subject.strip()) <= 120:
        raise ValueError("Exposure needs a supported axis and a named subject.")
    label = " ".join(subject.split())
    fallback = label.upper() if axis == "issuer" else label.casefold() if axis != "sector" else label.title()
    return _SUBJECT_ALIASES[axis].get(label.casefold(), fallback)


def _calendar_date(value):
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        if parsed.isoformat() == value:
            return parsed
    return None


def _fraction(value):
    return type(value) in (float, int) and 0 <= value <= 1


def _public_url(value):
    if not isinstance(value, str) or not 0 < len(value) <= 1000 or any(char.isspace() for char in value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname) and url.username is None
                and ("." in url.hostname) and url.port in (None, 443))
    except ValueError:
        return False


def _record(ticker, axis, subject, lower, upper, *, source_url=None, source_id=None,
            as_of=None, published_on=None, kind="unknown", license=None, classification=None):
    row = dict(ticker=ticker, axis=axis, subject=subject, lower=lower, upper=upper, source_url=source_url,
               source_id=source_id, as_of=as_of, published_on=published_on, kind=kind, license=license)
    if classification:
        row["classification"] = dict(classification)
    return row


def _validated_row(row):
    if not isinstance(row, Mapping) or row.keys() - (_FIELDS | {"classification"}) or _FIELDS - row.keys():
        raise ValueError("invalid_record_fields")
    if _contains_instruction(row):
        raise ValueError("evidence_instruction_ignored")
    normalized = dict(row)
    normalized["subject"] = normalize_subject(row["axis"], row["subject"])
    if (not isinstance(row["ticker"], str) or not 0 < len(row["ticker"]) <= 24
            or row["kind"] not in {"disclosed", "mandate_bounded", "direct", "unknown"}
            or not all(_fraction(row[key]) for key in ("lower", "upper")) or row["lower"] > row["upper"]):
        raise ValueError("invalid_evidence_bounds")
    if row["kind"] == "unknown":
        return _unknown(row["ticker"], row["axis"], normalized["subject"])
    if (not _public_url(row["source_url"]) or not all(isinstance(row[key], str) and 0 < len(row[key].strip()) <= 240
                                                     for key in ("source_id", "license"))):
        raise ValueError("invalid_source_provenance")
    observed, available = (_calendar_date(row[key]) for key in ("as_of", "published_on"))
    if observed is None or available is None or available < observed:
        raise ValueError("invalid_observation_publication_dates")
    info = row.get("classification", {})
    if (not isinstance(info, Mapping) or info.keys() - (_CLASSIFICATION_TEXT | {"complete_list"})
            or not all(isinstance(value, str) and 0 < len(value.strip()) <= 400
                       for key, value in info.items() if key in _CLASSIFICATION_TEXT)
            or ("complete_list" in info and type(info["complete_list"]) is not bool)):
        raise ValueError("invalid_classification")
    if row["kind"] == "direct" and (row["lower"], row["upper"]) not in {(0, 0), (1, 1)}:
        raise ValueError("invalid_direct_classification")
    if "retrieved_on" in info and _calendar_date(info["retrieved_on"]) is None:
        raise ValueError("invalid_retrieval_date")
    if row["axis"] in {"issuer", "sector", "asset_class"}:
        required_denominator = "position" if row["kind"] == "direct" else "nav"
        if info.get("denominator") != required_denominator:
            raise ValueError("unqualified_exposure_denominator")
    if info:
        normalized["classification"] = dict(info)
    return normalized


def _unknown(ticker, axis, subject):
    classification = {"state": "unknown", "policy": subject} if axis == "controversy" else None
    return _record(ticker, axis, subject, 0.0, 1.0, classification=classification)


def _manifest_bytes(path):
    if path.is_dir():
        candidates = (path, path / "alphaforge_starter", path / "Datathon2026" / "alphaforge_starter")
        matches = [directory / "assets_universe.csv" for directory in candidates
                   if (directory / "assets_universe.csv").is_file()]
        if len(matches) != 1:
            return None
        with matches[0].open("rb") as stream:
            return stream.read(_MAX_MANIFEST_BYTES + 1)
    with ZipFile(path) as archive:
        matches = [entry for entry in archive.infolist()
                   if PurePosixPath(entry.filename).parts[-2:] == ("alphaforge_starter", "assets_universe.csv")]
        if len(matches) != 1 or matches[0].file_size > _MAX_MANIFEST_BYTES:
            return None
        return archive.read(matches[0])


def _starter_assets(data):
    if not getattr(data, "official_starter", False) or not data.source_path:
        return {}, None
    metadata = dict(data.source_csvs).get("sources_metadata.csv")
    if not isinstance(metadata, str) or sha256(metadata.encode()).hexdigest() != _METADATA_SHA256:
        return {}, None
    try:
        payload = _manifest_bytes(Path(data.source_path))
    except (OSError, BadZipFile):
        return {}, None
    if payload is None or sha256(payload).hexdigest() != _STARTER_SHA256:
        return {}, None
    assets = csv.DictReader(io.StringIO(payload.decode("utf-8")))
    source = next(row for row in _csv_rows(metadata, {"file", "retrieved_on", "terms_of_use"})
                  if row["file"] == "assets_universe.csv")
    return {row["ticker"]: row for row in assets}, source


def _starter_records(assets, source, tickers):
    for ticker in sorted(assets.keys() & tickers):
        asset = assets[ticker]
        category = asset["asset_class"]
        common = {"source_url": _STARTER_URL, "source_id": f"starter:assets_universe:{asset['asset_id']}:{_STARTER_SHA256}",
                  "as_of": source["retrieved_on"], "published_on": _STARTER_AVAILABLE, "kind": "direct",
                  "license": source["terms_of_use"]}
        classification = {"denominator": "position", "name": "Organizer starter instrument classification",
                          "asset_class": category, "locator": f"assets_universe.csv, {asset['asset_id']}",
                          "limitation": "Organizer-assigned instrument bucket; fund holdings are assessed separately."}
        for subject in WRAPPERS.values():
            value = float(WRAPPERS.get(category) == subject)
            yield _record(ticker, "asset_class", subject, value, value, **common, classification=classification)
        if category in {"equity", "crypto"}:
            economic_class = "equity" if category == "equity" else "cryptocurrency"
            for subject in sorted(ASSET_CLASSES):
                value = float(economic_class == subject)
                yield _record(ticker, "asset_class", subject, value, value, **common, classification=classification)
        if category == "equity":
            issuer = {**classification, "name": "Organizer starter issuer identity", "issuer": asset["name"],
                      "limitation": "Direct equity issuer at the position level."}
            yield _record(ticker, "issuer", ticker, 1.0, 1.0, **common, classification=issuer)
            yield _record(ticker, "issuer", "*", 0.0, 0.0, **common, classification=issuer)
            # The manifest's organizer-assigned sector labels are a defined simulation taxonomy.
            if asset["sector"] in SECTORS and ticker != "NVDA":
                sector = {**classification, "name": "Organizer starter sectors", "level": "sector",
                          "version": "2026", "limitation": "Simplified organizer-assigned labels using GICS names."}
                for subject in sorted(SECTORS):
                    value = float(asset["sector"] == subject)
                    yield _record(ticker, "sector", subject, value, value, **common, classification=sector)


def _issuer_records(tickers, knowledge_date, gaps):
    raw = issuer_evidence()
    if "NVDA" in tickers:
        identity = {"denominator": "position", "issuer": "NVIDIA Corporation", "locator": "Form 10-Q cover, NVDA common stock"}
        for subject, value in ((NVIDIA, 1.0), ("*", 0.0)):
            yield _record("NVDA", "issuer", subject, value, value, source_url=_NVDA_10Q,
                          source_id="sec:10-q:0001045810-26-000075", as_of="2026-07-26", published_on="2026-08-26",
                          kind="direct", license=_EDGAR_PUBLIC_FILING, classification=identity)
    qualified = validate_issuer_snapshot(raw, reference_date=knowledge_date, publication_cutoff=knowledge_date,
                                         assets=sorted(tickers))
    for ticker, row in qualified["holdings"].items():
        if ticker not in tickers or ticker == "NVDA":
            continue
        if row["status"] == "disclosed" and ticker in _SEC_HOLDINGS:
            accession, reported_pct = _SEC_HOLDINGS[ticker]
            weight = row["weight"]
            if Fraction(reported_pct) / 100 != Fraction(str(weight)):
                gaps.append(_gap(ticker, "issuer", NVIDIA, "filing_nav_conversion_mismatch"))
                continue
            link = row["url"].replace("/primary_doc.html", "/xslFormNPORT-P_X01/primary_doc.xml")
            filing = {"source_url": link, "source_id": f"sec:nport:{accession}", "as_of": row["as_of"],
                      "published_on": row["published_on"], "kind": "disclosed", "license": _EDGAR_PUBLIC_FILING}
            classification = {"denominator": "nav", "issuer": "NVIDIA Corporation",
                              "locator": "Form N-PORT Items C.1–C.4, CUSIP 67066G104",
                              "limitation": "Reported common equity holding as a fraction of fund NAV."}
            yield _record(ticker, "issuer", NVIDIA, weight, weight, **filing, classification=classification)
            yield _record(ticker, "asset_class", "equity", weight, 1.0, **filing,
                          classification={**classification, "limitation": "One disclosed common-equity holding sets a minimum."})
        elif ticker in raw["holdings"]:
            gaps.append(_gap(ticker, "issuer", NVIDIA, row["reason"]))
    try:
        catalog = load_issuer_catalog()
    except ValueError:
        gaps.append(_gap(None, "issuer", NVIDIA, "reviewed_catalog_unavailable"))
        return
    for reviewed in catalog.values():
        if reviewed.ticker in tickers:
            yield _record(reviewed.ticker, "issuer", NVIDIA, reviewed.weight, reviewed.weight,
                          source_url=reviewed.url, source_id=f"reviewed:issuer:{reviewed.id}", as_of=reviewed.as_of,
                          published_on=reviewed.published_on, kind="disclosed", license="Public cited disclosure",
                          classification={"denominator": "nav", "locator": reviewed.source_locator,
                                          "source_document_sha256": reviewed.source_document_sha256,
                                          "catalog_sha256": reviewed.catalog_sha256})


def _sector_records(tickers, knowledge_date, gaps):
    if not tickers:
        return
    portfolio = {ticker: 1 / len(tickers) for ticker in sorted(tickers)}
    try:
        analysis = sector_analysis(portfolio, portfolio, reference_date=knowledge_date)
    except ValueError:
        gaps.append(_gap(None, "sector", None, "reviewed_catalog_unavailable"))
        return
    taxonomy = analysis["taxonomy"]
    for ticker, row in analysis["evidence"].items():
        denominator = row["source_denominator"]
        source_id = analysis.get("catalog_sha256", "reference")
        license = ("S&P DJI copyrighted source" if ticker == "NVDA" and source_id == "reference"
                   else "Public cited disclosure; publisher terms apply")
        common = {"source_url": row["url"], "source_id": f"sector:{source_id}:{ticker}:{row['as_of']}",
                  "as_of": row["as_of"], "published_on": row["available_by"], "license": license}
        classification = {"name": taxonomy["name"], "level": taxonomy["level"], "version": taxonomy["version"],
                          "locator": row["locator"], "denominator": "position" if denominator == "position" else "nav"}
        known = row["sector_nav_lower"]
        non_equity = row["non_equity_nav_lower"]
        derivation = row.get("non_equity_derivation", {})
        if derivation.get("method") == "fair_value_nav_display_envelope":
            fair_value, nav = derivation["reported_fair_value"], derivation["reported_net_assets"]
            exact_min = Fraction(max(0, fair_value - 1), nav + 1)
            if not isclose(non_equity, float(exact_min), abs_tol=_EPSILON, rel_tol=0):
                gaps.append(_gap(ticker, "asset_class", None, "fund_nav_conversion_mismatch"))
                continue
            if ticker == "ZST.TO" and source_id == "reference":
                maximum = float(min(1, Fraction(fair_value + 1, nav - 1)))
                bmo = {**classification, "name": "BMO interim financial statements",
                       "limitation": "Reported debt fair value divided by NAV with a display rounding envelope."}
                yield _record(ticker, "asset_class", "fixed_income", non_equity, maximum, **common,
                              kind="disclosed", classification=bmo)
                for subject in sorted(ASSET_CLASSES - {"fixed_income"}):
                    yield _record(ticker, "asset_class", subject, 0.0, 1 - non_equity, **common, kind="disclosed",
                                  classification={**bmo, "limitation": "Upper bound uses the NAV residual outside reported debt."})
        unknown = max(0.0, 1 - fsum([*known.values(), non_equity]))
        for subject in sorted(SECTORS | known.keys()):
            lower = known.get(subject, 0.0)
            upper = min(1.0, lower + unknown)
            if (lower, upper) != (0.0, 1.0):
                yield _record(ticker, "sector", subject, lower, upper, **common, classification=classification,
                              kind="direct" if denominator == "position" else "disclosed")
    for ticker, reason in analysis["ignored"].items():
        if reason != "unavailable":
            gaps.append(_gap(ticker, "sector", None, reason))


def _gpfg_records(tickers):
    ids = {"CNQ.TO": "2020-05-13", "TD.TO": "2025-06-11"}
    for ticker in sorted(tickers & _GPFG_CHECKED.keys()):
        issuer, state = _GPFG_CHECKED[ticker]
        classification = {"state": state, "issuer": issuer, "complete_list": True,
                          "locator": "Alphabetical company list for observation and exclusion, updated August 11, 2026",
                          "retrieved_on": _GPFG_REVIEWED_ON,
                          "limitation": "Direct issuer lookup in the dated GPFG list; not an ESG rating or a complete controversy screen."}
        if ticker in ids:
            classification["decision_on"] = ids[ticker]
        for policy in ("gpfg", "gpfg_exclusions"):
            value = float(state == "excluded" or (policy == "gpfg" and state == "under_observation"))
            yield _record(ticker, "controversy", policy, value, value, source_url=_GPFG_URL,
                          source_id=f"nbim:gpfg:{_GPFG_DATE}", as_of=_GPFG_DATE, published_on=_GPFG_DATE,
                          kind="direct", license=_GPFG_LICENSE, classification={**classification, "policy": policy})


def _gap(ticker, axis, subject, reason):
    return {"ticker": ticker, "axis": axis, "subject": subject, "reason": reason}


def _eligibility(row, cutoff):
    if row["kind"] == "unknown":
        return "unqualified_evidence"
    observed, published = (_calendar_date(row[key]) for key in ("as_of", "published_on"))
    if published > cutoff:
        return "outside_evidence_cutoff"
    # A direct issuer identity or instrument taxonomy is not a fund holdings snapshot.
    # Holdings, mandates and screening lists still have a bounded freshness lifetime.
    if (row["kind"] != "direct" or row["axis"] == "controversy") and (
            cutoff - observed).days > DEFAULT_HOLDINGS_MAX_AGE_DAYS:
        return "stale_evidence"
    return None


def _qualify_controv(row, built_in):
    info = row.get("classification", {})
    state = info.get("state")
    if state not in {"excluded", "under_observation", "not_listed", "confirmed", "reported", "unknown"}:
        return "unqualified_screen_state"
    if info.get("policy") != row["subject"]:
        return "unqualified_screen_policy"
    if state == "excluded" and (row["lower"], row["upper"]) != (1, 1) and row["kind"] == "direct":
        return "contradictory_screen_state"
    if state == "under_observation" and row["subject"] == "gpfg" and (
            row["lower"], row["upper"]) != (1, 1) and row["kind"] == "direct":
        return "contradictory_screen_state"
    if state == "not_listed" or (state == "under_observation" and row["subject"] == "gpfg_exclusions"):
        if not (built_in and row["subject"] in {"gpfg", "gpfg_exclusions"} and info.get("complete_list") is True
                and row["source_url"] == _GPFG_URL and row["as_of"] == _GPFG_DATE
                and (row["lower"], row["upper"]) == (0, 0)):
            return "unqualified_complete_screen_list"
    elif state == "unknown" or not row["lower"]:
        return "unqualified_screen_exposure"
    return None


def evidence_context(data, tickers, *, knowledge_date, extra_evidence=()):
    """Build one dated context from verified sources and operator-reviewed extra records."""
    cutoff = _calendar_date(knowledge_date)
    if cutoff is None:
        raise ValueError("Knowledge date must use YYYY-MM-DD.")
    tickers = set(tickers)
    if not all(isinstance(ticker, str) and 0 < len(ticker) <= 24 for ticker in tickers):
        raise ValueError("Evidence tickers must be nonempty position identifiers.")
    gaps, trace = [], []
    assets, source = _starter_assets(data)
    reviewed = defaultdict(list)
    built_ins = [*_starter_records(assets, source, tickers), *_issuer_records(tickers, knowledge_date, gaps),
                 *_sector_records(tickers, knowledge_date, gaps), *_gpfg_records(tickers)]
    if "NVDA" in tickers:
        # Use the end of the publication month as the earliest verified availability date.
        as_of = "2026-04-30"
        for subject in sorted(SECTORS):
            value = float(subject == "Information Technology")
            built_ins.append(_record("NVDA", "sector", subject, value, value, source_url=_SP_ILLUSTRATION,
                                     source_id="sp-dji:gics-illustration:2026-04", as_of=as_of, published_on=as_of,
                                     kind="direct", license="S&P DJI copyrighted source",
                                     classification={"name": "GICS", "version": "2026", "level": "sector",
                                                     "denominator": "position", "locator": "Exhibit 2, NVIDIA example",
                                                     "limitation": "Month-dated publication qualified at month end."}))
    for built_in, candidates in ((True, built_ins), (False, extra_evidence)):
        for candidate in candidates:
            try:
                row = _validated_row(candidate)
            except (TypeError, ValueError) as exc:
                reason = "evidence_instruction_ignored" if str(exc) == "evidence_instruction_ignored" else "invalid_evidence_record"
                gaps.append(_gap(None, None, None, reason))
                continue
            key = row["ticker"], row["axis"], row["subject"]
            if key[0] not in tickers:
                continue
            reason = _eligibility(row, cutoff)
            if key[1] == "controversy" and reason is None:
                reason = _qualify_controv(row, built_in)
            if not built_in and key[2] == "*":
                reason = "unqualified_wildcard"
            if reason:
                gaps.append(_gap(*key, reason))
            else:
                reviewed[key].append(row)

    records = {ticker: {axis: {} for axis in AXES} for ticker in sorted(tickers)}
    for key, candidates in sorted(reviewed.items()):
        ticker, axis, subject = key
        latest = max(row["as_of"] for row in candidates)
        current = [row for row in candidates if row["as_of"] == latest]
        if len({(row["lower"], row["upper"], row.get("classification", {}).get("state")) for row in current}) > 1:
            records[ticker][axis][subject] = _unknown(*key)
            gaps.append(_gap(*key, "conflicting_dated_evidence"))
            continue
        selected = max(current, key=lambda row: (row["published_on"], row["source_id"]))
        records[ticker][axis][subject] = selected
        trace.append({"ticker": ticker, "axis": axis, "subject": subject, "source_id": selected["source_id"],
                      "as_of": latest, "published_on": selected["published_on"], "kind": selected["kind"]})
    for ticker, axes in records.items():
        for axis, subjects in axes.items():
            if not subjects:
                gaps.append(_gap(ticker, axis, None, "no_qualified_evidence"))
    aliases = {asset["name"].upper(): normalize_subject("issuer", ticker) for ticker, asset in assets.items()
               if asset["asset_class"] == "equity" and cutoff >= date.fromisoformat(_STARTER_AVAILABLE)}
    # A wildcard zero is valid only against another resolved issuer identity. An
    # unfamiliar name may be an alias for this same issuer, so it must stay unknown.
    known_issuers = {NVIDIA, *aliases.values()}
    context = {"knowledge_date": knowledge_date, "records": records, "trace": trace, "gaps": gaps,
               "issuer_aliases": aliases, "known_issuers": sorted(known_issuers)}
    # This is an integrity check after qualification, not proof that a source is true.
    return {**context, "evidence_digest": _digest(context)}


def exposure_bounds(weights, context, axis, subject):
    """Return absolute bounds and weighted uncertainty for one exposure subject."""
    if not isinstance(context, Mapping) or context.get("evidence_digest") != _digest(
            {key: value for key, value in context.items() if key != "evidence_digest"}):
        raise ValueError("Qualified evidence changed before exposure verification.")
    subject = normalize_subject(axis, subject)
    if axis == "issuer":
        subject = context.get("issuer_aliases", {}).get(subject, subject)
    if (not isinstance(weights, Mapping) or not all(isinstance(ticker, str) and ticker for ticker in weights)
            or not all(_fraction(weight) for weight in weights.values())
            or not isclose(fsum(weights.values()), 1.0, rel_tol=0, abs_tol=_EPSILON)):
        raise ValueError("Exposure needs long-only portfolio weights totaling 100%.")
    records = context["records"]
    coefficients = {}
    for ticker, weight in sorted(weights.items()):
        if not weight:
            continue
        known = records.get(ticker, {}).get(axis, {})
        row = known.get(subject)
        if row is None and axis == "issuer" and subject in context.get("known_issuers", ()):
            row = known.get("*")
        coefficients[ticker] = ({**deepcopy(row), "subject": subject} if row else _unknown(ticker, axis, subject))
    bounds = {key: min(1.0, fsum(weights[ticker] * row[key] for ticker, row in coefficients.items()))
              for key in ("lower", "upper")}
    # Independent exact rational arithmetic over the input decimals checks both products and their sum.
    for key, bound in bounds.items():
        exact = sum(Fraction(str(weights[ticker])) * Fraction(str(row[key])) for ticker, row in coefficients.items())
        if not isclose(bound, float(exact), rel_tol=0, abs_tol=_EPSILON):
            raise ArithmeticError("Exposure bounds failed independent recomputation.")
    unknown_weight = max(0.0, min(1.0, bounds["upper"] - bounds["lower"]))
    classified = {
        "disclosed_weight": fsum(weights[ticker] for ticker, row in coefficients.items()
                                 if row["kind"] in {"direct", "disclosed"}),
        "mandate_bounded_weight": fsum(weights[ticker] for ticker, row in coefficients.items()
                                       if row["kind"] == "mandate_bounded"),
        "unassessed_weight": fsum(weights[ticker] for ticker, row in coefficients.items() if row["kind"] == "unknown"),
    }
    return {**bounds, "coverage": 1 - unknown_weight, "unknown_weight": unknown_weight,
            **classified, "coverage_basis": "One minus the weighted exposure interval width; not complete holdings disclosure.",
            "verified": True, "coefficients": coefficients}
