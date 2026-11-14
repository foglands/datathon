"""The controller holds unverified outcomes and transport limits apply across workers."""

import asyncio
import io
import json
import threading
import unittest
from unittest.mock import patch

from datathon.agents import StrandsAgents, ToolSpec
from datathon.runtime_budget import (
    PROFILE_MAX_REQUEST_BYTES, RuntimeBudgetExceeded, RuntimeLimits, current_budget, run_bounded, run_sync_action,
)


class RuntimeBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_workers_share_one_attempt_budget(self):
        async def operation():
            budget = current_budget()
            results = await asyncio.gather(*(asyncio.to_thread(budget.before_send) for _ in range(4)),
                                           return_exceptions=True)
            return results, budget

        (results, budget), usage = await run_bounded(operation(), RuntimeLimits(2, 2, 500))
        reasons = [item.reason for item in results if isinstance(item, RuntimeBudgetExceeded)]
        self.assertEqual(reasons, ["http_attempts"] * 2)
        self.assertEqual(usage["http_attempts_started"], 2)
        self.assertEqual(usage["limit_reached"], "http_attempts")
        self.assertIsNone(current_budget())
        with self.assertRaisesRegex(RuntimeBudgetExceeded, "action_closed"):
            budget.before_send()

    async def test_reported_token_threshold_stops_new_model_calls(self):
        async def operation():
            budget = current_budget()
            budget.before_send()
            budget.observe_response(retries=0, throttled=False, total_tokens=510)
            budget.before_send()

        with self.assertRaises(RuntimeBudgetExceeded) as caught:
            await run_bounded(operation(), RuntimeLimits(2, 4, 500))
        self.assertEqual(caught.exception.reason, "reported_tokens")
        self.assertEqual(caught.exception.usage["http_attempts_started"], 1)
        self.assertEqual(caught.exception.usage["reported_total_tokens"], 510)

    async def test_oversized_profile_stops_before_invocation(self):
        async def unexpected(*_):
            self.fail("An oversized request should not invoke a model.")

        result = await StrandsAgents(invoker=unexpected).run(
            "profile", {"user_request": "é" * (PROFILE_MAX_REQUEST_BYTES // 2 + 1)},
        )
        self.assertEqual(result.stop_reason, "input_too_large")
        self.assertNotIn("é", json.dumps(result.trace, ensure_ascii=False))

    async def test_timeout_has_no_output_after_cancelling_unverified_work(self):
        cancelled = asyncio.Event()

        async def operation():
            try:
                await asyncio.sleep(2)
            finally:
                cancelled.set()
            return {"status": "pass"}

        with self.assertRaises(RuntimeBudgetExceeded) as caught:
            await run_bounded(operation(), RuntimeLimits(.05, 4, 500))
        self.assertTrue(cancelled.is_set())
        self.assertEqual(caught.exception.reason, "deadline")
        self.assertIsNone(current_budget())


class SynchronousActionTests(unittest.TestCase):
    def test_closes_dispatch_without_waiting_for_running_transport(self):
        sent = threading.Event()
        can_finish = threading.Event()
        stopped = threading.Event()
        retries = []

        def transport(budget):
            budget.before_send()
            sent.set()
            can_finish.wait(timeout=2)
            try:
                budget.before_send()
            except RuntimeBudgetExceeded as exc:
                retries.append(exc.reason)
            stopped.set()

        async def operation():
            await asyncio.to_thread(transport, current_budget())

        try:
            with self.assertRaisesRegex(RuntimeBudgetExceeded, "deadline"):
                run_sync_action(run_bounded(operation(), RuntimeLimits(.1, 4, 500)))
            self.assertTrue(sent.is_set())
            self.assertFalse(stopped.is_set())
        finally:
            can_finish.set()
        self.assertTrue(stopped.wait(timeout=2))
        self.assertEqual(retries, ["action_closed"])


class BedrockTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_throttle_only_retries_once_and_respects_action_limit(self):
        try:
            import boto3
            from botocore.awsrequest import AWSResponse
            import strands.models.bedrock
        except ImportError:
            self.skipTest("The pinned Strands SDK is required for this offline adapter test.")

        session = boto3.Session(aws_access_key_id="test", aws_secret_access_key="test", region_name="us-east-1")

        class Raw(io.BytesIO):
            def stream(self, **_):
                yield self.read()

        def response(request, status, body, headers=None):
            return AWSResponse(request.url, status, headers or {}, Raw(json.dumps(body).encode()))

        def throttle(request):
            return response(request, 429, {"message": "busy"}, {"x-amzn-errortype": "ThrottlingException"})

        def success(request):
            return response(request, 200, {
                "output": {"message": {"role": "assistant", "content": [{
                    "toolUse": {"toolUseId": "local-injected", "name": "read_evidence", "input": {}},
                }]}},
                "stopReason": "tool_use",
                "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                "metrics": {"latencyMs": 1},
            }, {"x-amzn-requestid": "simulated-request-id"})

        def lookup() -> dict:
            return {"found": True}

        tool = ToolSpec("read_evidence", "Read test evidence", lookup, completes_handoff=True)
        for cap, response_2, attempted, expected in (
            (2, success, 2, "ok"),
            (2, throttle, 2, "error"),
            (1, success, 1, "error"),
        ):
            with self.subTest(cap=cap, expected=expected, second=response_2.__name__):
                reply = iter((throttle, response_2))
                with (patch("strands.models.bedrock.boto3.Session", return_value=session),
                      patch("botocore.httpsession.URLLib3Session.send",
                            side_effect=lambda request: next(reply)(request)) as send,
                      patch("botocore.endpoint.time.sleep", return_value=None)):
                    result, usage = await run_bounded(StrandsAgents().run(
                        "evidence", {"required_tool": tool.name}, tools=(tool,),
                    ), RuntimeLimits(5, cap, 500))
                self.assertEqual(send.call_count, attempted, result.trace)
                self.assertEqual(usage["http_attempts_started"], attempted)
                self.assertEqual(result.status, expected)
                if expected == "ok":
                    self.assertEqual(usage["reported_response_retries"], 1)
                    self.assertEqual(usage["reported_total_tokens"], 15)
                elif cap == 1:
                    self.assertEqual(usage["limit_reached"], "http_attempts")
                else:
                    self.assertEqual(usage["final_throttled_responses"], 1)
