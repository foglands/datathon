"""Customer interface acceptance: conclusion first, useful failures, no empty evidence cards."""
import asyncio
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.test_app import CUSTOMER_APP, AppTest
from tests.test_customer_research import asset, fx, plan
from tests.test_customer_reasoning import sections
from datathon.customer_report import METHOD
from datathon.customer_workflow import research_question
from datathon.review_snapshot import fingerprint


def seal(report):
    report['report_digest'] = fingerprint({k:v for k,v in report.items() if k != 'report_digest'})
    return report


@unittest.skipIf(AppTest is None, 'Streamlit is required')
class CustomerViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provider = Mock(asset=Mock(return_value=asset()), fx=Mock(return_value=fx()))
        with patch('datathon.customer_workflow.understand', AsyncMock(return_value=plan())):
            cls.base = asyncio.run(research_question('Research AMD with 3000 CAD.', provider=provider))

    def setUp(self):
        self.app = AppTest.from_file(str(CUSTOMER_APP), default_timeout=30).run()
        self.assertFalse(self.app.exception)

    def show(self, report):
        self.app.session_state['customer_report'] = seal(report)
        self.app.run()
        self.assertFalse(self.app.exception)

    def test_home_is_a_customer_question_without_marketing_or_developer_modes(self):
        self.assertEqual(len(self.app.text_area), 1)
        self.assertEqual(len(self.app.number_input), 0)
        self.assertFalse(any(r.label == 'Workspace' for r in self.app.radio))
        self.assertTrue(any(b.label == 'Analyze my question' for b in self.app.button))
        values = ' '.join(str(getattr(n.proto,'body','')) for n in self.app.main if hasattr(n,'proto'))
        self.assertNotIn('A little clarity', values)
        self.assertNotIn('Before your next move', values)

    def test_sidebar_applies_question_without_running_it(self):
        from datathon.customer_ui import EXAMPLES
        self.app.radio(key='customer_example').set_value('Compare two funds').run()
        next(b for b in self.app.button if b.label == 'Apply question').click().run()
        self.assertEqual(self.app.session_state['customer_question'], EXAMPLES['Compare two funds'])
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.session_state.filtered_state.get('customer_report'))

    def test_reviewed_conclusion_precedes_question_export_tabs_and_evidence(self):
        report = deepcopy(self.base)
        report['editor'].update(explanations=sections(), answer_status='reviewed')
        self.show(report)
        values = [str(getattr(n.proto,'body','')) for n in self.app.main if hasattr(n,'proto')]
        conclusion = next(i for i,v in enumerate(values) if 'class="conclusion-text"' in v)
        question = next(i for i,v in enumerate(values) if v == report['question'])
        support = next(i for i,v in enumerate(values) if 'Supporting evidence' in v)
        self.assertLess(conclusion, question)
        self.assertLess(conclusion, support)
        self.assertNotIn('Your idea, in perspective.', ' '.join(values))
        self.assertNotIn('No separately reviewed', ' '.join(values))

    def test_failed_synthesis_shows_checked_facts_without_empty_sides(self):
        report = deepcopy(self.base)
        report['editor']['explanations'] = []
        report['editor']['answer_status'] = 'evidence_only'
        self.show(report)
        values = ' '.join(str(getattr(n.proto,'body','')) for n in self.app.main if hasattr(n,'proto'))
        self.assertIn('A conclusion is not available yet.', values)
        self.assertIn('Available evidence', values)
        self.assertIn(report['blocks']['AMD.behavior']['text'], values)
        self.assertNotIn('Supporting evidence', values)
        self.assertNotIn('Counterpoints &amp; risks', values)
        self.assertNotIn('No separately reviewed', values)

    def test_one_reviewed_side_does_not_create_an_empty_opposing_card(self):
        report = deepcopy(self.base)
        report['editor'].update(explanations=sections()[:2], answer_status='partial')
        self.show(report)
        values = ' '.join(str(getattr(n.proto,'body','')) for n in self.app.main if hasattr(n,'proto'))
        self.assertIn('Supporting evidence', values)
        self.assertNotIn('Counterpoints &amp; risks', values)

    def test_tampered_report_does_not_release_its_conclusion(self):
        report = seal(deepcopy(self.base))
        report['editor']['explanations'] = sections()
        self.app.session_state['customer_report'] = report
        self.app.run()
        self.assertFalse(self.app.exception)
        values = ' '.join(str(getattr(n.proto,'body','')) for n in self.app.main if hasattr(n,'proto'))
        self.assertIn('no longer matches', values)
        self.assertNotIn('class="conclusion-text"', values)

    def test_stated_context_is_sent_to_research_and_results_render(self):
        self.app.text_area(key='customer_question').set_value('Research AMD').run()
        self.app.text_input(key='customer_goal').set_value('Tuition')
        self.app.text_input(key='customer_timing').set_value('Two years')
        self.app.text_input(key='customer_constraints').set_value('No other funds')
        workflow = AsyncMock(return_value=deepcopy(self.base))
        with patch('datathon.customer_ui.customer_runtime', return_value=None), patch('datathon.customer_ui.research_question', workflow):
            next(b for b in self.app.button if b.label == 'Analyze my question').click().run()
        self.assertFalse(self.app.exception)
        for value in ('Research AMD','Tuition','Two years','No other funds'):
            self.assertIn(value, workflow.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
