"""Select a current-market lookup from user-stated inputs."""

import re
from decimal import Decimal
from typing import Literal

from .agents import Role, StrandsAgents, ToolSpec
from .model_settings import configured_bedrock_runtime
from .planning_request import _OTHER_PERSON, parse_planning_request, planning_context
from .runtime_budget import PROFILE_MAX_REQUEST_BYTES, RuntimeBudgetExceeded, RuntimeLimits, run_bounded


MarketIntent = Literal["quote", "share_purchase", "market_history", "planning", "not_applicable", "needs_input", "unsupported"]
LookupScope = Literal["latest_quote", "quote_and_history", "none"]
DataSource = Literal["alpaca", "none"]

_SCOPES = {"quote": "latest_quote", "share_purchase": "quote_and_history", "market_history": "quote_and_history"}
_UNROUTED = {"planning", "not_applicable", "needs_input", "unsupported"}
_LIMITS = RuntimeLimits(12, 2, 18000)
_CLAUSE_BREAK = re.compile(r"\n+|(?<=[.!?;])\s+")
_TICKER = r"(?:\$[A-Za-z][A-Za-z0-9]{0,7}(?:[.-][A-Za-z0-9]{1,5})?|[A-Z][A-Z0-9]{0,7}(?:[.-][A-Z0-9]{1,5})?)"
_SYMBOL = re.compile(rf"(?<![\w.$-]){_TICKER}(?![\w$-])")
_EXCLUDED = {"I", "A", "AI", "AND", "AS", "AT", "CAD", "ETF", "ETFS", "ESG", "EUR", "FOR", "GBP", "IN", "OF",
             "OR", "THE", "TO", "USD", "US", "VS", "WITH"}
_QUANTITY = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
_SHARE_TERMS = re.compile(
    rf"(?<![\w.,+−-])(?P<quantity>{_QUANTITY})\s+"
    rf"(?:(?i:shares?\s+(?:(?:of|in)\s+)?)(?P<after>{_TICKER})|(?P<before>{_TICKER})(?i:\s+shares?))"
    r"(?![\w$-])",
)
_FIRST_PERSON_ACTION = re.compile(
    r"\b(?:(?:I|we)\s+(?:(?:want|plan|intend|would like|hope)\s+to|(?:am|are)\s+(?:considering|thinking about))"
    r"|(?:I['’]m|we['’]re)\s+(?:considering|thinking about)|(?:I|we)['’]d\s+like\s+to"
    r"|(?:what if|should|can|could)\s+(?:I|we)|(?:simulate|analyze|assess|test))"
    r"\s+(?:buy|buying|bought|purchase|purchasing|purchased|invest|investing)(?:\s+in)?\s*$",
    re.I,
)
_PURCHASE_WORDS = re.compile(r"\b(?:buy|buying|bought|purchase|purchasing|purchased|invest|investing)\b", re.I)
_PROSPECTIVE = re.compile(
    r"\b(?:want|plan|intend|would|consider(?:ing)?|think(?:ing)?|can see|hope|might|should|could|what if|simulate|analyze|assess|test)\b",
    re.I,
)
_INEXACT_QUANTITY = re.compile(
    r"\b(?:about|around|approximately|roughly|up to|at least|at most|max(?:imum)?|min(?:imum)?)\s*$"
    r"|[0-9]\s*(?:to|or|and|[-–—])\s*$", re.I,
)
_SHARE_WORD = re.compile(r"\bshares?\b", re.I)
_QUOTE_WORDS = re.compile(r"\b(?:quotes?|prices?|trading at|worth per share|cost per share)\b", re.I)
_CURRENT = re.compile(r"\b(?:current|latest|live|now|today|right now|real[ -]time|recent|last|past)\b", re.I)
_HISTORY = re.compile(r"\b(?:history|historical|performance|returns?|drawdown|trend|recent trading)\b", re.I)
_FROZEN_WINDOW = re.compile(r"\b(?:reference case|archived stress|stress window|replay|backtest)\b", re.I)
_EXACT_RANGE = re.compile(
    r"\b(?:last|past|previous|preceding|trailing)\s+(?:\S+\s+){0,3}(?:minutes?|hours?|days?|weeks?|months?|quarters?|years?)\b"
    r"|\b(?:as of|on|since|in|during|through|between|from)\s+(?:20[0-9]{2}(?:-[0-9]{2}-[0-9]{2})?|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+[0-9]{1,2})\b|\b(?:yesterday|YTD|year[- ]to[- ]date)\b",
    re.I,
)
_SUPPORTED_RANGE = re.compile(r"(?:last|past|previous|preceding|trailing)\s+90\s+(?:calendar\s+)?days", re.I)
_UNSUPPORTED_VIEW = re.compile(
    r"\b(?:hourly|intraday|minute bars?|(?:in|convert(?:ed)? to)\s+(?:CAD|AUD|EUR|GBP|HKD|CNY|JPY))\b",
    re.I,
)
_QUOTE_END = re.compile(r"\b(?:quote|stock price|share price|trading at)\b", re.I)
_NEGATED = re.compile(r"\b(?:don['’]t|didn['’]t|do not|did not|never|avoid|not interested in|no need to|without looking up)\b", re.I)
_FORECAST = re.compile(r"\b(?:forecast|predict|price target|future (?:price|return))\b"
                       r"|\b(?:price|return)\s+(?:for\s+)?next (?:week|month|year)\b", re.I)
