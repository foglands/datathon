"""A question → research → calculation → review → report customer journey."""

import asyncio
import re
from datetime import datetime, timezone

from .customer_agents import understand
from .inquiry_engine import plan_inquiry as plan_analysis, synthesize_inquiry as synthesize
from .inquiry_contracts import InquiryBudget
from .customer_tools import execute_checks
from .customer_data import PublicResearch, ResearchUnavailable, ResearchAmbiguous, BudgetedResearch, StarterResearch, UnavailableResearch
from .customer_report import analyze, evidence_blocks, METHOD
from .review_snapshot import fingerprint
from .customer_profile import build_profile, risk_plan
from .customer_risks import explicit_rule_checks


def default_provider(market_data=None):
    """Organizer dataset first; the public source only for instruments it does not cover.

    DATATHON_PUBLIC_FALLBACK=0 disables the public source entirely, so every
    answer is reproducible from the archive alone.
    """
    from os import environ
    public = None if environ.get("DATATHON_PUBLIC_FALLBACK", "1").strip() == "0" else PublicResearch()
    if market_data is not None:
        return StarterResearch(market_data, fallback=public)
    if public is None:
        return UnavailableResearch("No market data is configured: set DATATHON_STARTER_PATH to the organizer archive, "
                                   "or enable the public source with DATATHON_PUBLIC_FALLBACK=1.")
    return public


async def research_question(question, *, runtime=None, provider=None, progress=None, market_data=None, previous_state=None, limits=None):
    provider = provider or default_provider(market_data)
    progress = progress or (lambda stage: None)
    progress("Understanding your idea and conditions")
    budget_tracker = InquiryBudget(limits)
    provider = BudgetedResearch(provider, budget_tracker)
    if runtime is not None:
        budget_tracker.take("model_calls")
    plan = await understand(question, runtime, previous_state=previous_state)
    budget_tracker.usage.append(plan.get("usage", {}))
    profile = build_profile(plan, question)
    if profile["resolved_budget"]:
        plan["budget"] = profile["resolved_budget"]
    if any(conflict["field"] in {"investment_amount", "base_currency"} for conflict in profile["conflicts"]):
        plan["budget"] = None
        plan["question"] = "Which investment amount and currency should this research use? Your statements conflict, so sizing has been withheld."
    result = {"question": question, "plan": plan, "analyses": [], "errors": [], "fx": None,
              "conversation_state": plan.get("conversation_state"), "tasks": [], "resolutions": [], "profile": profile, "risks": [], "rule_checks": [], "cpi": None,
              "blocks": {}, "editor": {}, "method": METHOD, "created_at": datetime.now(timezone.utc).isoformat()}
    requested = [asset for asset in plan["assets"] if asset["role"] == "consider"]
    if not requested:
        requested = [asset for asset in plan["assets"] if asset["role"] == "holding"]
    if plan["mode"] != "research" or not requested:
        result["status"] = "needs_input"
        result["report_digest"] = fingerprint(result)
        return result
    progress("Planning which claims need evidence")
    result["planning"] = await plan_analysis(question, plan, runtime, profile=profile, budget=budget_tracker)
    result["executed_tools"], result["tool_outcomes"] = [], []
    progress("Looking up dated prices and historical observations")

    async def fetch(asset):
        try:
            data = await asyncio.wait_for(asyncio.to_thread(provider.asset, asset["query"]), max(.01, budget_tracker.remaining()))
            if data.get("resolution"):
                result["resolutions"].append(data["resolution"])
            return data
        except ResearchAmbiguous as exc:
            result["resolutions"].append({"query": exc.query, "status": "needs_confirmation", "candidates": exc.candidates, "source_url": exc.source_url})
            result["errors"].append(str(exc))
            plan["question"] = "Which ticker and exchange did you mean for " + exc.query + "?"
            return None
        except asyncio.TimeoutError:
            result["errors"].append("The data request exceeded the research time budget.")
            return None
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
        raw_blocks, _ = evidence_blocks(plan, result["analyses"], result["errors"])
        # Keep facts and evidence gaps, not prewritten goal-based verdicts.
        result["blocks"] = {key: block for key, block in raw_blocks.items()
                            if key.endswith((".behavior", ".budget", ".stale")) or key in {"data_gap", "portfolio_gap"}}
        if not result["blocks"]:
            result["blocks"] = raw_blocks
        checks = result["planning"]["checks"]
        if runtime is None:
            # Explicitly labeled offline evidence recovery; never a model judgment.
            checks = [{"tool": risk["id"], "question": risk["reason"], "context_ids": ["user.request"]}
                      for risk in risk_plan(profile, assets, result["analyses"])]
        async def execute(requests):
            await execute_checks(result, requests, provider, market_data, budget=budget_tracker)
        progress("Collecting evidence for the selected analysis questions")
        await execute(checks)
        result["rule_checks"] = explicit_rule_checks(profile, result["analyses"])
        for index, check in enumerate(result["rule_checks"]):
            key = f"explicit_rule.{index}"
            actual = f"{check['actual']:.2%}" if check["actual"] is not None and check["metric"] != "recovery_days" else str(check["actual"])
            cap = f"{check['cap']:.2%}" if check["metric"] != "recovery_days" else f"{check['cap']} days"
            result["blocks"][key] = {"title": f"Explicit rule · {check['status'].replace('_', ' ')}",
                "text": f"{check['symbol']} · {check['metric']}: stated cap {cap}, observed result {actual}. {check['reason']}", "sources": []}
        missing_client = next((risk for risk in result["risks"] if risk["id"] == "cash_needs" and risk["status"] == "needs_client_information"), None)
        if missing_client and not profile["conflicts"]:
            plan["question"] = missing_client["limitation"]
        progress("Preparing the conclusion, supporting evidence and follow-up")
        result["editor"] = await synthesize(result, result["planning"], runtime, execute, progress, budget=budget_tracker)
        result["status"] = "ready" if not result["errors"] and result["editor"].get("answer_status") == "reviewed" else "partial"
    else:
        result["status"] = "unavailable"
    result["execution_budget"] = budget_tracker.snapshot()
    result["report_digest"] = fingerprint(result)
    return result
