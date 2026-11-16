"""Bounded, explicitly confirmed changes to one historical audit assumption.

Every scenario starts from the original confirmed terms. A challenge never
edits the original report, accumulates relaxed rules, or inherits permission
to search alternative funding. All new figures pass the normal independent
review and publication boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json

from .decision_release import publish_report, report_json, validate_report_inputs
from .decision_workflow import ConfirmedDecision, FundingAuthorization, RISK_METRICS, confirm_decision, run_decision


MAX_ROUNDS = 3
_FIELDS = {"risk_metric", "risk_cap", "holding_minimum", "purchase_quantity"}


def _encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


@dataclass(frozen=True)
class ChallengeProposal:
    original_id: str
    confirmed: ConfirmedDecision
    _change: str

    @property
    def change(self):
        """A detached description suitable for the confirmation UI."""
        return json.loads(self._change)


def _differences(before, after, path=()):
    if isinstance(before, dict) and isinstance(after, dict):
        if before.keys() != after.keys():
            return [path]
        return [item for key in before for item in _differences(before[key], after[key], (*path, key))]
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [path]
        return [item for index, (first, last) in enumerate(zip(before, after))
                for item in _differences(first, last, (*path, index))]
    return [] if before == after and type(before) is type(after) else [path]


def prepare_challenge(confirmed, *, field, value, rule_index=0):
    """Prepare exactly one user-selected change without executing a replay.

    Risk caps and holding floors are fractions. Purchase quantity retains its
    already confirmed unit and can only decrease. A metric change retains the
    existing cap; the confirmation description makes both meanings explicit.
    """
    if not isinstance(confirmed, ConfirmedDecision):
        raise ValueError("Confirm the original decision before preparing a hypothetical change.")
    if not isinstance(field, str) or field not in _FIELDS or type(rule_index) is not int or rule_index < 0:
        raise ValueError("Select one supported rule or purchase quantity to change.")
    original = confirmed.data
    draft = confirmed.data
    if field in {"risk_metric", "risk_cap"}:
        if rule_index >= len(draft["risk_limits"]):
            raise ValueError("Choose an existing risk limit.")
        key = "metric" if field == "risk_metric" else "cap"
        if field == "risk_metric" and value not in RISK_METRICS:
            raise ValueError("Choose a supported historical risk metric.")
        path = ("risk_limits", rule_index, key)
        parent = draft["risk_limits"][rule_index]
        unit = "metric" if key == "metric" else "days" if parent["metric"] == "recovery_days" else "fraction"
    elif field == "holding_minimum":
        if rule_index >= len(draft["constraints"]) or draft["constraints"][rule_index].get("min") is None:
            raise ValueError("Choose an existing minimum exposure rule.")
        path, parent, key, unit = ("constraints", rule_index, "min"), draft["constraints"][rule_index], "min", "fraction"
    else:
        if draft["intent"] != "audit":
            raise ValueError("A smaller purchase requires an original trade audit.")
        parent, key = draft["trade"], "quantity"
        if type(value) not in (int, float) or not 0 < value < parent[key]:
            raise ValueError("Confirm a positive purchase quantity smaller than the original quantity.")
        path, unit = ("trade", "quantity"), parent["unit"]
    before = parent[key]
    parent[key] = value
    draft["trace"] = confirmed.trace
    changed = confirm_decision(draft, scope=draft["scope"])
    if _differences(original, changed.data) != [path]:
        raise ValueError("A challenge must change exactly the selected field.")
    after = changed.data
    for part in path:
        after = after[part]
    change = {"field": field, "path": list(path), "before": before, "after": after, "unit": unit,
              "kind": "user_confirmed_hypothetical"}
    if field == "risk_metric":
        change["unchanged_cap"] = draft["risk_limits"][rule_index]["cap"]
    return ChallengeProposal(confirmed.id, changed, _encode(change))


def read_finding(report, question):
    """Read checked findings. This function cannot call the replay or a solver."""
    snapshot = json.loads(report_json(report))
    if snapshot["publication"]["status"] != "released":
        raise ValueError("An independently reviewed result is required before asking about it.")
    rules = snapshot.get("rules", [])
    if question == "why_fail":
        selected = [row for row in rules if row.get("status") == "fail" and
                    (snapshot.get("intent") != "audit" or row.get("candidate") != "Starting allocation")]
        return {"question": question, "kind": "existing_report", "verdict": snapshot.get("verdict"),
                "rules": selected, "message": "These checked rules failed." if selected else
                "This report contains no proven rule violation for the assessed proposal."}
    if question == "uncertain":
        return {"question": question, "kind": "existing_report", "gaps": snapshot.get("gaps", []),
                "rules": [row for row in rules if row.get("status") == "unknown"]}
    if question == "funding_difference":
        funding = snapshot.get("funding")
        return {"question": question, "kind": "existing_report", "funding": funding,
                "message": "Only the already authorized funding findings are shown." if funding else
                "No alternative funding search was authorized in this report. Confirm its scope before searching."}
    raise ValueError("Choose why_fail, funding_difference, or uncertain.")


def run_challenges(confirmed, original_report, market_data, proposals, *, acknowledged=False,
                   upload=None, funding_authorizations=None, code_version=None):
    """Run at most three independently reviewed, single-change scenarios.

    Each proposal is anchored to the original inputs, rather than to the prior
    scenario. A changed verdict ends the sequence. Optional funding permission
    must be freshly issued for the corresponding changed confirmation; old
    permission is rejected by the normal workflow. A missing permission means
    that no funding search runs.
    """
    if acknowledged is not True:
        raise ValueError("Review and confirm the proposed hypothetical changes before running them.")
    validate_report_inputs(original_report, confirmed)
    if not isinstance(proposals, (list, tuple)) or not 1 <= len(proposals) <= MAX_ROUNDS:
        raise ValueError("Confirm between one and three hypothetical checks.")
    permissions = {} if funding_authorizations is None else funding_authorizations
    if not isinstance(permissions, Mapping) or any(type(i) is not int or i not in range(len(proposals)) for i in permissions):
        raise ValueError("Funding permissions must identify the specific confirmed challenge.")
    for proposal in proposals:
        if not isinstance(proposal, ChallengeProposal) or proposal.original_id != confirmed.id:
            raise ValueError("Every challenge must start from these original confirmed inputs.")
        if (_differences(confirmed.data, proposal.confirmed.data) != [tuple(proposal.change["path"])]
                or proposal.confirmed.trace != confirmed.trace):
            raise ValueError("A challenge changed more than its confirmed assumption.")
        # Reconstruct the permitted operation so a forged proposal cannot hide
        # a different one-field change behind a misleading confirmation label.
        index = proposal.change["path"][1] if len(proposal.change["path"]) == 3 else 0
        expected = prepare_challenge(confirmed, field=proposal.change["field"],
                                     value=proposal.change["after"], rule_index=index)
        if expected != proposal:
            raise ValueError("The challenge no longer matches its reviewed change.")
    for index, permission in permissions.items():
        if not isinstance(permission, FundingAuthorization) or permission.decision_id != proposals[index].confirmed.id:
            raise ValueError("Funding authorization belongs to different confirmed inputs.")
    before = {"verdict": original_report.get("verdict"), "publication": original_report["publication"]["status"]}
    result = {"kind": "user_confirmed_hypothetical", "original_id": confirmed.id,
              "max_rounds": MAX_ROUNDS, "steps": [], "stopped_reason": "confirmed_checks_complete"}
    for index, proposal in enumerate(proposals):
        report = publish_report(run_decision(proposal.confirmed, market_data, upload=upload,
                                            funding=permissions.get(index), code_version=code_version))
        after = {"verdict": report.get("verdict"), "publication": report["publication"]["status"]}
        result["steps"].append({"round": index + 1, "change": proposal.change, "before": dict(before),
                                "after": after, "confirmed_id": proposal.confirmed.id,
                                "funding_authorized": index in permissions, "report": report})
        if after["publication"] != "released":
            result["stopped_reason"] = "independent_review_withheld"
            break
        if after["verdict"] != before["verdict"]:
            result["stopped_reason"] = "verdict_changed"
            break
    return result
