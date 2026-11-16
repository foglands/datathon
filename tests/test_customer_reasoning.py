"""Behavioral contracts for inquiry, contextual synthesis and review."""

from copy import deepcopy
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch
from datathon.agents import AgentRun
from datathon.customer_reasoning import plan_analysis, synthesize, validate_findings, number_registry
from datathon.customer_tools import horizon_evidence, execute_checks
from datathon.customer_workflow import research_question
from datathon.customer_profile import build_profile
from datathon.customer_report import analyze
from tests.test_customer_research import asset, fx, plan

HEADINGS = ["My research conclusion", "What supports this view", "What argues against it", "Important gaps and next step"]

def sections(evidence="AMD.behavior"):
    return [{"heading": heading, "text": "The checked history informs the question, while future outcomes remain unknown.",
             "evidence_ids": [evidence], "context_ids": ["user.request"]} for heading in HEADINGS]


def task(tool, question, output=None, scope="asset"):
    from datathon.inquiry_contracts import tool_catalog
    spec = tool_catalog()[tool]
    return {"tool": tool, "question": question, "context_ids": ["user.request"],
            "relevance": "Resolve a material part of the current request.", "required_inputs": spec["inputs"],
            "required_outputs": [output] if output else spec["outputs"], "required_measures": spec["measures"][:1], "scope": scope,
            "completion_condition": "Return verified evidence answering this question within the stated scope."}


def claims(evidence="AMD.behavior", repaired=False):
    return [{"id": "claim." + str(i), "heading": heading,
             "text": ("Incomplete holdings prevent whole-portfolio conclusions; historical observations remain useful." if repaired else
                      "The checked history informs the question, while future outcomes remain unknown."),
             "kind": "limitation", "scope": "asset", "evidence_ids": [evidence], "context_ids": ["user.request"],
             "relevance": "The evidence limits the available assessment.", "assumptions": [], "limitations": ["Future outcomes remain unknown."]}
            for i,heading in enumerate(HEADINGS)]


def audit(handle, payload, accepted=True, feedback="Supported within scope."):
    handle(claim_reviews=[{"claim_id": row["id"], "status": "supported" if accepted else "insufficient",
        "evidence_ids": row["evidence_ids"], "defect": "none" if accepted else "unsupported", "severity": "conclusion",
        "reason": feedback, "repair": "none" if accepted else "narrow"} for row in payload["arguments"]],
        task_reviews=[{"task_id": row["id"], "status": "complete" if not row["missing_outputs"] and row["scope_supported"] else "blocked",
                       "reason": "Checked the actual output against the task condition."} for row in payload["tasks"]],
        answers_question=accepted, requested_scope_complete=accepted, remaining_user_requests=[] if accepted else ["Resolve material evidence gap."], feedback=feedback)


