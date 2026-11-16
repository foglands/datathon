"""Observable task contracts and evidence scope; no investment verdict rules."""

from copy import deepcopy
from dataclasses import dataclass, asdict
from time import monotonic
import re
from typing import Literal
from typing_extensions import TypedDict, NotRequired


@dataclass(frozen=True)
class InquiryLimits:
    seconds: float = 240
    model_calls: int = 10
    tool_calls: int = 8
    source_calls: int = 12
    investigations: int = 3
    format_repairs: int = 2
    reviews: int = 2

    def __post_init__(self):
        if any(type(v) not in (int, float) or not 0 < v < 10000 for v in asdict(self).values()):
            raise ValueError("Inquiry budgets must be positive and bounded.")
        if any(type(value) is not int for key, value in asdict(self).items() if key != "seconds"):
            raise ValueError("Call and retry budgets must be integers.")


class InquiryBudget:
    def __init__(self, limits=None, clock=monotonic):
        self.limits, self.clock = limits or InquiryLimits(), clock
        self.started = clock()
        self.model_calls = self.tool_calls = self.source_calls = 0
        self.stop_reason = None
        self.usage = []

    def remaining(self):
        return max(0, self.limits.seconds - (self.clock() - self.started))

    def take(self, kind):
        if self.remaining() <= 0:
            self.stop_reason = "time_budget"
            return False
        limit = getattr(self.limits, kind)
        if getattr(self, kind) >= limit:
            self.stop_reason = kind + "_budget"
            return False
        setattr(self, kind, getattr(self, kind) + 1)
        return True

    def snapshot(self):
        return {"limits": asdict(self.limits), "elapsed_seconds": round(self.clock() - self.started, 3),
                "model_calls": self.model_calls, "tool_calls": self.tool_calls, "source_calls": self.source_calls,
                "stop_reason": self.stop_reason,
                "reported_tokens": sum(row.get("reported_total_tokens", 0) for row in self.usage),
                "monetary_cost": None, "cost_note": "Token usage where returned; no assumed token price."}


class Task(TypedDict):
    tool: str
    question: str
    context_ids: list[str]
    relevance: str
    required_inputs: list[str]
    required_outputs: list[str]
    required_measures: list[str]
    scope: Literal["asset", "product_comparison", "portfolio", "client_context"]
    completion_condition: str
    horizon_excerpt: NotRequired[str]


_MEASURES = {
    "historical_market": ["return", "drawdown", "volatility", "rolling_returns", "recovery", "stress"],
    "product_comparison": ["return", "drawdown", "period", "currency"],
    "horizon_window": ["window_count", "worst", "best", "period"],
    "cash_needs": ["withdrawals", "shortfall", "remaining_assets"],
    "purchasing_power": ["nominal_return", "real_return", "cpi_change", "period"],
    "market_liquidity": ["volume_ratio"], "interest_rate": ["duration", "rate_shock"],
    "credit": ["rating_buckets", "unknown_coverage"], "concentration": ["exposure_bounds", "unknown_coverage"],
    "controversy": ["screening_bounds", "unknown_coverage"], "tail_loss": ["var", "expected_shortfall"],
    "portfolio_context": ["missing_inputs"], "verify_calculations": ["arithmetic_check", "window_count_check"],
}

_SPECS = {
    "verify_calculations": (["existing price rows and verified calculations"], ["calculation_verification"], ["client_context"], "Independently recheck arithmetic and window counts; does not establish an investment conclusion."),
    "historical_market": (["verified adjusted prices"], ["historical_metrics"], ["asset"], "Observed single-asset history only; no portfolio effects, forecasts or suitability."),
    "product_comparison": (["at least two resolved products", "common dates, currency and price adjustment"], ["aligned_comparison"], ["product_comparison"], "Compare observed metrics on a shared basis; not holdings, valuation or future performance."),
    "horizon_window": (["one explicit duration", "sufficient price history"], ["holding_period_outcomes"], ["asset"], "Overlapping historical windows; no forecast. Insufficient coverage is a gap, not a completed horizon assessment."),
    "cash_needs": (["budget", "withdrawal amount/currency/timing/frequency"], ["withdrawal_replay"], ["asset"], "One historical starting path with fractional-unit sales; no cross-start shortfall frequency/distribution or future success probability."),
    "purchasing_power": (["CAD price history", "official CPI"], ["real_return"], ["asset"], "CPI-aligned reference months, latest vintage; not a forward inflation forecast."),
    "market_liquidity": (["transaction amount and currency", "close and volume"], ["volume_proxy"], ["asset"], "No spreads, depth, market impact or execution guarantee."),
    "interest_rate": (["qualified dated duration disclosure"], ["duration_scenario"], ["asset"], "First-order parallel shock, not a prediction; cannot substitute historical volatility."),
    "credit": (["qualified dated issuer rating distribution"], ["credit_buckets"], ["asset"], "Disclosed buckets; unknown and unrated remain unknown."),
    "concentration": (["complete weights", "qualified look-through disclosures"], ["exposure_bounds"], ["portfolio"], "Coverage-limited bounds; no inferred fund holdings."),
    "controversy": (["explicit screening policy", "qualified dated list"], ["screening_bounds"], ["portfolio"], "A named screening list only, not ESG certification."),
    "tail_loss": (["certified complete exchange sessions"], ["tail_estimate"], ["asset"], "Withheld without coverage certification; not a future maximum."),
    "portfolio_context": (["explicit before/after holdings and weights"], ["portfolio_input_check"], ["client_context"], "Checks missing inputs only. Does NOT compute a before/after portfolio comparison."),
}