_ORDER = re.compile(r"\b(?:place|execute|submit|send|fill)\b[^.!?;\n]{0,45}\b(?:orders?|trades?)\b", re.I)
_DIRECT_ORDER = re.compile(r"^(?:please\s+)?(?:buy|sell|purchase)\s+", re.I)
_TRACE_KEYS = {"event", "role", "status", "tool_name", "model_id", "region", "operation", "http_status", "error_type",
               "error_code", "stop_reason", "duration_ms", "total_tokens"}

_ROLE = Role(
    "Interpret the entire latest English request from a fictional investor. Choose a task and whether it calls for a read-only lookup. "
    "Use quote/latest_quote for the latest observed per-share price of one explicitly supplied ticker. "
    "Use share_purchase/quote_and_history for a hypothetical single-ticker purchase with an explicit share count. "
    "Use market_history/quote_and_history for recent price behavior or unquantified purchase research on one explicitly supplied ticker. "
    "Use planning for an investment goal or broad choices without an explicit request for a ticker-level lookup. "
    "For planning, cite the clause with the stated goal or choices. Use not_applicable for unrelated requests, "
    "fixed stress-window replays, and other historical workflows. Use unsupported for actual order execution "
    "and future price forecasts. Use needs_input for missing or ambiguous inputs to an explicit lookup. "
    "Select data_source alpaca for a lookup. For other tasks use scope none and data_source none and omit ticker and share_count. "
    "Use a candidate clause ID that contains the operative request. Copy the exact ticker spelling from that clause, including a dollar prefix if present. "
    "For share_purchase, copy the exact quantity that modifies shares of the ticker. Treat potential purchases as proposals, never holdings. "
    "Do not resolve a company name into a guessed ticker; ask for the ticker. "
    "Do not use assets from quoted, rejected, or unrelated text, or choose between several candidate tickers. "
    "Call select_market_lookup once. Never fetch a URL, produce market values, or advise a trade."
)


class LiveMarketIntakeAgents(StrandsAgents):
    def _role_config(self, role: str) -> Role:
        return _ROLE if role == "live_market_intake" else super()._role_config(role)


def configured_live_market_intake_runtime() -> StrandsAgents:
    """Use the configured profile model for current-market understanding."""
    runtime = configured_bedrock_runtime(profile=True)
    return LiveMarketIntakeAgents(model_id=runtime.model_id, region=runtime.region)


def _symbols(clause):
    return {match[0] for match in _SYMBOL.finditer(clause) if match[0].lstrip("$").upper() not in _EXCLUDED}


def _share_evidence(clause):
    return [(match["after"] or match["before"], match["quantity"]) for match in _SHARE_TERMS.finditer(clause)
            if match["quantity"].strip("0,.") and _PURCHASE_WORDS.search(clause[:match.start()])
            and _PROSPECTIVE.search(clause[:match.start()]) and not _INEXACT_QUANTITY.search(clause[:match.start()])]


def _allowed_clause(clause):
    return not (clause.startswith(('"', "'", "“", "‘")) or _NEGATED.search(clause) or _OTHER_PERSON.search(clause))


