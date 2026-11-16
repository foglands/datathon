"""Adversarial task/evidence/state cases, with code-authored expectations."""
from copy import deepcopy
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import Mock, AsyncMock, patch

from datathon.agents import AgentRun
from datathon.customer_data import PublicResearch, ResearchAmbiguous
from datathon.customer_state import apply_turn
from datathon.customer_agents import understand
from datathon.customer_profile import build_profile
from datathon.customer_report import analyze
from datathon.customer_workflow import research_question
from datathon.customer_tools import execute_checks
from datathon.inquiry_engine import validate_claims, review_claims
from datathon.inquiry_contracts import InquiryBudget, InquiryLimits, attach_evidence_scope
from tests.test_customer_reasoning import task, claims, audit
from tests.test_customer_research import asset, fx, plan, NOW


def report(items=None):
    from datathon.customer_report import evidence_blocks
    p = plan()
    analyses = analyze(items or [asset("VTI")], None)
    blocks, _ = evidence_blocks(p, analyses, [])
    result = {"plan": p, "profile": build_profile(p), "analyses": analyses, "blocks": blocks,
        "executed_tools": [], "tool_outcomes": [], "risks": [], "cpi": None, "created_at": NOW.isoformat(), "tasks": []}
    attach_evidence_scope(result)
    return result


