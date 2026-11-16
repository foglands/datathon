"""Checked evidence tools for a model-selected analysis plan."""

import asyncio
from datetime import date
from fractions import Fraction
from math import isclose
import re

from .customer_data import ResearchUnavailable
from .customer_profile import risk_plan
from .customer_risks import quantify_risks, risk_blocks, add_months
from .customer_reasoning import CATALOG


def horizon_evidence(profile, analyses):
    excerpts = [row["excerpt"] for row in profile["fields"]["horizon"]]
    horizons = set()
    for text in excerpts:
        words = {"one":"1", "two":"2", "three":"3", "five":"5", "six":"6", "ten":"10"}
        text = re.sub(r"\b(" + "|".join(words) + r")\b", lambda m: words[m[0]], text.lower())
        for value, unit in re.findall(r"\b(\d+)\s*(months?|years?)\b", text):
            horizons.add(int(value) * (12 if unit.startswith("year") else 1))
    if len(horizons) != 1 or not 1 <= next(iter(horizons), 0) <= 600:
        return {"title": "Holding-period evidence gap", "text": "No single unambiguous supported holding period was stated. Confirm the intended horizon; no period or loss threshold was inferred.", "sources": []}
    months = next(iter(horizons))
    summaries, sources = [], []
    for item in analyses:
        rows = item["rows"]
        days = [date.fromisoformat(row["date"]) for row in rows]
        returns = []
        # Use the last observed close on/before each anniversary, within seven days.
        # Do not extend the sample or substitute a longer holding period.
        from bisect import bisect_right
        for i, row in enumerate(rows):
            due = add_months(days[i], months)
            if due > days[-1]:
                continue
            end = bisect_right(days, due) - 1
            if end <= i or (due - days[end]).days > 7:
                continue
            value = rows[end]["price"] / row["price"] - 1
            exact = Fraction(str(rows[end]["price"])) / Fraction(str(row["price"])) - 1
            if not isclose(value, float(exact), rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("Holding-period verification failed.")
            returns.append(value)
        symbol = item["asset"]["symbol"]
        if returns:
            summaries.append(f"{symbol}: {len(returns)} overlapping observed {months}-month windows in {item['basis']}; "
                             f"worst change {min(returns):+.2%}, best change {max(returns):+.2%}. "
                             "End observations are on or before the anniversary within seven days. "
                             "These overlapping historical outcomes are not future probabilities or guaranteed bounds.")
        else:
            summaries.append(f"{symbol}: available history cannot cover the stated {months}-month horizon. No long-horizon result was extrapolated.")
        sources.append(item["asset"]["source_url"])
    return {"title": "Evidence for your stated holding period", "text": " ".join(summaries), "sources": sources}


async def execute_checks(report, checks, provider, market_data):
    templates = {risk["id"]: risk for risk in risk_plan(report["profile"],
        [item["asset"] for item in report["analyses"]], report["analyses"])}
    for check in checks:
        key = check["tool"]
        if key in report["executed_tools"]:
            continue
        report["executed_tools"].append(key)
        if key == "horizon_window":
            block = horizon_evidence(report["profile"], report["analyses"])
            report["blocks"]["analysis.horizon"] = block
            report["tool_outcomes"].append({**check, "evidence_ids": ["analysis.horizon"], "outcome": block["text"]})
            continue
        if key == "portfolio_context":
            profile = report["profile"]
            text = ("Complete explicitly stated allocation weights: " + repr(profile["weights"]) + ". " if profile["weights"] else
                    "Complete portfolio weights were not supplied. ")
            text += ("Standalone purchase results do not establish its impact on the whole portfolio. "
                     "Existing holdings and the proposed before/after allocation must be confirmed for an impact comparison; no weights or funding were invented.")
            report["blocks"]["analysis.portfolio"] = {"title": "Scope of portfolio evidence", "text": text, "sources": []}
            report["tool_outcomes"].append({**check, "evidence_ids": ["analysis.portfolio"], "outcome": text})
            continue
        risk = templates.get(key, {"id": key, "reason": check["question"], "data_needed": CATALOG[key],
            "method": CATALOG[key], "status": "missing_market_data", "limitation": "The required input or qualified data is unavailable.", "results": []})
        # A proposed question is not verified evidence and must not seed the numeric registry.
        risk["reason"] = CATALOG[key]
        if key == "purchasing_power" and report["cpi"] is None:
            try:
                report["cpi"] = await asyncio.to_thread(provider.cpi)
            except ResearchUnavailable as exc:
                risk["limitation"] = str(exc)
        assessed = quantify_risks([risk], report["profile"], report["analyses"], report["plan"]["budget"],
            cpi=report["cpi"], market_data=market_data, today=report["created_at"][:10])
        blocks, _ = risk_blocks(assessed)
        assessed[0]["reason"] = check["question"]
        report["risks"].extend(assessed)
        report["blocks"].update(blocks)
        report["tool_outcomes"].append({**check, "status": assessed[0]["status"], "evidence_ids": list(blocks),
                                      "outcome": " ".join(block["text"] for block in blocks.values())})
