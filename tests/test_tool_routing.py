"""Check routed AWS tool requests while keeping evidence and calculations in Python."""

import json
import unittest

from datathon.agents import AgentRun, StrandsAgents
from datathon.data import MarketData
from datathon.workflow import examples, preset_profile, run_case


DATES = ("2021-12-31", "2022-06-13", "2022-12-30", "2024-12-31", "2025-03-03", "2025-04-08")
PRICES = {
    ticker: dict(zip(DATES, closes))
    for ticker, closes in {
        "SPY": (100, 83, 87, 100, 99, 98),
        "XIU.TO": (100, 85, 87, 100, 99, 98),
        "QQQ": (100, 70, 75, 100, 98, 97),
        "ZST.TO": (100, 100, 100, 100, 100, 100),
        "NVDA": (100, 30, 74, 100, 95, 93),
    }.items()
}
MARKET = MarketData(PRICES, dict.fromkeys(DATES, 1.0))


def select_tool_arguments(role, payload):
    if role == "evidence":
        catalog = payload["catalog"]
        use_issuer = payload["policy"]["issuer_cap"] is not None
        return {
            "scope": "market_and_issuer" if use_issuer else "market_replay",
            "evidence_ids": catalog["market_evidence_ids"] + (catalog["issuer_evidence_ids"] if use_issuer else []),
            "holdings_as_of": catalog["holdings_as_of"] if use_issuer else "",
        }
    if role == "scenario":
        policy = payload["policy"]
        return {
            "metric": policy["metric"] if policy["loss_limit"] is not None else "comparison",
            "window_ids": payload["required_windows"],
        }
    return {}


class ToolRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, case, *, changes=None, omit_roles=(), false_tool_success=()):
        """Inject model choices, then execute the production handlers with those choices."""
        called_roles = []
        changes = changes or {}

        async def invoke(role, prompt, tools, record):
            called_roles.append(role)
            payload = json.loads(prompt.split("\n", 1)[1])
            for tool in tools:
                if role in false_tool_success:
                    record("tool", tool_name=tool.name, status="success")
                elif role not in omit_roles:
                    arguments = {**select_tool_arguments(role, payload), **changes.get(role, {})}
                    try:
                        result = tool.handler(**arguments)
                        status = result.get("status") if isinstance(result, dict) else None
                    except (TypeError, ValueError):
                        status = "rejected"
                    record("tool", tool_name=tool.name, input=arguments,
                           status="error" if status == "rejected" else "success")
            # Model commentary and claimed citations must not change the audit or its evidence.
            return {"status": "ok", "summary": "Invented claim: this proposal always passes.",
                    "evidence_ids": ["model:made-up-source"]}, "end_turn"

        profile = AgentRun("ok", preset_profile(case))
        report = await run_case(MARKET, case, StrandsAgents(invoker=invoke), confirmed_profile=profile)
        return report, called_roles

    def routing(self, report, role, status):
        matches = [
            event for event in report["trace"]
            if event["event"] == "tool_routing" and event["role"] == role and event["status"] == status
        ]
        self.assertTrue(matches, f"Missing {role} route with status {status}: {report.get('error', '')}")
        return matches[0]

    async def test_robert_selects_different_metric_calls_from_one_policy_change(self):
        terminal_case, drawdown_case = examples("robert")
        terminal, terminal_calls = await self.run_fixture(terminal_case)
        drawdown, drawdown_calls = await self.run_fixture(drawdown_case)
        self.assertEqual(drawdown["policy"], {**terminal["policy"], "metric": "max_drawdown"})
        for report, calls, metric in (
            (terminal, terminal_calls, "terminal_loss"),
            (drawdown, drawdown_calls, "max_drawdown"),
        ):
            self.assertNotIn("exposure", calls)
            scope = self.routing(report, "evidence", "accepted")["arguments"]
            self.assertEqual(scope["scope"], "market_replay")
            self.assertEqual(scope["holdings_as_of"], "")
            self.assertEqual(set(scope["evidence_ids"]), {"starter:prices_daily.csv", "starter:fx_usdcad_daily.csv"})
            scenario = self.routing(report, "scenario", "accepted")["arguments"]
            self.assertEqual(scenario, {"metric": metric, "window_ids": ["2022", "2025"]})
            self.assertTrue(any(event.get("event") == "tool" and event.get("tool_name") == "stress_replay"
                                and event.get("input") == scenario for event in report["trace"]))
            focus = report["scenario_focus"]["portfolios"]["proposal"]["2022"]
            self.assertEqual(report["scenario_focus"]["metric"], metric)
            other_metric = "max_drawdown" if metric == "terminal_loss" else "terminal_loss"
            self.assertIn(metric, focus)
            self.assertNotIn(other_metric, focus)
            self.assertIn(other_metric, report["audit"]["verified"]["proposal"]["windows"]["2022"])
            self.assertNotIn("model:made-up-source", report["evidence"]["evidence_ids"])
        self.assertEqual(terminal["alternatives"]["status"], "feasible_full")
        self.assertAlmostEqual(terminal["audit"]["verified"]["frontier"]["full_zst_max"], .044)
        self.assertEqual(drawdown["alternatives"]["status"], "no_feasible")
        self.assertTrue(drawdown["audit"]["verified"]["no_feasible_confirmed"])

    async def test_amira_routes_to_issuer_evidence_and_keeps_missing_qqq_unresolved(self):
        amira, missing_qqq = examples("amira", stress=True)
        complete, calls = await self.run_fixture(amira)
        missing, missing_calls = await self.run_fixture(missing_qqq)
        self.assertIn("exposure", calls)
        self.assertIn("exposure", missing_calls)
        evidence = self.routing(complete, "evidence", "accepted")["arguments"]
        self.assertEqual(evidence["scope"], "market_and_issuer")
        self.assertEqual(evidence["holdings_as_of"], "2026-06-30")
        self.assertIn("issuer:QQQ:2026-06-30", evidence["evidence_ids"])
        evidence = self.routing(missing, "evidence", "accepted")["arguments"]
        self.assertNotIn("issuer:QQQ:2026-06-30", evidence["evidence_ids"])
        scenario = self.routing(complete, "scenario", "accepted")["arguments"]
        self.assertEqual(scenario["metric"], "comparison")
        self.assertEqual(complete["status"], "fail")
        self.assertEqual(missing["status"], "insufficient_evidence")
        self.assertNotIn("maximum", missing["audit"]["verified"])
        self.assertEqual(set(missing["audit"]["verified"]["proposal"]["windows"]), {"2022", "2025"})

    async def test_invalid_dates_ids_and_scenario_scope_trigger_explicit_fallback(self):
        amira, = examples("amira")
        report, calls = await self.run_fixture(amira, changes={
            "evidence": {"holdings_as_of": "2024-01-01", "evidence_ids": ["model:made-up-source"]},
            "scenario": {"metric": "terminal_loss", "window_ids": ["2022"]},
        })
        for role, fields in (("evidence", {"holdings_as_of", "evidence_ids"}),
                             ("scenario", {"metric", "window_ids"})):
            rejected = self.routing(report, role, "rejected")
            self.assertTrue(fields.issubset(rejected["invalid_fields"]))
            self.assertTrue(any(event.get("event") == "tool" and event.get("role") == role
                                and event.get("status") == "error" and event.get("input") == {}
                                for event in report["trace"]))
            self.routing(report, role, "deterministic_fallback")
        self.assertIn("review", calls)
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("model:made-up-source", report["evidence"]["evidence_ids"])
        self.assertEqual(report["evidence"]["issuer_snapshot"]["as_of"], "2026-06-30")
        self.assertEqual(set(report["scenarios"]["proposal"]["windows"]), {"2022", "2025"})

    async def test_missing_routed_call_recovers_but_missing_review_withholds_decision(self):
        robert, _ = examples("robert")
        routed_fallback, calls = await self.run_fixture(robert, omit_roles={"scenario"})
        self.routing(routed_fallback, "scenario", "deterministic_fallback")
        self.assertIn("review", calls)
        self.assertEqual(routed_fallback["alternatives"]["status"], "feasible_full")

        invalid_review, calls = await self.run_fixture(robert, omit_roles={"review"})
        self.assertEqual(invalid_review["status"], "execution_error")
        self.assertNotIn("audit", invalid_review)
        self.assertNotIn("explanation", calls)

    async def test_success_status_without_actual_tool_callback_uses_explicit_fallback(self):
        robert, _ = examples("robert")
        report, calls = await self.run_fixture(robert, false_tool_success={"evidence", "scenario"})
        self.routing(report, "evidence", "deterministic_fallback")
        self.routing(report, "scenario", "deterministic_fallback")
        self.assertIn("review", calls)
        self.assertEqual(report["alternatives"]["status"], "feasible_full")

    async def test_issuer_evidence_cannot_be_selected_for_market_only_request(self):
        robert, _ = examples("robert")
        report, calls = await self.run_fixture(robert, changes={
            "evidence": {"scope": "market_and_issuer", "holdings_as_of": "2026-06-30",
                         "evidence_ids": ["issuer:QQQ:2026-06-30"]},
        })
        self.assertIn("scope", self.routing(report, "evidence", "rejected")["invalid_fields"])
        self.routing(report, "evidence", "deterministic_fallback")
        self.assertNotIn("exposure", calls)
        self.assertEqual(set(report["evidence"]["evidence_ids"]),
                         {"starter:prices_daily.csv", "starter:fx_usdcad_daily.csv"})

    async def test_independent_review_still_rejects_tampered_result(self):
        tampered = examples("robert", stress=True)[2]
        report, calls = await self.run_fixture(tampered)
        self.routing(report, "evidence", "accepted")
        self.routing(report, "scenario", "accepted")
        self.assertEqual(report["status"], "invalid")
        self.assertIn("review", calls)
        self.assertNotIn("explanation", calls)
        findings = {item["metric_id"]: item for item in report["audit"]["findings"]}
        self.assertEqual(findings["proposal.2022.terminal_loss"]["status"], "invalid")
