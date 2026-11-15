"""Bind an issued review to its inputs and keep independent section results."""

from __future__ import annotations

from hashlib import sha256
import json
from uuid import uuid4


AUDIT_SNAPSHOT_KEY = "_audit_snapshot"
REVIEW_ID_KEY = "_review_id"
CHECK_SNAPSHOT_KEY = "_check_snapshot"
OPTIONAL_SECTIONS = ("sector_analysis", "exposure_change")

POLICY_VERSION = "portfolio-audit-v1"
FORMULA_VERSIONS = {
    "portfolio_replay": "buy-and-hold-v1",
    "historical_risk_and_contributions": "terminal-loss-and-drawdown-v1",
    "exposure": "shared-coefficient-bounds-v1",
    "funding": "two-source-frontier-v1",
}
_SNAPSHOT_VERSION = 1
AUDIT_FIELDS = frozenset({
    REVIEW_ID_KEY, "case", "mode", "status", "decision_reason", "search_alternatives", "assessment_scope",
    "confirmed_scope", "policy", "unassessed_requirements", "requirements", "evidence", "audit",
    "needs_smaller_authorization",
})
_CHECK_FIELDS = frozenset({
    "status", "reason", "verified", "statement", "selection_mode", "option", "confirmed_threshold",
    "changed_fields", "action",
})


class _IssuedSnapshot(str):
    """Immutable, JSON-serializable internal record. A decoded string confers no authority."""

    __slots__ = ()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _selected(row, fields):
    return {key: row[key] for key in fields if key in row}


def _section_input(report, name):
    return _selected(report, (name,))


def seal_audit_report(report, *, input_versions, verified_sections):
    """Issue a snapshot after Review and requirement-status assembly have completed."""
    report[REVIEW_ID_KEY] = uuid4().hex
    versions = {
        "formula_versions": FORMULA_VERSIONS,
        "policy_version": POLICY_VERSION,
        "snapshot_version": _SNAPSHOT_VERSION,
        "inputs": input_versions,
    }
    sections = {}
    for name in OPTIONAL_SECTIONS:
        if name in verified_sections or name in report:
            checked = verified_sections.get(name, {"status": "unavailable"})
            sections[name] = {"claim": fingerprint(_section_input(report, name)),
                              "check": checked}
    report[AUDIT_SNAPSHOT_KEY] = _IssuedSnapshot(_canonical({
        "kind": "audit",
        "main": fingerprint({"versions": versions, "result": _selected(report, AUDIT_FIELDS)}),
        "review_id": report[REVIEW_ID_KEY],
        "versions": versions,
        "sections": sections,
    }))


def _read(report, key, kind):
    issued = report.get(key)
    if type(issued) is _IssuedSnapshot:
        decoded = json.loads(issued)
        if decoded["kind"] == kind:
            return decoded
    return None


def review_versions_match(versions):
    return (
        versions.get("snapshot_version") == _SNAPSHOT_VERSION
        and versions.get("policy_version") == POLICY_VERSION
        and versions.get("formula_versions") == FORMULA_VERSIONS
    )


def audit_snapshot(report):
    """Return the issued snapshot only if its audited context and main result still agree."""
    snapshot = _read(report, AUDIT_SNAPSHOT_KEY, "audit")
    if (snapshot is None or snapshot["review_id"] != report.get(REVIEW_ID_KEY)
            or not review_versions_match(snapshot["versions"])):
        return None
    try:
        current = fingerprint({"versions": snapshot["versions"], "result": _selected(report, AUDIT_FIELDS)})
    except (TypeError, ValueError):
        return None
    return snapshot if current == snapshot["main"] else None


def audit_snapshot_matches(report):
    return audit_snapshot(report) is not None


def reviewed_section(report, snapshot, name):
    section = snapshot["sections"].get(name) if snapshot is not None else None
    if section is None:
        return {"status": "invalid" if name in report else "not_requested"}
    try:
        claim_matches = section["claim"] == fingerprint(_section_input(report, name))
    except (TypeError, ValueError):
        claim_matches = False
    if not claim_matches:
        return {"status": "invalid", "reason": "reviewed_section_changed"}
    return section["check"]


def _challenge_bound_fields(check):
    return {
        **_selected(check, _CHECK_FIELDS),
        "baseline_review_id": (check.get("baseline") or {}).get(REVIEW_ID_KEY),
        "replay_review_id": (check.get("replay") or {}).get(REVIEW_ID_KEY),
    }


def seal_counterfactual_check(check):
    """Bind checked selectors, disclosure actions and prose to the two review identities."""
    check[CHECK_SNAPSHOT_KEY] = _IssuedSnapshot(_canonical({
        "kind": "challenge", "result": fingerprint(_challenge_bound_fields(check)),
    }))
    return check


def counterfactual_snapshot_matches(check):
    snapshot = _read(check, CHECK_SNAPSHOT_KEY, "challenge")
    try:
        return snapshot is not None and snapshot["result"] == fingerprint(_challenge_bound_fields(check))
    except (AttributeError, TypeError, ValueError):
        return False