def _market_history(clause):
    explicit_range = _EXACT_RANGE.search(clause)
    return bool((explicit_range or _CURRENT.search(clause)) and (
        _HISTORY.search(clause) or (explicit_range and _QUOTE_WORDS.search(clause))
    )) or any(
        _FIRST_PERSON_ACTION.search(clause[:match.start()]) for match in _SYMBOL.finditer(clause)
    )


def _market_quote(clause):
    return bool(_QUOTE_END.search(clause) or ((_CURRENT.search(clause) or _EXACT_RANGE.search(clause))
                                             and _QUOTE_WORDS.search(clause)))


def _prohibited_request(clauses):
    for clause in clauses:
        if (_ORDER.search(clause) and not _NEGATED.search(clause)) or (
            _DIRECT_ORDER.match(clause) and _SHARE_TERMS.search(clause)
        ):
            return "unsupported"
        if _FORECAST.search(clause) and (_QUOTE_WORDS.search(clause) or _HISTORY.search(clause)):
            return "unsupported"
    return None


def _range_is_supported(clauses, intent):
    for clause in clauses:
        if _FROZEN_WINDOW.search(clause) or _UNSUPPORTED_VIEW.search(clause):
            return False
        if any(intent == "quote" or not _SUPPORTED_RANGE.fullmatch(match[0]) for match in _EXACT_RANGE.finditer(clause)):
            return False
    return True


def _result(status, *, intent=None, symbol=None, shares=None, wording=None, origin="local", trace=(), usage=None,
            message=None):
    return {
        "status": status, "intent": intent, "scope": _SCOPES.get(intent), "symbol": symbol, "shares": shares,
        "data_source": "alpaca" if intent in _SCOPES else None, "wording": wording, "origin": origin, "message": message,
        "trace": tuple({key: value for key, value in event.items() if key in _TRACE_KEYS
                        and type(value) in (str, bool, int, float, type(None))} for event in trace),
        "usage": usage or {},
    }


def _ground(intent, scope, data_source, clause, ticker, share_count):
    if intent in _UNROUTED and scope == data_source == "none" and not ticker and not share_count:
        if intent == "planning":
            if not _allowed_clause(clause) or not planning_context(clause)["financial"]:
                raise ValueError("Use the clause containing the investment goal or choices.")
            return _result(intent, intent=intent, wording=clause, origin="bedrock")
        return _result(intent, origin="bedrock")
    if (intent not in _SCOPES or scope != _SCOPES[intent] or data_source != "alpaca" or not ticker or _symbols(clause) != {ticker}
            or not _allowed_clause(clause) or _FROZEN_WINDOW.search(clause)):
        raise ValueError("Choose a supported lookup with a single ticker from the operative clause.")
    if intent == "share_purchase":
        if (ticker, share_count) not in _share_evidence(clause):
            raise ValueError("Copy the share count linked to the selected ticker.")
    elif share_count or (intent == "quote" and not _market_quote(clause)) or (
        intent == "market_history" and not _market_history(clause)
    ):
        raise ValueError("Copy the clause asking for the selected market evidence.")
    return _result("ready", intent=intent, symbol=ticker.lstrip("$").upper(),
                   shares=share_count.replace(",", "") or None, wording=clause, origin="bedrock")


def _local_intake(clauses):
    choices = []
    needs_ticker = False
    for clause in clauses:
        if not _allowed_clause(clause) or _FROZEN_WINDOW.search(clause):
            continue
        symbols = _symbols(clause)
        purchase = [(match["after"] or match["before"], match["quantity"])
                    for match in _SHARE_TERMS.finditer(clause)
                    if _FIRST_PERSON_ACTION.search(clause[:match.start()]) and match["quantity"].strip("0,.")]
        if purchase and len(symbols) == 1 and len(purchase) == 1:
            ticker, shares = purchase[0]
            choices.append(_result("ready", intent="share_purchase", symbol=ticker.lstrip("$").upper(),
                                   shares=shares.replace(",", ""), wording=clause))
        elif purchase or any(_FIRST_PERSON_ACTION.search(clause[:match.start()])
                             for match in re.finditer(rf"\b{_QUANTITY}\s+", clause)
                             if _SHARE_WORD.search(clause[match.end():])):
            needs_ticker = True
        elif _market_history(clause) or _market_quote(clause):
            if len(symbols) != 1:
                needs_ticker = True
                continue
            ticker, = symbols
            choices.append(_result("ready", intent="market_history" if _market_history(clause) else "quote",
                                   symbol=ticker.lstrip("$").upper(), wording=clause))
    if choices and len({choice["symbol"] for choice in choices}) == 1 and not needs_ticker:
        return next((choice for choice in choices if choice["intent"] == "share_purchase"), choices[0])
    return _result("needs_input" if needs_ticker or choices else "not_applicable")