class TaskAndSupportTests(IsolatedAsyncioTestCase):
    def test_prose_statistics_cannot_bypass_the_completion_contract(self):
        from datathon.inquiry_contracts import record_task
        r = report(); check = task("cash_needs", "Calculate the shortfall frequency and magnitude across starting dates.")
        outcome = {"produced_outputs": ["withdrawal_replay"], "produced_measures": ["withdrawals", "shortfall", "remaining_assets"], "evidence_ids": ["risk.cash_needs"]}
        row = record_task(r, check, outcome)
        self.assertEqual(row["status"], "blocked")
        self.assertIn("measure:shortfall_frequency", row["missing_outputs"])

    def test_argument_metadata_cannot_introduce_model_calculations(self):
        r = report(); claim = claims(evidence="VTI.behavior")[0]
        claim["relevance"] = "This would leave an unverified balance of 8934.27 USD."
        with self.assertRaises(ValueError):
            validate_claims([claim], r, {"user.request": "Review the fund."})

    async def test_conditional_support_that_requires_repair_is_not_accepted(self):
        r = report(); runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            tools[0].handler(claim_reviews=[{"claim_id": "c", "status": "conditional", "evidence_ids": ["VTI.behavior"],
                "defect": "scope_expansion", "severity": "conclusion", "reason": "Narrow the conclusion to the observed path.", "repair": "narrow"}],
                task_reviews=[], answers_question=True, requested_scope_complete=False,
                remaining_user_requests=["Repair the conclusion."], feedback="A conditional classification is not approval to publish this claim.")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await review_claims({}, [{"id": "c"}], r, runtime, InquiryBudget())
        self.assertFalse(result["accepted"])

    async def test_repeated_old_facts_are_carried_forward_without_new_source_attribution(self):
        original = plan(conditions=[{"kind": "goal", "excerpt": "for tuition"}, {"kind": "horizon", "excerpt": "2 years"}])
        original["assets"] = [{"query": "VTI", "excerpt": "VTI", "role": "consider"}]
        original["budget"] = {"amount": 3000., "currency": "USD", "excerpt": "3000 USD"}
        previous = apply_turn(None, original, "VTI for tuition in 2 years with 3000 USD")["conversation_state"]
        target = next(c["id"] for c in previous["statements"] if c["kind"] == "horizon")
        runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            tools[0].handler(mode="research", assets=previous["assets"],
                conditions=[{"kind": "goal", "excerpt": "for tuition"}, {"kind": "horizon", "excerpt": "3 months", "operation": "replace", "targets": [target]}],
                budget_text="3000", currency="USD", budget_excerpt="3000 USD", question_to_ask="")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await understand("Actually 3 months", runtime, previous_state=previous)
        self.assertEqual(result["origin"], "bedrock")
        self.assertEqual(result["assets"], previous["assets"])
        self.assertEqual(result["budget"], previous["budget"])
        goals = [c for c in result["conditions"] if c["kind"] == "goal"]
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["turn"], 1)

    async def test_invalid_state_update_does_not_poison_repaired_handoff(self):
        previous = apply_turn(None, plan(conditions=[{"kind": "horizon", "excerpt": "2 years"}]), "2 years")["conversation_state"]
        target = previous["statements"][0]["id"]
        runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            args = {"mode": "research", "assets": [], "conditions": [{"kind": "horizon", "excerpt": "3 months", "operation": "replace", "targets": ["wrong"]}],
                "budget_text": "", "currency": "", "budget_excerpt": "", "question_to_ask": ""}
            with self.assertRaises(ValueError): tools[0].handler(**args)
            args["conditions"][0]["targets"] = [target]
            tools[0].handler(**args)
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await understand("Actually 3 months", runtime, previous_state=previous)
        self.assertEqual(result["origin"], "bedrock")
        self.assertEqual([c["excerpt"] for c in result["conditions"]], ["3 months"])

    def test_volume_proxy_does_not_establish_execution_feasibility(self):
        r = report(); r["blocks"]["risk.market_liquidity"] = {"text": "Volume ratio is 0.01%; no spread or impact evidence.", "sources": []}
        claim = claims(evidence="risk.market_liquidity")[0]
        for text in ("The measured volume ratio indicates execution feasibility.",
                     "The volume proxy suggests low execution friction.",
                     "The amount implies negligible price impact."):
            claim["text"] = text
            with self.assertRaisesRegex(ValueError, "metric_substitution"):
                validate_claims([claim], r, {"user.request": "Review the fund."})
        claim["text"] = "The measured volume ratio cannot establish execution feasibility."
        self.assertEqual(len(validate_claims([claim], r, {"user.request": "Review the fund."})), 1)

    def test_optional_horizon_is_only_applied_to_its_supported_tool(self):
        from datathon.inquiry_contracts import validate_tasks
        check = task("historical_market", "Review the historical behavior relevant to this request.")
        check["horizon_excerpt"] = "3 years"
        validate_tasks([check], {"user.request": "for 3 years"})
        self.assertNotIn("horizon_excerpt", check)
        check = task("horizon_window", "Review the stated holding period.")
        check["horizon_excerpt"] = "36 months"
        with self.assertRaisesRegex(ValueError, "exact quotation"):
            validate_tasks([check], {"user.request": "for 3 years"})

    async def test_successful_asset_tool_cannot_complete_portfolio_comparison(self):
        r = report()
        await execute_checks(r, [task("historical_market", "How does the proposed change affect the whole portfolio?", "portfolio_comparison", "portfolio")], Mock(), None)
        self.assertTrue(r["tool_outcomes"][0]["evidence_ids"])
        self.assertEqual(r["tasks"][0]["status"], "blocked")
        self.assertIn("portfolio_comparison", r["tasks"][0]["missing_outputs"])
        runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            with self.assertRaisesRegex(ValueError, "cannot be complete"):
                tools[0].handler(claim_reviews=[{"claim_id": "c", "status": "supported", "evidence_ids": ["VTI.behavior"],
                    "defect": "none", "severity": "local", "reason": "Actual fact.", "repair": "none"}],
                    task_reviews=[{"task_id": "task.0", "status": "complete", "reason": "Tool returned data."}], answers_question=True, requested_scope_complete=True, remaining_user_requests=[], feedback="Done")
            return AgentRun("error", {})
        runtime.run.side_effect = run
        reviewed = await review_claims({}, [{"id": "c"}], r, runtime, InquiryBudget())
        self.assertFalse(reviewed["accepted"])

    async def test_same_tool_is_cached_but_new_task_scope_is_checked(self):
        r = report(); budget = InquiryBudget()
        await execute_checks(r, [task("historical_market", "Describe the observed historical changes.")], Mock(), None, budget)
        await execute_checks(r, [task("historical_market", "Establish the portfolio impact of this change.", "portfolio_comparison", "portfolio")], Mock(), None, budget)
        self.assertEqual(budget.tool_calls, 1)
        self.assertEqual(len(r["tasks"]), 2)
        self.assertEqual(r["tasks"][0]["status"], "evidence_ready")
        self.assertEqual(r["tasks"][1]["status"], "blocked")

    async def test_returned_range_does_not_complete_a_requested_percentile(self):
        r = report(); r["profile"] = build_profile(plan(conditions=[{"kind": "horizon", "excerpt": "1 month"}]))
        check = task("horizon_window", "Establish both the range and the median holding-period result.")
        check["required_measures"].append("median")
        await execute_checks(r, [check], Mock(), None)
        self.assertEqual(r["tasks"][0]["status"], "blocked")
        self.assertIn("measure:median", r["tasks"][0]["missing_outputs"])

    def test_overlapping_daily_window_count_has_an_independent_oracle(self):
        from datetime import date, timedelta
        from datathon.customer_tools import horizon_evidence
        data = asset("VT")
        data["rows"] = [{"date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(), "price": 100 + i} for i in range(365)]
        analyses = analyze([data], None)
        profile = build_profile(plan(conditions=[{"kind": "horizon", "excerpt": "1 month"}]))
        evidence = horizon_evidence(profile, analyses)
        # Jan 1 through Nov 30 are 334 possible starts with their next month inside 2025.
        self.assertEqual(evidence["calculation_review"][0]["window_count"], 334)
        self.assertEqual(evidence["calculation_review"][0]["independent_count"], 334)

    async def test_short_history_does_not_produce_missing_rolling_metrics(self):
        r = report()
        check = task("historical_market", "Establish long rolling returns from the supplied history.")
        check["required_measures"] = ["rolling_returns"]
        await execute_checks(r, [check], Mock(), None)
        self.assertEqual(r["tasks"][0]["status"], "blocked")
        self.assertIn("measure:rolling_returns", r["tasks"][0]["missing_outputs"])

    async def test_horizon_changes_are_not_served_from_the_wrong_cached_period(self):
        from datetime import date, timedelta
        data = asset("VT")
        data["rows"] = [{"date": (date(2022, 1, 1) + timedelta(days=i)).isoformat(), "price": 100 + i} for i in range(1500)]
        r = report([data]); budget = InquiryBudget()
        for duration in ("36 months", "3 months", "3 months"):
            check = task("horizon_window", "Check the historical outcome over this explicit duration.")
            check["horizon_excerpt"] = duration
            await execute_checks(r, [check], Mock(), None, budget)
        self.assertEqual(budget.tool_calls, 2)
        self.assertNotEqual(r["tasks"][0]["evidence_ids"], r["tasks"][1]["evidence_ids"])
        self.assertEqual(r["tasks"][1]["evidence_ids"], r["tasks"][2]["evidence_ids"])
        self.assertIn("3-month", r["tasks"][1]["actual_result"])

    async def test_review_accepts_user_context_and_receives_no_old_rejection(self):
        r = report(); runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            self.assertNotIn("review_feedback", payload)
            self.assertNotIn("previous_answer", payload)
            tools[0].handler(claim_reviews=[{"claim_id": "c", "status": "supported", "evidence_ids": ["statement.1.0"],
                "defect": "none", "severity": "local", "reason": "The user explicitly left this field unknown.", "repair": "none"}],
                task_reviews=[], answers_question=True, requested_scope_complete=False,
                remaining_user_requests=["The required amount remains unknown."], feedback="Scoped answer.")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await review_claims({"user_context": {"statement.1.0": "My loss limit is undecided."},
            "review_feedback": "Stale rejection", "previous_answer": "Old answer"}, [{"id": "c"}], r, runtime, InquiryBudget())
        self.assertTrue(result["accepted"])

    async def test_comparison_requires_common_currency_not_just_nonempty_prices(self):
        for currency, expected in (("USD", "evidence_ready"), ("CAD", "blocked")):
            r = report([asset("VTI"), asset("VCN.TO", currency)])
            await execute_checks(r, [task("product_comparison", "Compare the two funds on compatible observations.", scope="product_comparison")], Mock(), None)
            self.assertEqual(r["tasks"][0]["status"], expected)

    async def test_review_rejection_can_trigger_new_evidence_in_actual_workflow(self):
        runtime, seen = AsyncMock(), []
        async def run(role, payload, *, tools, stop_after_tool):
            handle = tools[0].handler; seen.append(role)
            if role == "customer_planner":
                handle(checks=[task("historical_market", "What does the observed asset history establish?")])
            elif role == "customer_analyst":
                if payload["review_feedback"] and "portfolio_context" in payload["available_tools"]:
                    handle(action="investigate", checks=[task("portfolio_context", "Are complete portfolio inputs available for this claim?", scope="client_context")], claims=[], follow_up="")
                else:
                    handle(action="conclude", checks=[], claims=claims(repaired="portfolio_context" in payload["tool_outcomes"].__str__()), follow_up="What are the before and after allocations?")
            else:
                accepted = any(row["tool"] == "portfolio_context" for row in payload["tool_outcomes"])
                audit(handle, payload, accepted, "Inspect incomplete holdings before claiming portfolio effects." if not accepted else "Scoped answer supported.")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan())):
            result = await research_question("Would adding this stock change my portfolio?", runtime=runtime, provider=Mock(asset=Mock(return_value=asset()), fx=Mock(return_value=fx())))
        self.assertIn("portfolio_context", result["executed_tools"])
        self.assertTrue(result["editor"]["explanation_review"]["accepted"])
        self.assertEqual(seen.count("customer_auditor"), 2)

    async def test_local_unsupported_claim_does_not_erase_supported_main_answer(self):
        from datathon.inquiry_engine import synthesize_inquiry
        r = report([asset()]); runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            if role == "customer_analyst":
                tools[0].handler(action="conclude", checks=[], claims=claims(), follow_up="")
            else:
                rows = [{"claim_id": x["id"], "status": "supported" if i != 2 else "insufficient",
                    "evidence_ids": x["evidence_ids"], "defect": "none" if i != 2 else "causal_inference",
                    "severity": "local", "reason": "History cannot establish the proposed causal interpretation." if i == 2 else "Limited historical statement.",
                    "repair": "delete" if i == 2 else "none"} for i, x in enumerate(payload["arguments"])]
                tools[0].handler(claim_reviews=rows, task_reviews=[], answers_question=True, requested_scope_complete=True, remaining_user_requests=[], feedback="Delete the unsupported causal sentence.")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await synthesize_inquiry(r, {"origin": "bedrock", "context": {"user.request": "Research the history."}}, runtime,
            AsyncMock(), lambda _: None, InquiryBudget(InquiryLimits(reviews=1)))
        self.assertEqual(result["answer_status"], "partial")
        self.assertEqual(len(result["arguments"]), 3)
        self.assertEqual(result["explanations"][0]["heading"], "My research conclusion")
        self.assertFalse(result["explanation_review"]["accepted"])

    def test_currency_period_and_coverage_changes_update_calculation_scope(self):
        data = asset("SCHB"); rates = fx()
        for i, row in enumerate(rates["rows"]): row["rate"] = 1.2 + i / 200
        usd = analyze([data], None, target_currency="USD")[0]
        cad = analyze([data], None, rates, target_currency="CAD")[0]
        self.assertNotEqual(usd["metrics"]["return"], cad["metrics"]["return"])
        self.assertEqual(cad["basis"], "CAD")
        reduced = deepcopy(data); reduced["rows"] = reduced["rows"][8:]
        shorter = analyze([reduced], None)[0]
        self.assertNotEqual(shorter["metrics"]["start"], usd["metrics"]["start"])
        self.assertNotEqual(shorter["metrics"]["return"], usd["metrics"]["return"])
        rates["rows"] = rates["rows"][3:]
        partial = analyze([data], None, rates, target_currency="CAD")[0]
        self.assertEqual(partial["missing_fx"], 3)
        self.assertEqual(partial["metrics"]["start"], rates["rows"][0]["date"])

    def test_correct_number_cannot_be_cited_from_another_object_or_promoted_to_portfolio(self):
        r = report([asset("VTI"), asset("SCHB")]); context = {"user.request": "Compare my options."}
        draft = claims("VTI.behavior")
        draft[0]["text"] = "Observed result: {{SCHB.return}}; this is historical only."
        with self.assertRaisesRegex(ValueError, "own verified evidence"):
            validate_claims(draft, r, context)
        draft[0]["text"] = "Observed result: {{VTI.return}}; this is historical only."
        output = validate_claims(draft, r, context)
        self.assertIn("USD;", output[0]["text"])
        self.assertIn(r["analyses"][0]["metrics"]["start"], output[0]["text"])
        draft[0].update(kind="calculation", scope="portfolio")
        with self.assertRaisesRegex(ValueError, "Asset evidence"):
            validate_claims(draft, r, context)

    def test_elapsed_budget_and_zero_remaining_work_stop_without_looping(self):
        clock = Mock(side_effect=[0, 3, 3])
        budget = InquiryBudget(InquiryLimits(seconds=2), clock)
        self.assertFalse(budget.take("model_calls"))
        self.assertEqual(budget.stop_reason, "time_budget")

    def test_literal_quantities_bind_to_verified_sources_with_units_dates_and_currency(self):
        r = report(); r["blocks"]["checked"] = {"text": "SCHB returned -12.50% in USD from 2023-01-03 to 2024-01-03.", "sources": []}
        draft = claims("checked"); context = {"user.request": "Assess historical behavior."}
        draft[0]["text"] = "Observed change was -12.50% in USD from 2023-01-03 to 2024-01-03; this does not predict future outcomes."
        checked = validate_claims(draft, r, context)
        self.assertEqual(checked[0]["numeric_bindings"][0]["support_ids"], ["checked"])
        for text in ("The observed gain was +12.50%; this is historical.",
                     "The observed loss was -12.50 in USD; this is historical.",
                     "The observed change was -12.50% in CAD; this is historical.",
                     "The observed change was -12.50% on 2023-01-04; this is historical."):
            draft[0]["text"] = text
            with self.assertRaises(ValueError): validate_claims(draft, r, context)


