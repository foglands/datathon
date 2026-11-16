"""Checked evidence tools for a model-selected analysis plan."""

import asyncio
from datetime import date
from fractions import Fraction
from math import isclose
import re
from copy import deepcopy
from hashlib import sha256

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
    summaries, sources, verifications = [], [], []
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
        independent_count = 0
        for start in days:
            due = add_months(start, months)
            if due <= days[-1] and any(start < end <= due and (due - end).days <= 7 for end in days):
                independent_count += 1
        if independent_count != len(returns):
            raise ValueError("Independent holding-window count verification failed.")
        symbol = item["asset"]["symbol"]
        verifications.append({"symbol": symbol, "months": months, "window_count": len(returns), "independent_count": independent_count,
            "sampling": "one possible start at each observed date; overlapping daily starts", "start": item["metrics"]["start"], "end": item["metrics"]["end"]})
        if returns:
            summaries.append(f"{symbol}: {len(returns)} overlapping observed {months}-month windows in {item['basis']} from {item['metrics']['start']} to {item['metrics']['end']}; "
                             f"worst change {min(returns):+.2%}, best change {max(returns):+.2%}. "
                             "End observations are on or before the anniversary within seven days. "
                             "Each observed date is a possible start; counts use overlapping daily starts, not monthly starts. "
                             "These overlapping historical outcomes are not future probabilities or guaranteed bounds.")
        else:
            summaries.append(f"{symbol}: available history cannot cover the stated {months}-month horizon. No long-horizon result was extrapolated.")
        sources.append(item["asset"]["source_url"])
    return {"title": "Evidence for your stated holding period", "text": " ".join(summaries), "sources": sources, "calculation_review": verifications}


async def _execute_checks(report, checks, provider, market_data):
    templates = {risk["id"]: risk for risk in risk_plan(report["profile"],
        [item["asset"] for item in report["analyses"]], report["analyses"])}
    for check in checks:
        key = check["tool"]
        if key not in report["executed_tools"]:
            report["executed_tools"].append(key)
        if key == "verify_calculations":
            from .customer_report import review
            checked = all(review(item["rows"], item["metrics"]) for item in report["analyses"])
            window = horizon_evidence(report["profile"], report["analyses"])
            text = ("Independent Python replay of existing financial metrics: " + ("passed. " if checked else "failed. ") +
                    "Holding-window verification: " + repr(window.get("calculation_review", [])) +
                    ". Each observed date can start an overlapping holding window; this is not a count of non-overlapping or monthly-start periods.")
            report["blocks"]["analysis.verification"] = {"title": "Independent calculation recheck", "text": text, "sources": window["sources"], "calculation_review": window.get("calculation_review", [])}
            report["tool_outcomes"].append({**check, "evidence_ids": ["analysis.verification"], "outcome": text, "status": "assessed" if checked else "unavailable",
                "produced_measures": (["arithmetic_check"] + (["window_count_check"] if window.get("calculation_review") else [])) if checked else []})
            continue
        if key == "product_comparison":
            items = report["analyses"]
            aligned = len(items) >= 2 and len({(row["basis"], tuple(point["date"] for point in row["rows"])) for row in items}) == 1
            text = ("Comparable observed histories: " + "; ".join(
                f"{row['asset']['symbol']}: adjusted-price change {row['metrics']['return']:+.2%}, largest peak-to-trough fall {row['metrics']['drawdown']:.2%}"
                for row in items) + f". All use {items[0]['basis']} over {items[0]['metrics']['start']} to {items[0]['metrics']['end']}. "
                "Independent Python checks passed. These are standalone historical outcomes, not a portfolio allocation or a prediction."
                if aligned else "A comparable product analysis is unavailable: at least two products on identical dates and currency are required.")
            report["blocks"]["analysis.comparison"] = {"title": "Comparable product evidence", "text": text, "sources": [x["asset"]["source_url"] for x in items],
                "scope": {"level": "product_comparison" if aligned else "limited_check", "objects": [x["asset"]["symbol"] for x in items],
                    "currency": items[0]["basis"] if aligned else None, "start": items[0]["metrics"]["start"] if aligned else None,
                    "end": items[0]["metrics"]["end"] if aligned else None, "method": "common-date adjusted-price buy-and-hold replay"}}
            report["tool_outcomes"].append({**check, "evidence_ids": ["analysis.comparison"], "outcome": text,
                "status": "assessed" if aligned else "missing_market_data"})
            continue
        if key == "horizon_window":
            profile = deepcopy(report["profile"])
            excerpt = check.get("horizon_excerpt")
            if excerpt:
                profile["fields"]["horizon"] = [{"excerpt": excerpt}]
            block = horizon_evidence(profile, report["analyses"])
            evidence_id = "analysis.horizon" + ("." + sha256(excerpt.encode()).hexdigest()[:8] if excerpt else "")
            report["blocks"][evidence_id] = block
            report["tool_outcomes"].append({**check, "evidence_ids": [evidence_id], "outcome": block["text"], "status": "assessed" if "overlapping observed" in block["text"] and "cannot cover" not in block["text"] else "missing_market_data"})
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
        if key == "historical_market":
            rows = assessed[0].get("results", [])
            produced = ["return", "drawdown", "recovery"] if rows else []
            if rows and all(row.get("volatility_basis") != "withheld" for row in rows):
                produced.append("volatility")
            if rows and all(all(row["metrics"]["rolling"][period]["worst_return"] is not None for period in ("12m", "36m")) for row in rows):
                produced.append("rolling_returns")
            if rows and all(row["stress"] and all(s["status"] == "assessed" for s in row["stress"]) for row in rows):
                produced.append("stress")
            report["tool_outcomes"][-1]["produced_measures"] = produced


async def execute_checks(report, checks, provider, market_data, budget=None):
    """Cache executions by tool/input snapshot, then check every task's output contract."""
    from .inquiry_contracts import record_task, tool_catalog, attach_evidence_scope
    for check in checks:
        key = check["tool"]
        cached = next((row for row in report["tool_outcomes"] if row["tool"] == key and row.get("horizon_excerpt") == check.get("horizon_excerpt")), None)
        if cached is not None:
            outcome = {**cached, "cache_hit": True}
        elif budget is not None and not budget.take("tool_calls"):
            outcome = {"outcome": "Evidence budget exhausted; task remains incomplete.", "evidence_ids": [], "produced_outputs": []}
        else:
            try:
                if budget is None:
                    await _execute_checks(report, [check], provider, market_data)
                else:
                    await asyncio.wait_for(_execute_checks(report, [check], provider, market_data), budget.remaining())
                outcome = report["tool_outcomes"][-1]
            except (ResearchUnavailable, asyncio.TimeoutError, ValueError) as exc:
                # Record a bounded public error, not exception payloads or provider credentials.
                evidence_id = "unavailable." + key
                report["blocks"][evidence_id] = {"title": "Evidence unavailable", "text": "The requested tool did not return verified evidence; its task remains unresolved.", "sources": []}
                outcome = {**check, "status": "unavailable", "evidence_ids": [evidence_id], "outcome": report["blocks"][evidence_id]["text"]}
                report["tool_outcomes"].append(outcome)
            status = outcome.get("status")
            produced = tool_catalog()[key]["outputs"] if status == "assessed" or key == "portfolio_context" else []
            outcome["produced_outputs"] = produced
            outcome.setdefault("produced_measures", tool_catalog()[key]["measures"] if produced else [])
        if "required_outputs" in check:
            record_task(report, check, outcome)
    attach_evidence_scope(report)
