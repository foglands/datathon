"""Suggest one authorized application route for a fictional investor to confirm."""

from typing import Literal, get_args

from .agents import StrandsAgents, ToolSpec
from .runtime_budget import PROFILE_LIMITS, PROFILE_MAX_REQUEST_BYTES, RuntimeBudgetExceeded, run_bounded


TaskChoice = Literal["trade_audit", "compare_allocations", "unsupported"]
_ALLOWED_CHOICES = get_args(TaskChoice)
_TRACE_FIELDS = {
    "event", "role", "run_id", "model_id", "region", "tool_name", "status", "duration_ms", "operation",
    "request_id", "http_status", "retry_attempts", "throttled", "input_tokens", "output_tokens", "total_tokens",
}


def _result(status, *, task=None, trace=(), usage=None):
    return {
        "status": status,
        "task": task,
        "trace": [{key: value for key, value in event.items() if key in _TRACE_FIELDS} for event in trace],
        "usage": usage or {},
    }


async def suggest_intent(text: str, runtime: StrandsAgents | None) -> dict:
    """Bound model-assisted routing and expose only a checked, editable task suggestion."""
    if not isinstance(text, str) or not (request := text.strip()):
        return _result("needs_input")
    if len(request) > PROFILE_MAX_REQUEST_BYTES or len(request.encode("utf-8")) > PROFILE_MAX_REQUEST_BYTES:
        return _result("needs_input")
    if runtime is None:
        return _result("unavailable")

    choice = None
    rejected = False

    def select_investment_task(task: TaskChoice) -> dict:
        """Propose exactly one application task for the user to confirm."""
        nonlocal choice, rejected
        if task not in _ALLOWED_CHOICES or choice is not None:
            rejected = True
            raise ValueError("Select exactly one supported task.")
        choice = task
        return {"task": task}

    tool = ToolSpec("select_investment_task", select_investment_task.__doc__, select_investment_task,
                    trace_fields=("task",), completes_handoff=True)
    try:
        run, usage = await run_bounded(runtime.run(
            "assistant_intent", {"user_request": request, "required_tool": tool.name}, tools=(tool,),
            stop_after_tool=tool.name,
        ), PROFILE_LIMITS)
    except RuntimeBudgetExceeded as exc:
        return _result("unavailable", usage=exc.usage)

    if run.status != "ok" or rejected or choice is None:
        return _result("unavailable", trace=run.trace, usage=usage)
    if choice == "unsupported":
        return _result("unsupported", trace=run.trace, usage=usage)
    return _result("proposed", task=choice, trace=run.trace, usage=usage)