class DialogueTests(IsolatedAsyncioTestCase):
    def seed(self):
        return apply_turn(None, plan(conditions=[{"kind": "horizon", "excerpt": "5 years"},
            {"kind": "goal", "excerpt": "a home purchase"}]), "5 years for a home purchase")["conversation_state"]

    def test_correction_retraction_and_repeat_keep_provenance(self):
        state = self.seed(); horizon = state["statements"][0]["id"]
        updated = apply_turn(state, plan(assets=[], budget=None, conditions=[{"kind": "horizon", "excerpt": "Actually 8 years",
            "operation": "replace", "targets": [horizon]}]), "Actually 8 years")
        self.assertEqual([x["excerpt"] for x in updated["conditions"]], ["a home purchase", "Actually 8 years"])
        self.assertFalse(updated["conversation_state"]["statements"][0]["active"])
        new_id = updated["conditions"][-1]["id"]
        withdrawn = apply_turn(updated["conversation_state"], plan(assets=[], budget=None, conditions=[{"kind": "horizon", "excerpt": "Withdraw my horizon",
            "operation": "retract", "targets": [new_id]}]), "Withdraw my horizon")
        self.assertFalse(any(x["kind"] == "horizon" for x in withdrawn["conditions"]))
        self.assertTrue(withdrawn["assets"])

    async def test_model_outage_preserves_confirmed_fields_and_unknowns(self):
        updated = await understand("I like chess", None, previous_state=self.seed())
        self.assertEqual({x["kind"] for x in updated["conditions"]}, {"goal", "horizon"})
        self.assertEqual(updated["origin"], "local")
        self.assertIn("capacity", build_profile(updated)["unknown"])

    def test_compatible_money_and_risk_wording_are_not_automatic_conflicts(self):
        p = plan(conditions=[{"kind": "investment_amount", "excerpt": "3000 CAD"},
            {"kind": "investment_amount", "excerpt": "CAD 3,000.00"},
            {"kind": "willingness", "excerpt": "I accept price swings"},
            {"kind": "willingness", "excerpt": "Fluctuations are fine"}])
        self.assertEqual(build_profile(p)["conflicts"], [])

    def test_unknown_statement_stays_unknown_and_stable_ids_are_citable(self):
        from datathon.customer_reasoning import context_records
        p = apply_turn(None, plan(conditions=[{"kind": "capacity", "excerpt": "My loss capacity is undecided",
            "knowledge_status": "unknown"}]), "My loss capacity is undecided")
        self.assertIn("capacity", build_profile(p)["unknown"])
        context = context_records("Follow-up", p)
        self.assertEqual(context[p["conditions"][0]["id"]], "My loss capacity is undecided")


