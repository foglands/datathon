"""Classify investment questions with a bounded tool and source-linked hints."""

import re
from typing import Literal, get_args

from .agents import StrandsAgents, ToolSpec
from .planning_request import _OTHER_PERSON, planning_context
from .runtime_budget import PROFILE_MAX_REQUEST_BYTES, RuntimeBudgetExceeded, RuntimeLimits, run_bounded


TaskChoice = Literal["planning", "analyze_allocation", "compare_allocations", "trade_audit", "unsupported"]
PlanningPoint = Literal["cash_position", "spending", "inflation", "growth", "risk", "timing", "beginner",
                        "concentration", "peer_trading", "return_claim"]
InstrumentChoice = Literal["sp500", "gold", "cash_deposits", "bonds", "equity_funds", "individual_stock", "crypto", "options"]
_TASK_CHOICES = frozenset(get_args(TaskChoice))
_POINT_CHOICES = frozenset(get_args(PlanningPoint))
_INSTRUMENT_CHOICES = frozenset(get_args(InstrumentChoice))
_CLAUSE_BREAK = re.compile(r"\n+|(?<=[.!?;])\s+|(?<=[。！？；])")
_MAX_CLAUSES = 40
_FIRST_PERSON = re.compile(r"\b(?:I|we|my|our|je|moi|mon|ma|mes|notre|nos|nous)\b|\bj['’]|我", re.I)
_ENGLISH_THIRD_PERSON = re.compile(r"\b(?:he|she|they|his|her|their)\b|\b(?:my|our)\s+(?:cousins?|roommates?)\b", re.I)
_FRENCH_THIRD_PERSON = re.compile(r"\b(?:mon|ma|mes|notre|nos|un|une)\s+(?:ami(?:e)?s?|coll[eè]gues?|voisin(?:e)?s?|"
                                 r"frères?|s[œo]urs?|parents?|père|mère)\b|^(?:il|elle|ils|elles)\b", re.I)
_PERSONAL_TOPICS = frozenset({"cash_position", "spending", "growth", "risk", "timing", "beginner"})
_REPORTED_TOPICS = frozenset({"peer_trading", "return_claim"})
_RISK_DENIAL = re.compile(
    r"\b(?:not|never|no)\s+(?:(?:really|particularly|very|at all|a)\s+)?"
    r"(?:afraid|scared|terrified|worried|concern(?:ed)?|anxious|fear|problem)\b"
    r"|\b(?:(?:don['’]t|do not|never)\s+(?:mind|fear|worry)|(?:doesn['’]t|does not)\s+(?:bother|worry)\s+(?:me|us))\b"
    r"|\b(?:fine|comfortable)\s+with\b|\b(?:pas|jamais)\s+(?:peur|inquiet(?:s|es?)?|pr[ée]occup[ée]e?)\b"
    r"|(?:不|并不|並不)(?:担心|擔心|介意|怕|害怕)", re.I,
)
_LIMITS = RuntimeLimits(timeout_seconds=12, max_http_attempts=1, observed_token_threshold=18000)
_TRACE_FIELDS = frozenset({
    "event", "role", "run_id", "status", "tool_name", "model_id", "region", "operation", "request_id", "http_status", "error_type", "stop_reason",
    "retry_attempts", "duration_ms", "throttled", "input_tokens", "output_tokens", "total_tokens", "error_code",
})


def _result(status, *, task=None, plan=None, trace=(), usage=None):
    return {
        "status": status,
        "task": task,
        "plan": plan,
        "trace": [{key: value for key, value in event.items()
                   if key in _TRACE_FIELDS and type(value) in (str, bool, int, float, type(None))} for event in trace],
        "usage": usage or {},
    }


def _source_clauses(kind, tags, allowed, clauses):
    if tags is None:
        return {}
    if type(tags) is not dict or not tags.keys() <= allowed:
        raise ValueError(f"Invalid {kind} tag.")
    if not all(type(source) is str and source in clauses for source in tags.values()):
        raise ValueError(f"Invalid {kind} source.")
    return {tag: clauses[source] for tag, source in tags.items()}


def _has_usable_topic_source(topic, clause, local_points):
    if topic in _REPORTED_TOPICS:
        return True
    if _OTHER_PERSON.search(clause) or _ENGLISH_THIRD_PERSON.search(clause) or _FRENCH_THIRD_PERSON.search(clause):
        return False
    if topic in _PERSONAL_TOPICS and not _FIRST_PERSON.search(clause):
        return False
    if topic == "cash_position":
        return topic in local_points and topic in planning_context(clause)["points"]
    return topic != "risk" or not _RISK_DENIAL.search(clause)


async def interpret_semantic_request(question: str, runtime: StrandsAgents | None) -> dict:
    """Identify a task and non-executable planning hints from the intact question."""
    if not isinstance(question, str) or not question.strip() or len(question) > PROFILE_MAX_REQUEST_BYTES:
        return _result("needs_input")
    try:
        request_bytes = question.encode("utf-8")
    except UnicodeEncodeError:
        return _result("needs_input")
    if len(request_bytes) > PROFILE_MAX_REQUEST_BYTES:
        return _result("needs_input")
    if runtime is None:
        return _result("unavailable")

    excerpts = dict.fromkeys(part.strip() for part in _CLAUSE_BREAK.split(question, maxsplit=_MAX_CLAUSES - 1) if part.strip())
    clauses = {f"clause_{index}": clause for index, clause in enumerate(excerpts, start=1)}
    selected = None
    called = False

    def classify_investment_question(
        task: TaskChoice, task_source: str,
        points: dict[PlanningPoint, str] | None = None, instruments: dict[InstrumentChoice, str] | None = None,
    ) -> dict:
        """Choose a task and map optional planning labels to exact candidate clause IDs."""
        nonlocal selected, called
        if called:
            selected = None
            raise ValueError("Submit exactly one task classification.")
        called = True
        if type(task) is not str or task not in _TASK_CHOICES or type(task_source) is not str or task_source not in clauses:
            raise ValueError("Choose one supported task with a supplied source clause.")
        if task != "planning" and (points or instruments):
            raise ValueError("Only planning accepts topic and instrument hints.")

        plan = None
        if task == "planning":
            context = planning_context(question)
            topic_sources = {
                topic: clause for topic, clause in _source_clauses("topic", points, _POINT_CHOICES, clauses).items()
                if _has_usable_topic_source(topic, clause, context["points"])
            }
            instrument_sources = {
                category: clause
                for category, clause in _source_clauses("instrument", instruments, _INSTRUMENT_CHOICES, clauses).items()
                if category in context["instruments"] and category in planning_context(clause)["instruments"]
            }
            plan = {"points": topic_sources, "instruments": tuple(instrument_sources),
                    "instrument_sources": instrument_sources, "examples": ()}
        selected = task, plan
        return {"status": "ok", "task": task}

    tool = ToolSpec("classify_investment_question", classify_investment_question.__doc__, classify_investment_question,
                    trace_fields=(), completes_handoff=True)
    try:
        run, usage = await run_bounded(runtime.run(
            "semantic_intake", {"user_request": question, "candidate_clauses": clauses, "required_tool": tool.name},
            tools=(tool,), stop_after_tool=tool.name,
        ), _LIMITS)
    except RuntimeBudgetExceeded as exc:
        return _result("unavailable", usage=exc.usage)

    if run.status != "ok" or selected is None:
        return _result("unavailable", trace=run.trace, usage=usage)
    task, plan = selected
    return _result("ready", task=task, plan=plan, trace=run.trace, usage=usage)
