"""Ground one fictional allocation and its replay requirements in the request."""

import re
from decimal import localcontext

from .assistant_request import _INTENT, _ORDINARY, _PERCENT, _asset_pattern, _blank, _weight_matches, parse_comparison_request


_ALLOCATION = re.compile(r"\b(?:allocat(?:e|ing|ion)|portfolios?|holdings|weights?|funds?|ETFs?)\b", re.I)
_TRADE = re.compile(
    r"\b(?:sell|liquidate|execute|place (?:a |the |my )?(?:market |limit )?order)\b"
    r"|\b(?:percentage points?|basis points?|bps)\b", re.I,
)
_TWO_SIDES = re.compile(
    r"\b(?:versus|vs\.?|relative to|side by side|(?:safer|riskier) than)\b", re.I,
)
_LABELLED_OPTIONS = re.compile(r"\b(?:portfolio|allocation|option)\s+([AB])\b", re.I)
_SYMBOL = re.compile(
    r"(?<![A-Za-z0-9_.$-])\$?(?P<ticker>[A-Z][A-Z0-9]{1,8}(?:[.-][A-Z0-9]{1,5})?)"
    r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9])"
)
_NON_SYMBOLS = (_ORDINARY | {
    "AUD", "BONDS", "CNY", "EQUITY", "FUNDS", "GIC", "GICS", "HKD", "JPY", "NZD", "SAVINGS", "STOCKS",
}) - {"CASH"}
_QUALIFIED_WEIGHT = re.compile(
    r"\b(?:about|around|roughly|approximately|under|over|between|up to|at least|at most|rather than)\s*$", re.I,
)
_ALTERNATIVE = re.compile(r"\b(?:or|either|instead|otherwise|alternatively)\b", re.I)
_ALTERNATIVE_TAIL = re.compile(r"^\s*[,;]?\s*(?:or|instead|otherwise|alternatively)\b", re.I)
_UNMODELED_METHOD = re.compile(
    r"\b(?:rebalanc(?:e|ed|es|ing)|(?:dollar[- ]cost|periodic) averaging|leverage|margin|hedg(?:e|ed|ing))\b",
    re.I,
)
_RISK_NARRATIVE = re.compile(
    r"\b(?:so (?:that )?)?(?:I|we)\s+(?:don['’]t|do not)\s+(?:want to\s+)?lose\b"
    r"|\bif\s+(?:(?:one|any|a|the|my|our|these|those)\s+)?(?:funds?|ETFs?|stocks?|markets?)"
    r"\s+(?:crash(?:es)?|falls?|drops?|declines?)\b", re.I,
)
_BALANCE_CURRENCY = re.compile(
    r"\b(?:"
    r"(?:my|our|the|this)\s+(?:cash|savings|balance|investment budget|starting amount)\s+(?:is|are)"
    r"|(?:I|we)\s+(?:have|saved|hold)\s+(?:about\s+)?\$[0-9][0-9,.]*[kKmM]?"
    r")\s+(?:in|denominated in)\s+(?:US dollars?|USD|EUR|GBP|CNY|HKD|euros?)\b", re.I,
)
_REPORTED_MEASURE = re.compile(
    r"\b(?:(?:returned|gained|lost|earned|yielded)\s*"
    r"|(?:gains?|losses?|returns?|discounts?|yields?|fees?)\s*(?:(?:were|are|of)\s+|[:=]\s*))"
    r"(?:(?:about|around|roughly)\s+)?$", re.I,
)
_WEIGHT_PROMPT = "Give one set of at least two ticker symbols with exact positive weights that add to 100%."


def _result(status, fields, sources, message="", *, needs_assets=False):
    return {
        "status": status, "task": "analyze_allocation", "fields": fields, "sources": sources,
        "message": message, "needs_assets": needs_assets,
    }


def _assets_in_question(question, available):
    candidates = {match.span(): match for match in _SYMBOL.finditer(question)
                  if match["ticker"] not in _NON_SYMBOLS}
    if available:
        candidates.update((match.span(), match) for match in _asset_pattern(available).finditer(question))
    return tuple(candidates.values())


def parse_allocation_request(question: str, assets=None) -> dict | None:
    """Interpret the stated weights without inventing positions or changing the scope."""
    if not isinstance(question, str) or not question.strip() or len(question) > 8000:
        return None
    options = {label.upper() for label in _LABELLED_OPTIONS.findall(question)}
    if _INTENT.search(question) or _TWO_SIDES.search(question) or _TRADE.search(question) or len(options) > 1:
        return None

    available = None if assets is None else {asset.upper() for asset in assets if isinstance(asset, str) and asset}
    candidates = _assets_in_question(question, available)
    bound = _weight_matches(question, candidates, allow_unbound=True)
    contextual = bool(_ALLOCATION.search(question))
    percentages = tuple(re.finditer(_PERCENT, question))
    if not bound and (len(percentages) < 2 or (not contextual and len(candidates) < 2)):
        return None
    if not bound or len(bound) < 2:
        if not contextual and len(percentages) < 2:
            return None
        return _result("clarify", {}, {}, _WEIGHT_PROMPT, needs_assets=available is None)

    positions = {asset["ticker"].upper(): amount for _, _, asset, amount in bound}
    start = min(left for left, _, _, _ in bound)
    end = max(right for _, right, _, _ in bound)
    sources = {"options": question[start:end]}
    if _REPORTED_MEASURE.search(question[:start]):
        return None
    qualified = any(_QUALIFIED_WEIGHT.search(question[:left]) for left, _, _, _ in bound)
    between = _blank(question, [(left, right) for left, right, _, _ in bound])[start:end]
    with localcontext() as precision:
        precision.prec = len(question)
        complete = len(positions) == len(bound) and sum(positions.values()) == 100
        weights = {ticker: float(amount / 100) for ticker, amount in positions.items()}
    if qualified or not complete or not all(weights.values()) or _ALTERNATIVE.search(between) or _ALTERNATIVE_TAIL.match(question[end:]):
        guess_lowercase = available is None and contextual and len(percentages) > len(bound)
        return _result("clarify", {}, sources, _WEIGHT_PROMPT, needs_assets=guess_lowercase)

    control_text = _blank(question, [(left, right) for left, right, _, _ in bound])
    context_matches = (*_RISK_NARRATIVE.finditer(control_text), *_BALANCE_CURRENCY.finditer(control_text))
    control_text = _blank(control_text, [match.span() for match in context_matches])
    controls = parse_comparison_request(control_text, (), extract_only=True)
    source_details = {field: source for field, source in controls["sources"].items() if source in question}
    sources.update(source_details)
    fields = {
        **controls["fields"], "weights": weights,
        "unsupported_assets": tuple(ticker for ticker in weights if available is not None and ticker not in available),
    }
    if _UNMODELED_METHOD.search(control_text):
        return _result(
            "unsupported", fields, sources,
            "The historical allocation replay buys at the start of each window and holds. "
            "It cannot model rebalancing, periodic trades, leverage, or hedging.",
        )
    scope_message = controls["message"].replace("The comparison replays", "The allocation analysis uses").replace(
        "comparison", "allocation replay"
    )
    if "Please label the two allocations" in scope_message:
        scope_message = "State any drawdown limit separately and explain other percentages in the request."
    if controls["status"] == "unsupported":
        return _result("unsupported", fields, sources, scope_message)
    if controls["status"] == "clarify" or not set(controls["fields"]) <= source_details.keys():
        return _result(
            "clarify", fields, sources, "Check the requested scope. "
            + (scope_message or "State each replay condition in a separate clause."),
        )
    return _result("allocation", fields, sources, needs_assets=available is None)