class SecurityTests(TestCase):
    def test_typo_and_short_name_use_traceable_search(self):
        rows = [{"symbol": "COST", "longname": "Costco Wholesale Corporation", "quoteType": "EQUITY", "exchange": "NMS", "currency": "USD"}]
        source = PublicResearch(transport=lambda url: {"quotes": rows}, clock=lambda: NOW)
        for query in ("Costco Wholesale", "Costco Wholsale"):
            result = source.resolve_security(query, search=True)
            self.assertEqual(result["symbol"], "COST")
            self.assertIn("finance/search", result["source_url"])

    def test_multiple_markets_do_not_silently_choose_a_security(self):
        rows = [{"symbol": symbol, "longname": "Shopify Inc.", "quoteType": "EQUITY", "exchange": exchange}
                for symbol, exchange in (("SHOP", "NYQ"), ("SHOP.TO", "TOR"))]
        source = PublicResearch(transport=lambda url: {"quotes": rows}, clock=lambda: NOW)
        with self.assertRaises(ResearchAmbiguous) as ctx:
            source.resolve_security("Shopify", search=True)
        self.assertEqual(len(ctx.exception.candidates), 2)
        self.assertEqual(source.resolve_security("SHOP.TO", search=True)["symbol"], "SHOP.TO")


class AssetStateTests(TestCase):
    def test_new_holding_preserves_considered_asset_and_explicit_retraction_removes_it(self):
        first = plan(); first["assets"] = [{"query": "VTI", "excerpt": "VTI", "role": "consider"}]
        state = apply_turn(None, first, "VTI")["conversation_state"]
        second = plan(); second["conditions"] = []; second["assets"] = [{"query": "BND", "excerpt": "BND", "role": "holding"}]
        state = apply_turn(state, second, "I hold BND")["conversation_state"]
        self.assertEqual([a["query"] for a in state["assets"]], ["VTI", "BND"])
        second["assets"] = [{"query": "BND", "excerpt": "BND", "role": "holding", "operation": "retract", "targets": ["BND"]}]
        result = apply_turn(state, second, "I no longer hold BND")
        self.assertEqual([a["query"] for a in result["assets"]], ["VTI"])
