"""Choose an evidence-backed conclusion for a simulated share purchase."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .agents import StrandsAgents, ToolSpec
from .runtime_budget import RuntimeBudgetExceeded, RuntimeLimits, run_bounded
from .semantic_intake import _TRACE_FIELDS

if TYPE_CHECKING:
    from .live_market_analysis import SharePurchaseAnalysis


_ROLE = "live_market_summary"
_LIMITS = RuntimeLimits(timeout_seconds=12, max_http_attempts=2, observed_token_threshold=12000)
Emphasis = Literal["purchase_cost", "quote_timing", "historical_risk"]
NextInput = Literal["none", "execution_price", "share_count", "portfolio_context"]
_NEXT_INPUT = {
    "none": "",
    "execution_price": "An execution-cost estimate also needs an assumed fill price and applicable transaction fees.",
    "share_count": "An indicative purchase cost needs a proposed share count.",
    "portfolio_context": "Assessing concentration requires the current portfolio value, existing position, and funding source.",
}


def _result(status, *, emphasis=None, next_input=None, conclusion=None, trace=(), usage=None, stop_reason=None):
    return {
        "status": status,
        "emphasis": emphasis,
        "next_input": next_input,
        "conclusion": conclusion,
        "trace": [{key: value for key, value in event.items()
                   if key in _TRACE_FIELDS and type(value) in (str, bool, int, float, type(None))} for event in trace],
        "usage": usage or {},
        "stop_reason": stop_reason,
    }


def _conclusion(report: SharePurchaseAnalysis, emphasis: Emphasis, next_input: NextInput) -> str:
    quote = report.quote
    if emphasis == "purchase_cost":
        interpretation = (
            f"At the available {report.ticker} trade price of {quote.currency} {quote.price:,f}, "
            f"the proposed {report.shares:,f} shares represent {quote.currency} {report.indicative_notional:,f} before fees."
        )
    elif emphasis == "quote_timing":
        interpretation = (
            f"The available {report.ticker} trade was {quote.currency} {quote.price:,f} at {quote.as_of.isoformat()} "
            f"on the {quote.source} {quote.feed} feed."
        )
    else:
        trailing = report.trailing
        interpretation = (
            f"From {trailing.start.isoformat()} through {trailing.end.isoformat()}, "
            f"{report.ticker} had a price return of {trailing.price_return:.2%} and a peak-to-trough "
            f"drawdown of {trailing.max_drawdown:.2%} using daily closes. "
            "Future drawdowns may differ from this observed sample."
        )
    return f"{interpretation} {_NEXT_INPUT[next_input]}".strip()


async def summarize_live_market(
    report: SharePurchaseAnalysis | None, runtime: StrandsAgents | None,
) -> dict:
    """Let Bedrock select an interpretation using the checked market report alone."""
    if report is None:
        return _result("not_run", stop_reason="no_verified_evidence")
    if runtime is None:
        return _result("not_run", stop_reason="runtime_not_configured")

    allowed_emphases = ("quote_timing",)
    if report.indicative_notional is not None:
        allowed_emphases += ("purchase_cost",)
    if report.trailing is not None:
        allowed_emphases += ("historical_risk",)
    follow_up = "share_count" if report.shares is None else "execution_price"
    allowed_next_inputs = {key: _NEXT_INPUT[key] for key in ("none", follow_up, "portfolio_context")}
    selection = None
    accepted = False

    def select_market_summary(emphasis: Emphasis, next_input: NextInput) -> dict:
        """Select one supported finding and one question the evidence cannot settle."""
        nonlocal selection, accepted
        if accepted:
            selection = None
            raise ValueError("Submit one market conclusion.")
        if (type(emphasis) is not str or emphasis not in allowed_emphases
                or type(next_input) is not str or next_input not in allowed_next_inputs):
            raise ValueError("Choose a finding and next input supported by the market evidence.")
        selection = emphasis, next_input
        accepted = True
        return {"status": "ok", "emphasis": emphasis, "next_input": next_input}

    tool = ToolSpec("select_market_summary", select_market_summary.__doc__, select_market_summary,
                    trace_fields=(), completes_handoff=True)
    payload = {
        "verified_market_evidence": report.as_model_evidence(),
        "allowed_emphases": allowed_emphases,
        "allowed_next_inputs": allowed_next_inputs,
        "required_tool": tool.name,
    }
    try:
        run, usage = await run_bounded(runtime.run(_ROLE, payload, tools=(tool,), stop_after_tool=tool.name), _LIMITS)
    except RuntimeBudgetExceeded as exc:
        return _result("unavailable", usage=exc.usage, stop_reason=exc.reason)

    if run.status != "ok" or selection is None:
        return _result("unavailable", trace=run.trace, usage=usage, stop_reason=run.stop_reason)
    emphasis, next_input = selection
    return _result("ready", emphasis=emphasis, next_input=next_input, trace=run.trace, usage=usage,
                   conclusion=_conclusion(report, emphasis, next_input), stop_reason=run.stop_reason)
