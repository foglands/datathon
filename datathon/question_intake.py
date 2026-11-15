"""Route an investment question before running any financial tool."""

import re

from .allocation_request import parse_allocation_request
from .assistant_request import parse_comparison_request
from .planning_request import parse_planning_request, planning_context


_CLAUSE = re.compile(r".+?(?:[!?。！？;；\n]|\.(?=\s|$)|$)", re.S)
_HISTORY = re.compile(
    r"\b(?:histor(?:y|ical(?:ly)?)|replays?|backtest|held up|performed|past (?:stress|crashes|downturns?)|"
    r"maximum drawdown|terminal loss|terminal return|historiques?)\b|历史|歷史|以往|回放|回测|回測|回撤|期末",
    re.I,
)
_SYMBOL = re.compile(r"(?<![A-Za-z0-9_.$-])(?:\$[A-Za-z]{1,9}|[A-Z]{2,8})(?:[.-][A-Z0-9]{1,5})?(?![A-Za-z0-9_-])")
_NON_SYMBOL = frozenset({"AI", "CAD", "ETF", "ETFS", "EUR", "ESG", "GIC", "GICS", "GBP", "HKD", "USD", "VS"})
_CHOICE = re.compile(r"\b(?:between|versus|vs\.?|both|which|each|side by side)\b|两种|兩種|哪个|哪個|各自|对照|對照", re.I)
_ORDER = re.compile(
    r"\b(?:place|execute|submit|send|fill)\b[^.!?;\n]{0,44}\b(?:orders?|trades?)\b"
    r"|(?:下单|下單|执行交易|執行交易)|\bpasser (?:un|l['’]) ordre\b", re.I,
)
_FORECAST = re.compile(
    r"\b(?:forecast|predict|project|price target)\b[^.!?;\n]{0,105}\b(?:prices?|returns?|gains?|yield|profit|"
    r"performance|next (?:week|month|quarter|year))\b|\b(?:live|current|real[- ]time|today['’]s)\s+"
    r"(?:market )?(?:price|quote)s?\b|\b(?:returns?|performance)\b[^.!?;\n]{0,30}\bnext (?:week|month|quarter|year)\b"
    r"|实时(?:价格|行情)|即[時时](?:價格|行情)|(?:预测|預測|预估|預估)[^。！？\n]{0,35}(?:价格|價格|走势|走勢|回报|回報|收益)"
    r"|(?:未来|未來|明年)(?:的)?(?:收益|回报|回報|表现|表現)|\bcours en direct\b",
    re.I,
)
_SCOPE_NEGATION = re.compile(
    r"(?:\b(?:do not|don't|don’t|never|without|avoid|no need to)\s+(?:(?:want|need|intend|plan)\s+to\s+)?|(?:不要|无需|無需|不需要))$", re.I,
)
_TRADE_AUDIT = re.compile(
    r"\b(?:audit|test|check|assess|replay)\b[^!?;\n]{0,60}\b(?:my |the |a |proposed )?(?:trade|rebalance)\b"
    r"|\b(?:buy|add|increase|sell)\b[^!?;\n]{0,65}\b(?:percentage points?|basis points?|bps)\b"
    r"|(?:审计|審計|复盘|復盤)[^。！？\n]{0,20}(?:交易|调仓|調倉)"
    r"|(?:买入|買入|卖出|賣出)[^。！？\n]{0,32}(?:百分点|百分點)",
    re.I,
)
_PURCHASE_INTENT = (
    r"(?:(?:i|we)\s+(?:(?:want|plan|intend|would like)\s+to|(?:am|are)\s+(?:considering|thinking about))"
    r"|i['’]m\s+(?:considering|thinking about)|we['’]re\s+(?:considering|thinking about)"
    r"|(?:i|we)['’]d\s+like\s+to|(?:what if|should|could|can)\s+(?:i|we)"
    r"|(?:simulate|analyze|assess|test))"
)
_TICKER_TEXT = r"[A-Z][A-Z0-9]{0,7}(?:[.-][A-Z0-9]{1,5})?"
_PURCHASE_TICKER = rf"(?:\${_TICKER_TEXT}|(?-i:{_TICKER_TEXT}))"
_SHARE_TERMS = (
    rf"(?P<shares>(?:[0-9]{{1,3}}(?:,[0-9]{{3}})+|[0-9]+)(?:\.[0-9]+)?)\s+"
    rf"(?:shares?\s+(?:(?:of|in)\s+)?(?P<after>{_PURCHASE_TICKER})(?:\s+(?:stock|ETF))?"
    rf"|(?P<before>{_PURCHASE_TICKER})\s+shares?)"
)
_SHARE_PURCHASE = re.compile(
    rf"{_PURCHASE_INTENT}\s+(?:buy(?:ing)?|purchas(?:e|ing)|invest(?:ing)?(?:\s+in)?)\s+{_SHARE_TERMS}[.!?]?",
    re.I,
)
_SHARE_ORDER = re.compile(
    rf"(?:please\s+)?(?:buy|purchase|sell)\s+{_SHARE_TERMS}(?:\s+(?:now|immediately|at market))?[.!?]?",
    re.I,
)
_LIMIT_ACTION = "This simulation can explain a trade or audit confirmed hypothetical inputs. It cannot execute an order."
_LIMIT_FORECAST = "The available market evidence is historical. A live quote or future price or return estimate is unavailable."


def _draft(status, *, task=None, message="", **details):
    return {"status": status, "task": task, "message": message, "fields": {}, "sources": {}, **details}


