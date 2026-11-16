"""Reserve execution budget for review without predetermining a financial answer."""
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock
from datathon.agents import AgentRun
from datathon.inquiry_contracts import InquiryBudget
from datathon.inquiry_engine import call, synthesize_inquiry
from tests.test_inquiry_contracts import report
from tests.test_customer_reasoning import claims, audit


class CompletionBudgetTests(IsolatedAsyncioTestCase):
    async def test_reserved_time_does_not_start_an_unfinishable_analyst_request(self):
        now = [0.]
        budget = InquiryBudget(clock=lambda: now[0])
        now[0] = 185.
        runtime = AsyncMock()
        result = await call(runtime, 'customer_analyst', {}, 'test', lambda: None, budget, reserve_seconds=60)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure'], 'review_reserve')
        self.assertEqual(budget.model_calls, 0)
        runtime.run.assert_not_called()

    async def test_optional_research_stops_with_time_and_slots_left_for_review(self):
        r = report()
        now = [0.]
        budget = InquiryBudget(clock=lambda: now[0])
        now[0] = 110.
        budget.model_calls = 8
        runtime = AsyncMock()
        seen = []
        async def run(role, payload, *, tools, stop_after_tool):
            seen.append(role)
            handle = tools[0].handler
            if role == 'customer_analyst':
                self.assertEqual(payload['available_tools'], {})
                self.assertIn('Conclude', payload['completion_instruction'])
                handle(action='conclude', checks=[], claims=claims('VTI.behavior'), follow_up='')
            else:
                audit(handle, payload)
            return AgentRun('ok', {})
        runtime.run.side_effect = run
        execute = AsyncMock()
        result = await synthesize_inquiry(r, {'origin':'bedrock','context':{'user.request':'Research VTI.'}}, runtime, execute, lambda _:None, budget)
        self.assertEqual(result['answer_status'], 'reviewed')
        self.assertEqual(seen, ['customer_analyst','customer_auditor'])
        self.assertEqual(budget.model_calls, 10)
        execute.assert_not_called()

    def test_signed_percentages_are_inserted_by_python_without_changing_units(self):
        from datathon.inquiry_engine import validate_claims
        r=report()
        r['blocks']['analysis.horizon']={'title':'Observed horizon results', 'text':'VTI: worst change -18.77%, best change +318.94%. These are historical observations.', 'sources':[]}
        claim=claims('analysis.horizon')[0]
        claim['text']='The history includes losses as well as gains. {{analysis.horizon}}'
        checked=validate_claims([claim],r,{'user.request':'Research VTI.'})
        self.assertIn('-18.77%',checked[0]['text'])
        self.assertIn('+318.94%',checked[0]['text'])
        claim['text']='The historical loss was 18.77%; future outcomes remain uncertain.'
        with self.assertRaisesRegex(ValueError,'Preserve signs'):
            validate_claims([claim],r,{'user.request':'Research VTI.'})
