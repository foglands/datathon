"""Open-ended profile facts, conflicts and question-specific risk planning."""

import re
from .decision_intake import _weights


FIELDS = ("goal", "horizon", "withdrawal", "willingness", "capacity", "income", "debt", "reserve",
          "portfolio", "investment_amount", "base_currency", "concentration", "asset_class", "exclusion",
          "esg", "experience", "explanation_depth", "loss", "liquidity", "preference", "funding")


def build_profile(plan, question=""):
    fields = {key: [] for key in FIELDS}
    for condition in plan["conditions"]:
        fields[condition["kind"]].append({"value": condition["excerpt"], "excerpt": condition["excerpt"],
            "source_type": "user_statement", "category": condition.get("source_type", "current_request"),
            "confirmation": "extracted_unconfirmed", "knowledge_status": condition.get("knowledge_status", "stated")})
    if plan.get("budget") and not fields["investment_amount"]:
        fields["investment_amount"].append({"value": plan["budget"]["excerpt"], "excerpt": plan["budget"]["excerpt"],
            "source_type": "user_statement", "category": "current_request", "confirmation": "extracted_unconfirmed"})
    conflicts = []
    # Multiple values in these single-valued fields remain visible until resolved.
    for key in ("investment_amount", "base_currency"):
        from .customer_state import semantic_key
        values = {semantic_key(key, item["value"]) for item in fields[key]}
        if len(values) > 1:
            conflicts.append({"field": key, "statements": [item["excerpt"] for item in fields[key]],
                              "impact": "This field is not used until the conflicting statements are resolved."})
    for condition in plan["conditions"]:
        if condition.get("operation") == "conflict":
            conflicts.append({"field": condition["kind"], "statements": [x["excerpt"] for x in plan["conditions"] if x["kind"] == condition["kind"]],
                              "impact": "The user supplied incompatible statements; clarify this field if material."})
    resolved_budget = None
    latest = question.rsplit("User clarification (takes precedence):", 1)
    if len(latest) == 2 and re.search(r"\b(?:use|confirm|confirmed|actually|correct amount)\b", latest[-1], re.I):
        from .customer_risks import _MONEY
        money = list(_MONEY.finditer(latest[-1]))
        if len(money) == 1 and re.search(r"invest|budget|amount|capital", latest[-1], re.I):
            match = money[0]
            value = float((match[2] or match[3]).replace(",", ""))
            if 0 < value <= 1e10:
                resolved_budget = {"amount": value, "currency": (match[1] or match[4]).upper(), "excerpt": latest[-1].strip()}
                for field in fields["investment_amount"]:
                    field["confirmation"] = "superseded_by_explicit_correction"
                fields["investment_amount"].append({"value": resolved_budget["excerpt"], "excerpt": resolved_budget["excerpt"],
                    "source_type": "user_statement", "category": "current_request", "confirmation": "explicitly_confirmed"})
                conflicts = [conflict for conflict in conflicts if conflict["field"] not in {"investment_amount", "base_currency"}]
    allocations = [_weights(item["excerpt"]) for item in fields["portfolio"]]
    allocations = [weights for weights in allocations if weights]
    weights = allocations[0] if len(allocations) == 1 else None
    if len(allocations) > 1:
        conflicts.append({"field": "portfolio", "statements": [item["excerpt"] for item in fields["portfolio"]],
                          "impact": "Multiple complete allocations are retained separately; no combined portfolio is inferred."})
    return {"fields": fields, "weights": weights, "resolved_budget": resolved_budget,
            "unknown": [key for key, values in fields.items() if not values or all(x.get("knowledge_status") == "unknown" for x in values)], "conflicts": conflicts,
            "classification": "No persona class; no age, occupation or name inference.",
            "assumptions": ["Trailing public history is a retrospective, not a forecast.",
                            "Each asset is assessed separately unless complete portfolio weights are supplied."]}