def _positive_match(pattern, clause):
    return any(not _SCOPE_NEGATION.search(clause[:match.start()]) for match in pattern.finditer(clause))


def _plan_draft(plan, *, limitation=None):
    if limitation:
        plan = {**plan, "examples": ()}
    return _draft("planning", task="planning", plan=plan, limitation=limitation)


def _share_purchase(clauses, assets):
    """Use one explicitly proposed ticker and share quantity from the original question."""
    matches = [(clause, match) for clause in clauses if (match := _SHARE_PURCHASE.fullmatch(clause))]
    if len(matches) != 1:
        return None
    clause, match = matches[0]
    ticker = (match["after"] or match["before"]).lstrip("$").upper()
    shares = match["shares"]
    if ticker in _NON_SYMBOL or not shares.strip("0,."):
        return None
    draft = _draft("share_purchase", task="planning", needs_assets=assets is None)
    draft["fields"] = {
        "ticker": ticker,
        "shares": shares,
        "historical_available": None if assets is None else ticker in assets,
    }
    draft["sources"] = {"proposed_purchase": clause}
    return draft


def analyze_question(question: str, assets=None, *, semantic=None) -> dict:
    """Combine whole-request interpretation with grounded, mode-specific input checks.

    With no asset catalog, planning and scope decisions still work. An analysis
    requiring the catalog returns `needs_assets` so the caller can load it lazily.
    A model handoff supplies intent and original qualitative excerpts only.
    """
    if not isinstance(question, str) or not (question := question.strip()):
        return _draft("unrecognized", message="Describe an investment decision or historical comparison.")
    if len(question) > 8000:
        return _draft("clarify", message="Shorten the question and keep the decision and binding conditions.")

    task = semantic.get("task") if semantic and semantic.get("status") == "ready" else None
    comparison = parse_comparison_request(question, () if assets is None else assets)
    clauses = tuple(match[0].strip() for match in _CLAUSE.finditer(question) if match[0].strip())
    blocked = tuple(clause for clause in clauses if _positive_match(_FORECAST, clause))
    if any(_positive_match(_ORDER, clause) or _SHARE_ORDER.fullmatch(clause) for clause in clauses):
        return _draft("unsupported", message=_LIMIT_ACTION)
    if blocked:
        if not _HISTORY.search(question) and len(blocked) < len(clauses):
            remaining = " ".join(clause for clause in clauses if clause not in blocked)
            if plan := parse_planning_request(remaining, require_decision=True):
                return _plan_draft(plan, limitation=_LIMIT_FORECAST)
        return _draft("unsupported", message=_LIMIT_FORECAST)
    if _TRADE_AUDIT.search(question) and comparison["status"] != "ready":
        return _draft("trade_audit", task="trade_audit")

    context = planning_context(question)
    if allocation := parse_allocation_request(question, assets):
        return {**allocation, "plan": context}
    plan = parse_planning_request(question)
    purchase = _share_purchase(clauses, assets)

    history = bool(_HISTORY.search(question))
    asks_comparison = comparison["status"] != "unrecognized"
    apparent_symbols = set(_SYMBOL.findall(question)) - _NON_SYMBOL
    explicit_comparison = (
        (history and (asks_comparison or len(apparent_symbols) >= 2 or (context["financial"] and _CHOICE.search(question))))
        or (task == "compare_allocations" and purchase is None)
        or (asks_comparison and (len(apparent_symbols) >= 2 or not plan and (apparent_symbols or context["financial"])))
    )
    if comparison["status"] == "ready" or explicit_comparison:
        if assets is None:
            if comparison["status"] == "unsupported":
                return {**comparison, "task": "compare_allocations"}
            return _draft("clarify", task="compare_allocations", needs_assets=True)
        if not asks_comparison:
            comparison = parse_comparison_request(question, assets, extract_only=True)
            if comparison["status"] == "ready":
                comparison = {
                    **comparison, "status": "clarify", "scope_review_required": True,
                    "message": "Check the proposed assets, archived windows, and every binding condition before running this comparison.",
                }
        if comparison["status"] == "unrecognized":
            return _draft("clarify", task="compare_allocations",
                          message="Which two assets or complete allocations should the historical analysis compare?")
        return {**comparison, "task": "compare_allocations"}

    if purchase:
        return purchase
    if task == "unsupported":
        limitation = "The requested action may fall outside the evidence or simulation tools available."
        if plan:
            return _plan_draft(plan, limitation=limitation)
        return _draft("unsupported", message=limitation)
    if task == "trade_audit" and not plan:
        return _draft("trade_audit", task="trade_audit")
    if task == "planning":
        model_plan = semantic.get("plan") or {}
        local = plan or context
        plan = {
            **local,
            "points": {**model_plan.get("points", {}), **local["points"]},
            "instruments": tuple(dict.fromkeys((*local["instruments"], *model_plan.get("instruments", ())))),
            "examples": local["examples"],
        }
    if task == "analyze_allocation":
        return _draft("clarify", task=task, plan=context, message=(
            "List each ticker with its proposed weight. The weights must total 100%."
        ))
    if plan:
        return _plan_draft(plan)
    if asks_comparison and context["financial"]:
        return {**comparison, "task": "compare_allocations"}

    if context["financial"]:
        return _draft("clarify", task="planning", message=(
            "What decision should the assistant help with? For example, say what the money is for "
            "or name the options you want to weigh."
        ))
    return _draft("unrecognized", message=(
        "Describe an investment choice, a trade you want to audit, or two investments to compare historically."
    ))
