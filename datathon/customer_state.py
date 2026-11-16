"""Versioned user statements, with explicit correction/retraction provenance."""

from copy import deepcopy
from decimal import Decimal
import re


def semantic_key(kind, excerpt):
    text = re.sub(r"\s+", " ", excerpt.casefold()).strip(" .")
    if kind in {"investment_amount", "base_currency"}:
        currencies = sorted(set(re.findall(r"\b(?:cad|usd)\b", text)))
        amounts = [str(Decimal(x.replace(",", "")).normalize()) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
        return kind, tuple(currencies), tuple(amounts) if kind == "investment_amount" else ()
    if kind == "horizon":
        match = re.fullmatch(r"(?:for |in )?(\d+)\s*(months?|years?)[.!]?", text)
        if match:
            return kind, int(match[1]) * (12 if match[2].startswith("year") else 1)
    return kind, text


def apply_turn(previous, parsed, message):
    state = deepcopy(previous) if previous else {"version": 0, "statements": [], "events": [], "assets": [], "budget": None}
    state.setdefault("messages", []).append({"turn": state["version"] + 1, "text": message})
    state["version"] += 1
    turn = state["version"]
    active = {row["id"]: row for row in state["statements"] if row["active"]}
    incoming = deepcopy(parsed["conditions"])
    if parsed.get("budget") and parsed["budget"]["excerpt"] in message and not any(x["kind"] == "investment_amount" for x in incoming):
        incoming.append({"kind": "investment_amount", "excerpt": parsed["budget"]["excerpt"]})
    for condition in incoming:
        operation = condition.get("operation", "add")
        targets = condition.get("targets", [])
        # On model outage, local recovery can only add exact facts; no deletions.
        if parsed["origin"] != "bedrock" and operation != "add":
            continue
        if any(key not in active or active[key]["kind"] != condition["kind"] for key in targets):
            raise ValueError("State update targets must be active statements in the same field.")
        if operation in {"replace", "retract", "repeat"} and not targets:
            raise ValueError("Corrections, retractions and repeats must identify prior statements.")
        if operation not in {"add", "replace", "retract", "repeat", "conflict"}:
            raise ValueError("Unknown conversation update operation.")
        if condition["excerpt"] not in message:
            raise ValueError("A state update must retain the user's exact words.")
        if operation in {"replace", "retract"}:
            for key in targets:
                active[key]["active"] = False
                active[key]["superseded_in_turn"] = turn
        equivalent = [row["id"] for row in active.values() if row["active"] and
                      semantic_key(row["kind"], row["excerpt"]) == semantic_key(condition["kind"], condition["excerpt"])]
        if operation not in {"retract", "repeat"} and not equivalent:
            row = {**deepcopy(condition), "id": f"statement.{turn}.{len(state['statements'])}", "active": True,
                   "turn": turn, "source": "user", "interpretation": parsed["origin"]}
            state["statements"].append(row)
            active[row["id"]] = row
        state["events"].append({"turn": turn, "operation": "repeat" if equivalent else operation,
            "field": condition["kind"], "targets": targets or equivalent, "excerpt": condition["excerpt"]})
    for asset in parsed.get("assets", []):
        operation, targets = asset.get("operation", "add"), asset.get("targets", [])
        if parsed["origin"] != "bedrock" and operation != "add":
            continue
        known = {row["query"] for row in state["assets"]}
        if operation not in {"add", "replace", "retract", "repeat"} or any(key not in known for key in targets):
            raise ValueError("Asset updates must use a supported operation and known prior queries.")
        if operation in {"replace", "retract", "repeat"} and not targets:
            raise ValueError("Asset corrections and retractions must name the prior asset query.")
        if operation in {"replace", "retract"}:
            state["assets"] = [row for row in state["assets"] if row["query"] not in targets]
        equivalent = any(row["query"].casefold() == asset["query"].casefold() and row["role"] == asset["role"] for row in state["assets"])
        if operation not in {"retract", "repeat"} and not equivalent:
            state["assets"].append({key: value for key, value in asset.items() if key not in {"operation", "targets"}})
        state["events"].append({"turn": turn, "field": "asset", "operation": "repeat" if equivalent else operation,
            "targets": targets, "excerpt": asset["excerpt"], "query": asset["query"]})
    if parsed.get("budget"):
        state["budget"] = deepcopy(parsed["budget"])
    if any(e["turn"] == turn and e["field"] in {"investment_amount", "base_currency"} and e["operation"] == "retract" for e in state["events"]):
        state["budget"] = None
    result = {**parsed, "assets": deepcopy(state["assets"]), "budget": deepcopy(state["budget"]),
              "conditions": [{k: v for k, v in row.items() if k not in {"active", "superseded_in_turn"}}
                             for row in state["statements"] if row["active"]], "conversation_state": state}
    if result["assets"] and parsed["mode"] != "unrelated":
        result["mode"] = "research"
    return result