def _select_request(question, clauses, model_result=None):
    local = _local_intake(clauses)
    if model_result and model_result["status"] == "ready" and (
        local["status"] == "not_applicable"
        or all(model_result[key] == local[key] for key in ("symbol", "intent", "shares"))
    ):
        local = model_result
    if local["status"] == "not_applicable":
        if model_result and model_result["status"] == "planning":
            local = model_result
        elif parse_planning_request(question) is not None:
            local = _result("planning", intent="planning")
        elif model_result:
            local = model_result
    return _validate_request_scope(local, clauses)


def _validate_request_scope(result, clauses):
    candidates = {(ticker.lstrip("$").upper(), Decimal(shares.replace(",", "")))
                  for clause in clauses if _allowed_clause(clause) and not _FROZEN_WINDOW.search(clause)
                  for ticker, shares in _share_evidence(clause) if ticker.lstrip("$").upper() not in _EXCLUDED}
    if len(candidates) > 1:
        return _result("needs_input", message="Which single ticker and share count should I use for the proposed purchase?")
    if result["status"] == "ready" and not _range_is_supported(clauses, result["intent"]):
        return _result("unsupported", message=(
            "Current market research supports the latest quote and daily closes from the last 90 calendar days "
            "in the listing currency. Please confirm which of those views to use."
        ))
    return result


def _request_clauses(question):
    if not isinstance(question, str) or not question.strip() or len(question) > PROFILE_MAX_REQUEST_BYTES:
        return None
    try:
        if len(question.encode("utf-8")) > PROFILE_MAX_REQUEST_BYTES:
            return None
    except UnicodeEncodeError:
        return None
    return {f"clause_{number}": clause for number, clause in enumerate(
        dict.fromkeys(part.strip() for part in _CLAUSE_BREAK.split(question, maxsplit=39) if part.strip()), start=1
    )}


def local_live_market_intake(question: str) -> dict:
    """Interpret current-market inputs without invoking the model or fetching prices."""
    clauses = _request_clauses(question)
    if not clauses:
        return _result("needs_input")
    if prohibited := _prohibited_request(clauses.values()):
        return _result(prohibited)
    return _select_request(question, clauses.values())


async def interpret_live_market_request(question: str, runtime: StrandsAgents | None) -> dict:
    """Ask the first model to select a data scope, with bounded local recovery."""
    if runtime is None:
        return local_live_market_intake(question)
    clauses = _request_clauses(question)
    if not clauses:
        return _result("needs_input")
    if prohibited := _prohibited_request(clauses.values()):
        return _result(prohibited)

    selected = None
    accepted = False

    def select_market_lookup(intent: MarketIntent, scope: LookupScope, data_source: DataSource, source: str,
                             ticker: str = "", share_count: str = "") -> dict:
        """Select a read-only lookup using a clause as evidence for every input."""
        nonlocal accepted, selected
        if accepted:
            selected = None
            raise ValueError("Submit exactly one lookup decision.")
        if not all(type(value) is str for value in (intent, scope, data_source, source, ticker, share_count)) or source not in clauses:
            raise ValueError("Use a candidate clause ID and explicitly stated values.")
        selected = _ground(intent, scope, data_source, clauses[source], ticker, share_count)
        accepted = True
        return {"status": "ok"}

    tool = ToolSpec("select_market_lookup", select_market_lookup.__doc__, select_market_lookup,
                    trace_fields=(), completes_handoff=True)
    try:
        run, usage = await run_bounded(runtime.run(
            "live_market_intake", {"user_request": question, "candidate_clauses": clauses, "required_tool": tool.name},
            tools=(tool,), stop_after_tool=tool.name,
        ), _LIMITS)
    except RuntimeBudgetExceeded as exc:
        return {**_select_request(question, clauses.values()), "usage": exc.usage}

    verified = selected if run.status == "ok" and selected else None
    fallback = _select_request(question, clauses.values(), verified)
    safe = _result(fallback["status"], trace=run.trace, usage=usage)
    return {**fallback, "trace": safe["trace"], "usage": safe["usage"]}
