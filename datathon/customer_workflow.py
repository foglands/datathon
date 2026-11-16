"""A question → research → calculation → review → report customer journey."""

import asyncio
import re
from datetime import datetime, timezone

from .customer_agents import understand, edit_report
from .customer_data import PublicResearch, ResearchUnavailable
from .customer_report import analyze, evidence_blocks, METHOD
from .review_snapshot import fingerprint
from .customer_profile import build_profile, risk_plan
from .customer_risks import quantify_risks, risk_blocks, explicit_rule_checks


async def research_question(question, *, runtime=None, provider=None, progress=None, market_data=None):
    provider = provider or PublicResearch()
    progress = progress or (lambda stage: None)
    progress("Understanding your idea and conditions")
    plan = await understand(question, runtime)
    profile = build_profile(plan, question)
    if profile["resolved_budget"]:
        plan["budget"] = profile["resolved_budget"]
    if any(conflict["field"] in {"investment_amount", "base_currency"} for conflict in profile["conflicts"]):
        plan["budget"] = None
        plan["question"] = "Which investment amount and currency should this research use? Your statements conflict, so sizing has been withheld."
    result = {"question": question, "plan": plan, "analyses": [], "errors": [], "fx": None,
              "profile": profile, "risks": [], "rule_checks": [], "cpi": None,
              "blocks": {}, "editor": {}, "method": METHOD, "created_at": datetime.now(timezone.utc).isoformat()}
    requested = [asset for asset in plan["assets"] if asset["role"] == "consider"]
    if not requested:
        requested = [asset for asset in plan["assets"] if asset["role"] == "holding"]
    if plan["mode"] != "research" or not requested:
        result["status"] = "needs_input"
        result["report_digest"] = fingerprint(result)
        return result
    progress("Looking up dated prices and historical observations")

    async def fetch(asset):
        try:
            return await asyncio.to_thread(provider.asset, asset["query"])
        except ResearchUnavailable as exc:
            result["errors"].append(f"{asset['query']}: {exc}")
            return None

    assets = [item for item in await asyncio.gather(*(fetch(asset) for asset in requested)) if item]
    assets = list({asset["symbol"]: asset for asset in assets}.values())
    budget = plan["budget"]
    explicit_currencies = set()
    for field in profile["fields"]["base_currency"]:
        text = field["excerpt"].lower()
        if re.search(r"\bcad\b|canadian dollars?", text):
            explicit_currencies.add("CAD")
        if re.search(r"\busd\b|us dollars?|u\.s\. dollars?", text):
            explicit_currencies.add("USD")
    target_currency = budget["currency"] if budget else next(iter(explicit_currencies)) if len(explicit_currencies) == 1 else None
    if any(conflict["field"] == "base_currency" for conflict in profile["conflicts"]):
        target_currency = None
    if target_currency in {"CAD", "USD"} and any(asset["currency"] != target_currency for asset in assets):
        progress("Checking the Bank of Canada exchange-rate observations")
        try:
            result["fx"] = await asyncio.to_thread(provider.fx)
        except ResearchUnavailable as exc:
            result["errors"].append(str(exc))
    progress("Calculating the evidence and independently checking each figure")
    try:
        result["analyses"] = analyze(assets, budget, result["fx"], target_currency=target_currency)
    except ValueError as exc:
        result["errors"].append(str(exc))
        if len(assets) > 1:
            for asset in assets:
                try:
                    result["analyses"].extend(analyze([asset], budget, result["fx"], target_currency=target_currency))
                except ValueError as asset_error:
                    result["errors"].append(f"{asset['symbol']}: {asset_error}")
    if result["analyses"]:
        result["risks"] = risk_plan(profile, assets, result["analyses"])
        if any(risk["id"] == "purchasing_power" for risk in result["risks"]):
            progress("Checking purchasing power against Canadian CPI")
            try:
                result["cpi"] = await asyncio.to_thread(provider.cpi)
            except ResearchUnavailable as exc:
                for risk in result["risks"]:
                    if risk["id"] == "purchasing_power":
                        risk["limitation"] = str(exc)
        progress("Running the checks relevant to your stated conditions")
        result["risks"] = quantify_risks(result["risks"], profile, result["analyses"], budget,
                                         cpi=result["cpi"], market_data=market_data,
                                         today=result["created_at"][:10])
        result["blocks"], required = evidence_blocks(plan, result["analyses"], result["errors"])
        additional, risk_priority = risk_blocks(result["risks"])
        result["blocks"].update(additional)
        required = risk_priority or required
        result["rule_checks"] = explicit_rule_checks(profile, result["analyses"])
        for index, check in enumerate(result["rule_checks"]):
            key = f"explicit_rule.{index}"
            actual = f"{check['actual']:.2%}" if check["actual"] is not None and check["metric"] != "recovery_days" else str(check["actual"])
            cap = f"{check['cap']:.2%}" if check["metric"] != "recovery_days" else f"{check['cap']} days"
            result["blocks"][key] = {"title": f"Explicit rule · {check['status'].replace('_', ' ')}",
                "text": f"{check['symbol']} · {check['metric']}: stated cap {cap}, observed result {actual}. {check['reason']}", "sources": []}
            if check["status"] == "observed_breach":
                required = key
        missing_client = next((risk for risk in result["risks"] if risk["id"] == "cash_needs" and risk["status"] == "needs_client_information"), None)
        if missing_client and not profile["conflicts"]:
            plan["question"] = missing_client["limitation"]
        progress("Preparing the conclusion, supporting evidence and follow-up")
        result["editor"] = await edit_report(plan, result["blocks"], runtime, required)
        result["status"] = "partial" if result["errors"] else "ready"
    else:
        result["status"] = "unavailable"
    result["report_digest"] = fingerprint(result)
    return result