def tool_catalog():
    return deepcopy({key: {"inputs": inp, "outputs": out, "scope": scope, "measures": _MEASURES[key], "limitations": limit}
                     for key, (inp, out, scope, limit) in _SPECS.items()})


def validate_tasks(tasks, context, maximum=4):
    if not isinstance(tasks, list) or len(tasks) > maximum:
        raise ValueError("Choose a bounded number of analysis tasks.")
    for task in tasks:
        if task["tool"] not in _SPECS or task["scope"] not in {"asset", "portfolio", "product_comparison", "client_context"}:
            raise ValueError("Use a catalog tool and a declared analysis scope.")
        for field in ("question", "relevance", "completion_condition"):
            if not isinstance(task[field], str) or not 10 <= len(task[field]) <= 600:
                raise ValueError("Each task needs a question, relevance and observable completion condition.")
        if not task["context_ids"] or any(key not in context for key in task["context_ids"]):
            raise ValueError("Use known context_ids only: " + ", ".join(context) + "; received: " + repr(task["context_ids"]))
        for field in ("required_inputs", "required_outputs", "required_measures"):
            if not isinstance(task[field], list) or not task[field] or len(task[field]) > 8 or any(not isinstance(x, str) or not x.strip() or len(x) > 160 for x in task[field]):
                raise ValueError("Name the required inputs and observable outputs.")
        if task["tool"] != "horizon_window":
            # Some structured-output providers fill optional fields on every task.
            # A horizon is not an input to these tools and must not alter their cache key.
            task.pop("horizon_excerpt", None)
        elif task.get("horizon_excerpt") and not any(task["horizon_excerpt"] in value for value in context.values()):
            raise ValueError(f"horizon_excerpt {task['horizon_excerpt']!r} must be an exact quotation from user_context; do not convert years to months or add words.")


def record_task(report, task, outcome):
    """Tool success is only evidence availability, never semantic task completion."""
    spec = tool_catalog()[task["tool"]]
    available = set(outcome.get("produced_outputs", []))
    missing = [key for key in task["required_outputs"] if key not in available]
    missing += ["measure:" + key for key in task["required_measures"] if key not in outcome.get("produced_measures", [])]
    # Check common explicit statistical requests in the prose too. The model must
    # not omit a desired statistic from required_measures and still call it done.
    request = task["question"] + " " + task["completion_condition"]
    statistics = {"median": r"\bmedian\b", "percentiles": r"\b(?:percentiles?|quantiles?)\b",
        "distribution": r"\bdistribution\b", "shortfall_frequency": r"\bshortfall (?:frequency|probability)\b|\b(?:frequency|probability) of (?:a )?shortfall\b"}
    for measure, pattern in statistics.items():
        if re.search(pattern, request, re.I) and measure not in outcome.get("produced_measures", []):
            missing.append("measure:" + measure)
    missing = list(dict.fromkeys(missing))
    scope_ok = task["scope"] in spec["scope"]
    row = {**deepcopy(task), "id": "task." + str(len(report.setdefault("tasks", []))),
           "evidence_ids": outcome.get("evidence_ids", []), "actual_result": outcome.get("outcome", "No result."),
           "missing_outputs": missing, "scope_supported": scope_ok,
           "status": "evidence_ready" if not missing and scope_ok else "blocked",
           "remaining_gap": "" if not missing and scope_ok else "Required outputs or scope were not established by this tool.",
           "completion_review": "pending"}
    report["tasks"].append(row)
    return row


def attach_evidence_scope(report):
    """Keep metadata with evidence; never assign whole-portfolio scope to asset facts."""
    assets = {item["asset"]["symbol"]: item for item in report["analyses"]}
    for key, block in report["blocks"].items():
        if "scope" in block:
            continue
        symbol = key.split(".")[0]
        item = assets.get(symbol)
        block["scope"] = {"objects": [symbol] if item else [],
            "level": "asset" if item else "limited_check",
            "currency": item["basis"] if item else None,
            "price_basis": item["asset"].get("price_basis") if item else None,
            "start": item["metrics"]["start"] if item and not key.endswith((".budget", ".stale")) else None,
            "end": item["metrics"]["end"] if item and not key.endswith((".budget", ".stale")) else None,
            "as_of": item["asset"]["price_as_of"] if item else None,
            "recorded_at": report["created_at"],
            "coverage": "observed adjusted-price rows; exchange completeness not certified" if item else "See the tool-specific result; do not inherit another block's period.",
            "method": ("current observed quote and explicit budget; whole shares before fees" if key.endswith(".budget") else "verified buy-and-hold replay") if item else "tool-specific evidence text",
            "sources": block.get("sources", [])}


def fact_registry(report):
    """Scoped quotations are generated by Python, not assembled numerically by a model."""
    facts = {}
    for item in report["analyses"]:
        symbol, metrics, basis = item["asset"]["symbol"], item["metrics"], item["basis"]
        for metric, label in (("return", "adjusted-price change"), ("drawdown", "largest observed peak-to-trough fall")):
            key = symbol + "." + metric
            facts[key] = {"evidence_id": symbol + ".behavior", "object": symbol, "metric": metric,
                "definition": label, "value": metrics[metric], "unit": "fraction", "currency": basis,
                "start": metrics["start"], "end": metrics["end"], "method": "independently checked buy-and-hold replay",
                "text": f"{symbol}: {label} {format(metrics[metric], '+.2%' if metric == 'return' else '.2%')} ({basis}; {metrics['start']} to {metrics['end']})"}
    # Every evidence ID is also a usable quotation key. Keep compact metric keys
    # above, but do not make callers invent a different key for a known block.
    for key, block in report["blocks"].items():
        facts[key] = {"evidence_id": key, "text": block["text"], "scope": block.get("scope", {}),
                      "method": "complete checked evidence quotation"}
    return facts