class InquiryTests(IsolatedAsyncioTestCase):
    async def test_tool_question_cannot_supply_unverified_numbers_to_evidence(self):
        p=plan()
        report={"profile":build_profile(p),"analyses":analyze([asset()],None),"executed_tools":[],"blocks":{},
                "tool_outcomes":[],"risks":[],"cpi":None,"plan":p,"created_at":"2026-11-16T00:00:00Z"}
        check={"tool":"cash_needs","question":"Can a fabricated 987654 CAD withdrawal be funded?","context_ids":["user.request"]}
        await execute_checks(report,[check],Mock(),None)
        self.assertNotIn("987654",report["blocks"]["risk.cash_needs"]["text"])
        self.assertEqual(report["tool_outcomes"][0]["question"],check["question"])

    async def test_model_can_investigate_after_initial_evidence_and_repair_rejected_answer(self):
        runtime = AsyncMock()
        provider = Mock(asset=Mock(return_value=asset()), fx=Mock(return_value=fx()))
        calls, audits = [], []
        async def run(role, payload, *, tools, stop_after_tool):
            calls.append((role, deepcopy(payload)))
            handle = tools[0].handler
            if role == "customer_planner":
                handle(checks=[])
            elif role == "customer_analyst":
                attempt=sum(row[0]=="customer_analyst" for row in calls)
                if not payload["tool_outcomes"]:
                    handle(action="investigate", checks=[task("portfolio_context", "Can incomplete holdings establish whole-portfolio effects?", scope="client_context")], claims=[], follow_up="")
                elif attempt==2:
                    handle(action="investigate",checks=[task("historical_market", "What observed drawdown evidence can qualify the answer?")],claims=[],follow_up="")
                elif attempt in (3,4):
                    try:
                        handle(action="conclude",checks=[],claims=claims("missing.evidence"),follow_up="")
                    except ValueError:
                        return AgentRun("error",{})
                else:
                    self.assertIn("Complete portfolio weights were not supplied", payload["verified_evidence"]["analysis.portfolio"]["text"])
                    if audits:
                        self.assertIn("Address incomplete holdings", str(payload["review_feedback"]))
                    handle(action="conclude", checks=[], claims=claims("analysis.portfolio", repaired=bool(audits)), follow_up="What are your existing holdings and weights?")
            elif role == "customer_auditor":
                accepted = bool(audits)
                audit(handle, payload, accepted, "Supported." if accepted else "Address incomplete holdings explicitly.")
                audits.append(accepted)
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan())):
            result = await research_question("Does this purchase change my overall risk?", runtime=runtime, provider=provider)
        self.assertEqual(result["executed_tools"], ["portfolio_context", "historical_market"])
        self.assertEqual(sum(role=="customer_analyst" for role,_ in calls),6)
        self.assertEqual(audits, [False, True])
        self.assertEqual(result["editor"]["origin"], "bedrock")
        provider.cpi.assert_not_called()
        self.assertEqual(calls[0][0], "customer_planner")
        self.assertEqual(result["editor"]["explanations"][0]["heading"], "My research conclusion")

    async def test_material_conflict_is_available_to_review_without_forcing_lead(self):
        runtime = AsyncMock()
        provider = Mock(asset=Mock(return_value=asset()), fx=Mock(return_value=fx()))
        request = plan(conditions=[{"kind":"capacity", "excerpt":"Maximum drawdown must not exceed 1%."}])
        async def run(role, payload, *, tools, stop_after_tool):
            handle=tools[0].handler
            if role == "customer_planner": handle(checks=[])
            elif role == "customer_analyst":
                self.assertTrue(any(key.startswith("explicit_rule") for key in payload["verified_evidence"]))
                # There is no required_takeaway or predetermined largest-risk lead.
                self.assertNotIn("required_takeaway", payload)
                handle(action="conclude", checks=[], claims=claims(repaired=bool(payload["previous_answer"])), follow_up="")
            else:
                self.assertIn("Maximum drawdown", str(payload["user_context"]))
                audit(handle, payload, False, "The conclusion ignores the user's explicit loss capacity.")
            return AgentRun("ok",{})
        runtime.run.side_effect=run
        with patch("datathon.customer_workflow.understand",AsyncMock(return_value=request)):
            result=await research_question("Maximum drawdown must not exceed 1%.",runtime=runtime,provider=provider)
        self.assertFalse(result["editor"].get("explanations"))
        self.assertEqual(len([step for step in result["editor"]["analysis_steps"] if step["action"]=="review"]),2)

    async def test_full_optional_context_reaches_planner_and_not_only_the_intake_labels(self):
        runtime=AsyncMock()
        question="Research AMD. Additional user-stated details: tuition is due before my grant arrives."
        async def run(role,payload,*,tools,stop_after_tool):
            self.assertEqual(payload["user_context"]["user.request"],question)
            self.assertNotIn("trace",payload["intake"])
            self.assertNotIn("question",payload["intake"])
            self.assertIn("horizon",payload["client_profile"]["unknown"])
            tools[0].handler(checks=[{"tool":"cash_needs","question":"Can the amount cover tuition before income arrives?","context_ids":["user.request"]}])
            return AgentRun("ok",{})
        runtime.run.side_effect=run
        result=await plan_analysis(question,plan(),runtime)
        self.assertEqual(result["checks"][0]["tool"],"cash_needs")


