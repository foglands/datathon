"""Bound each confirmed action across its model calls and tool handoffs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextvars import ContextVar
from dataclasses import dataclass
from math import isfinite
from threading import Lock
from time import perf_counter
from typing import TypeVar


@dataclass(frozen=True)
class RuntimeLimits:
    timeout_seconds: float
    max_http_attempts: int
    observed_token_threshold: int

    def __post_init__(self):
        if (not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
                or type(self.max_http_attempts) is not int or self.max_http_attempts <= 0
                or type(self.observed_token_threshold) is not int or self.observed_token_threshold <= 0):
            raise ValueError("Runtime limits must be finite and positive.")


PROFILE_MAX_REQUEST_BYTES = 8000
PROFILE_LIMITS = RuntimeLimits(12, 6, 18000)
AUDIT_LIMITS = RuntimeLimits(18, 16, 45000)
CHALLENGE_LIMITS = RuntimeLimits(22, 18, 50000)


class RuntimeBudgetExceeded(RuntimeError):
    """A request exhausted its deadline or model-call budget."""

    def __init__(self, reason: str, usage: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.usage = usage


class RuntimeBudget:
    """A shared budget for parallel roles and the SDK's HTTP worker threads."""

    def __init__(self, limits: RuntimeLimits):
        self.limits = limits
        self.started = perf_counter()
        self._lock = Lock()
        self._closed = False
        self._http_attempts = 0
        self._responses = 0
        self._retries = 0
        self._throttles = 0
        self._reported_tokens = 0
        self._responses_with_usage = 0
        self._blocked = None

    def seconds_left(self) -> float:
        return max(0.0, self.limits.timeout_seconds - (perf_counter() - self.started))

    def check_deadline(self) -> None:
        if not self.seconds_left():
            raise RuntimeBudgetExceeded("deadline")

    def before_send(self, **_):
        """Count transport attempts before they leave, including SDK retries."""
        with self._lock:
            if self._closed:
                raise RuntimeBudgetExceeded("action_closed")
            for exceeded, reason in (
                (not self.seconds_left(), "deadline"),
                (self._http_attempts >= self.limits.max_http_attempts, "http_attempts"),
                (self._reported_tokens >= self.limits.observed_token_threshold, "reported_tokens"),
            ):
                if exceeded:
                    self._blocked = reason
                    raise RuntimeBudgetExceeded(reason)
            self._http_attempts += 1

    def observe_response(self, *, retries: int, throttled: bool, total_tokens: int | None):
        with self._lock:
            if self._closed:
                return
            self._responses += 1
            self._retries += retries
            self._throttles += throttled
            if total_tokens is not None:
                self._responses_with_usage += 1
                self._reported_tokens += total_tokens

    def finish(self, reason: str | None) -> dict:
        with self._lock:
            self._closed = True
            return {
                "elapsed_ms": round((perf_counter() - self.started) * 1000, 2),
                "deadline_ms": round(self.limits.timeout_seconds * 1000),
                "http_attempts_started": self._http_attempts,
                "http_attempt_limit": self.limits.max_http_attempts,
                "reported_response_retries": self._retries,
                "responses_observed": self._responses,
                "responses_with_usage": self._responses_with_usage,
                "final_throttled_responses": self._throttles,
                "reported_total_tokens": self._reported_tokens,
                "observed_token_threshold": self.limits.observed_token_threshold,
                "limit_reached": reason or self._blocked,
            }


_current_budget: ContextVar[RuntimeBudget | None] = ContextVar("runtime_budget", default=None)
_Result = TypeVar("_Result")


def current_budget() -> RuntimeBudget | None:
    return _current_budget.get()


async def run_bounded(operation: Awaitable[_Result], limits: RuntimeLimits) -> tuple[_Result, dict]:
    """Execute one action. Time spent waiting for human confirmation is outside the action."""
    budget = RuntimeBudget(limits)
    context = _current_budget.set(budget)
    try:
        output = await asyncio.wait_for(operation, timeout=budget.seconds_left())
        budget.check_deadline()
    except (asyncio.TimeoutError, RuntimeBudgetExceeded) as exc:
        reason = exc.reason if isinstance(exc, RuntimeBudgetExceeded) else "deadline"
        raise RuntimeBudgetExceeded(reason, budget.finish(reason)) from None
    except BaseException:
        budget.finish(None)
        raise
    else:
        return output, budget.finish(None)
    finally:
        _current_budget.reset(context)


def run_sync_action(operation: Awaitable[_Result]) -> _Result:
    """Return the held result without waiting for an already sent SDK request."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(operation)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        # asyncio.run() would also await the default executor, including an
        # in-flight Converse that cannot be cancelled at the provider. The
        # closed action budget keeps its worker from sending another request.
        loop.close()


async def bound_audit(operation: Awaitable[dict], case_id: str, *, live: bool) -> dict:
    """Return the usual audit report shape, with a held result on deadline expiry."""
    try:
        report, usage = await run_bounded(operation, AUDIT_LIMITS)
    except RuntimeBudgetExceeded as exc:
        usage = exc.usage
        report = {
            "case": case_id, "mode": "aws" if live else "offline",
            "status": "execution_error", "decision_reason": "runtime_budget_exhausted",
            "error": "The audit reached its execution budget before it could publish a checked result.",
            "agent_outputs": {}, "trace": [], "elapsed_ms": round(usage["elapsed_ms"]),
        }
    return {**report, "runtime_usage": usage}