def risk_plan(profile, assets, analyses):
    fields = profile["fields"]
    all_text = " ".join(item["excerpt"] for values in fields.values() for item in values).lower()
    product_names = " ".join(asset.get("name", "") for asset in assets).lower()
    debt = bool(re.search(r"\bbonds?\b|fixed.income|treasury|aggregate bond|corporate debt", all_text + " " + product_names))
    risks = []

    def add(key, why, data, method, status, limitation):
        risks.append({"id": key, "reason": why, "data_needed": data, "method": method,
                      "status": status, "limitation": limitation, "results": []})

    add("historical_market", "The idea exposes the proposed amount to changes in market value.",
        "Adjusted closes on common dates", "Existing independently reviewed buy-and-hold replay",
        "assessed" if analyses else "missing_market_data", "History cannot establish a future loss limit or achieve a long-term goal.")
    if fields["withdrawal"] or fields["liquidity"]:
        add("cash_needs", "The user expects to use or withdraw money.",
            "Available investment amount; withdrawal amount, currency, first month and frequency",
            "Historical unit-sale replay with explicit schedule; compare withdrawals with available assets",
            "needs_client_information", "This checks funding needs, not bid/ask spreads or the ability to sell in a stressed market.")
    if fields["goal"] or fields["withdrawal"] or re.search(r"inflation|purchasing|保值", all_text):
        add("purchasing_power", "The goal concerns what the money can buy.",
            "CAD portfolio values and Canadian all-items CPI", "Monthly nominal growth divided by same-reference-month CPI growth",
            "missing_market_data", "Retrospective CPI is not a future inflation forecast; release vintages are unavailable.")
    if debt:
        add("interest_rate", "A stated holding or sourced product name identifies debt exposure.",
            "Dated issuer effective duration and an explicit rate shock", "First-order price sensitivity: minus duration times yield change",
            "missing_market_data", "No qualified duration disclosure was retrieved. Historical returns are not a duration estimate; convexity and spread changes are separate.")
        add("credit", "The idea includes debt instruments with underlying issuer credit exposure.",
            "Dated issuer rating distribution and government/corporate allocation", "Disclosed rating buckets, with unrated exposure retained as unknown",
            "missing_market_data", "Fund-level price volatility does not establish the underlying bonds' ratings or default probabilities.")
    if plan_amount(profile) or fields["liquidity"] or fields["withdrawal"]:
        add("market_liquidity", "The request involves a transaction amount or a need to convert assets to cash.",
            "Observed close and volume; a currency-consistent transaction amount", "Amount divided by recent average daily close-times-volume",
            "needs_client_information", "A limited trading-volume proxy; it does not measure spread, impact, execution certainty or underlying ETF liquidity.")
    if fields["portfolio"] or fields["concentration"] or fields["asset_class"] or len(assets) == 1:
        add("concentration", "The user is considering a single position or has stated allocation constraints.",
            "Explicit weights and eligible issuer, sector and fund-holdings disclosures", "Existing exposure bounds with coverage and unknown weight",
            "missing_market_data", "Standalone asset results do not establish whole-portfolio diversification; incomplete ETF look-through remains unknown.")
    if fields["esg"] or fields["exclusion"] or re.search(r"controvers|ESG|environment|social", all_text, re.I):
        add("controversy", "The user stated an exclusion or controversy preference.",
            "A named, dated screening list and eligible issuer identities", "Existing dated GPFG-list exposure bounds where qualified",
            "missing_market_data", "A list match is not a comprehensive ESG assessment; not listed is not controversy-free.")
    if fields["loss"] or fields["capacity"] or re.search(r"tail|value.at.risk|expected shortfall|\bVaR\b", all_text, re.I):
        add("tail_loss", "The user is concerned about losses or explicitly requested tail-risk measures.",
            "Sufficient complete consecutive daily observations", "One-session empirical loss quantile and mean beyond its tail threshold",
            "missing_market_data", "Exchange-session completeness is not certified. Daily VaR/ES are withheld rather than treating gaps as daily returns.")
    return risks


def plan_amount(profile):
    return bool(profile["fields"]["investment_amount"])