class EvidenceDisciplineTests(TestCase):
    def test_analysis_transport_budget_is_separate_from_legacy_roles(self):
        from datathon.customer_agents import CustomerAgents
        runtime=CustomerAgents()
        self.assertEqual(runtime._read_timeout("customer_analyst"),75)
        self.assertEqual(runtime._read_timeout("customer_auditor"),75)
        self.assertEqual(runtime._read_timeout("profile"),12)
        self.assertEqual(runtime._inference_parameters("customer_analyst"),{"temperature":0.0})
        self.assertEqual(runtime._inference_parameters("profile"),{})


    def test_only_values_from_cited_checked_evidence_can_be_inserted(self):
        blocks={"fact":{"text":"Observed change +12.34%."},"other":{"text":"Observed loss 8.00%."}}
        numbers=number_registry(blocks)
        draft=sections("fact")
        draft[0]["text"]="The observed change is {{n0}}; future outcomes remain unknown."
        self.assertIn("+12.34%",validate_findings(draft,blocks,{"user.request":"Query"},numbers)[0]["text"])
        draft[0]["text"]="The observed change is +12.34%; future outcomes remain unknown."
        self.assertIn("+12.34%",validate_findings(draft,blocks,{"user.request":"Query"},numbers)[0]["text"])
        for text in ("The observed change is 99%; this is unsupported.","The observed change is {{n1}}; this cites the wrong evidence."):
            draft[0]["text"]=text
            with self.assertRaises(ValueError):validate_findings(draft,blocks,{"user.request":"Query"},numbers)

    def test_name_synonym_and_irrelevant_context_do_not_change_horizon_calculation(self):
        analyses=analyze([asset()],None)
        results=[]
        for name,text,noise in (("Robin","one year",""),("Sam","12 months",""),("Sam","1 year","I like photography")):
            profile=build_profile(plan(conditions=[{"kind":"horizon","excerpt":text}]))
            profile["name"]=name;profile["unrelated"]=noise
            results.append(horizon_evidence(profile,analyses))
        self.assertTrue(all(row==results[0] for row in results))
        changed=build_profile(plan(conditions=[{"kind":"horizon","excerpt":"1 month"}]))
        self.assertNotEqual(horizon_evidence(changed,analyses),results[0])

    def test_date_ranges_do_not_become_negative_years_and_loss_sign_is_preserved(self):
        blocks={"fact":{"text":"From 2021-11-15 to 2026-11-13, the observed return was -12.34%."}}
        draft=sections("fact")
        draft[0]["text"]="The observed 2021-2026 return was -12.34%; future outcomes remain unknown."
        validate_findings(draft,blocks,{"user.request":"Query"},number_registry(blocks))
        draft[0]["text"]="The observed 2021-2026 return was +12.34%; future outcomes remain unknown."
        with self.assertRaises(ValueError):
            validate_findings(draft,blocks,{"user.request":"Query"},number_registry(blocks))

    def test_uncomputed_cross_unit_relationship_is_rejected_even_with_valid_operands(self):
        blocks={"fact":{"text":"Recovery took 343 calendar days. The stated withdrawal was after 12 months."}}
        draft=sections("fact")
        draft[0]["text"]="Recovery took 343 calendar days, exceeding the 12-month horizon."
        with self.assertRaisesRegex(ValueError,"not a checked calculation"):
            validate_findings(draft,blocks,{"user.request":"Query"},number_registry(blocks))
        draft[0]["text"]="If the horizon is shorter than three years, the assessment changes."
        with self.assertRaisesRegex(ValueError,"unstated time cutoff"):
            validate_findings(draft,blocks,{"user.request":"Query"},number_registry(blocks))
        blocks={"risk.market_liquidity":{"text":"The stated amount was 0.001% of daily volume; spreads and impact are unassessed."}}
        draft=sections("risk.market_liquidity")
        draft[0]["text"]="This indicates no material market-liquidity constraint for execution."
        with self.assertRaisesRegex(ValueError,"cannot establish execution liquidity"):
            validate_findings(draft,blocks,{"user.request":"Query"},number_registry(blocks))

    def test_stated_input_requires_its_extracted_context_citation(self):
        blocks={"fact":{"text":"Observed return -8.00%."}}
        context={"user.request":"Question", "user.0":"Withdraw in 12 months."}
        draft=sections("fact")
        draft[0]["text"]="You stated a withdrawal in 12 months; this is an input, not a forecast."
        with self.assertRaises(ValueError): validate_findings(draft,blocks,context,number_registry(blocks))
        draft[0]["context_ids"].append("user.0")
        validate_findings(draft,blocks,context,number_registry(blocks))

    def test_cpi_quantities_preserve_their_own_comparison_window(self):
        blocks={"risk.purchasing_power":{"text":"Between 2022-01-31 and 2026-10-30, the real change was +20.00%."}}
        draft=sections("risk.purchasing_power");context={"user.request":"Question"}
        draft[0]["text"]="The inflation-adjusted gain was +20.00% over the full market history."
        with self.assertRaisesRegex(ValueError,"CPI-aligned"):
            validate_findings(draft,blocks,context,number_registry(blocks))
        draft[0]["text"]="The inflation-adjusted gain was 20.00% over the full market history."
        with self.assertRaisesRegex(ValueError,"CPI-aligned"):
            validate_findings(draft,blocks,context,number_registry(blocks))
        draft[0]["text"]="Between 2022-01-31 and 2026-10-30, the observed inflation-adjusted gain was +20.00%."
        validate_findings(draft,blocks,context,number_registry(blocks))
