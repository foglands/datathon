"""Source discovery and checked evidence stay distinct through the request path."""

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch

from botocore.exceptions import ClientError

from datathon.agents import AgentRun
from datathon.customer_workflow import research_question
from datathon.inquiry_contracts import InquiryBudget, fact_registry
from datathon.inquiry_engine import plan_inquiry, validate_claims
from datathon.web_research import AgentCoreSearch, SEC_TICKERS, verified_issuer_filings
from tests.test_customer_reasoning import claims
from tests.test_customer_research import plan


class SearchTests(TestCase):
    def test_managed_service_discards_unsafe_links_and_surfaces_access_denial(self):
        client = Mock()
        client.invoke_web_search.return_value = {"results": [
            {"url": "http://example.com/unsafely-served"},
            {"url": "https://example.com@unknown.example/impersonation"},
            {"url": "https://example.com/research", "title": None, "text": "Published figure"},
            {"url": "https://example.com/research", "title": "Duplicate"},
        ]}
        search = AgentCoreSearch("us-east-1", client=client)
        returned = search.lookup("daily_prices", ("NVDA",))
        self.assertEqual(returned["status"], "success")
        self.assertEqual([hit["title"] for hit in returned["results"]], ["example.com"])
        self.assertEqual(client.invoke_web_search.call_args.kwargs["webSearchId"], "web-search.v1")
        client.invoke_web_search.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "private identity details"}}, "InvokeWebSearch")
        returned = search.lookup("daily_prices", ("NVDA",))
        self.assertEqual(returned["status"], "access_denied")
        self.assertNotIn("private identity", str(returned))


class LiveWorkflowTests(IsolatedAsyncioTestCase):
    async def test_planner_selects_research_topics(self):
        runtime = AsyncMock()

        async def run(role, payload, *, tools, stop_after_tool):
            self.assertIn("fund_methods", payload["available_web_topics"])
            tools[0].handler(checks=[], web_topics=["fund_methods"])
            return AgentRun("ok", {})

        runtime.run.side_effect = run
        result = await plan_inquiry("How does ESGU screen holdings?", plan(), runtime, web_available=True)
        self.assertEqual(result["web_topics"], ["fund_methods"])

    async def test_search_results_do_not_become_checked_quotes(self):
        client = Mock()
        client.invoke_web_search.return_value = {"results": [
            {"url": "https://example.com/prices", "title": "Page with a quote", "text": "Market price USD 999.99"}
        ]}
        search = AgentCoreSearch("us-east-1", client=client)
        with patch("datathon.customer_workflow.default_provider") as provider:
            from datathon.customer_data import UnavailableResearch
            provider.return_value = UnavailableResearch("No price source.")
            report = await research_question("What is the daily risk for Tesla (TSLA)? My amount is USD 4000.",
                                             web_search=search)
        self.assertEqual(report["web_search"][0]["status"], "success")
        self.assertEqual(report["analyses"], [])
        key = "web.daily_prices.1"
        self.assertEqual(report["blocks"][key]["scope"]["level"], "source_lead")
        self.assertNotIn(key, fact_registry(report))
        self.assertNotIn("4000", client.invoke_web_search.call_args.kwargs["searchQuery"])
        for kind in ("fact", "limitation"):
            claim = claims(evidence=key)[0]
            claim.update(text="The observed price was USD 999.99.", kind=kind)
            with self.assertRaises(ValueError):
                validate_claims([claim], report, {"user.request": report["question"]})

    async def test_sec_checks_ticker_identity_filing_dates_and_document(self):
        filings = {"cik": "1318605", "tickers": ["TSLA"], "filings": {"recent": {
            "form": ["10-K", "8-K", "10-Q"], "filingDate": ["2999-02-01", "2026-04-02", "2026-01-02"],
            "accessionNumber": ["0001318605-99-000001", "0001318605-26-000002", "0001318605-26-000001"],
        }}}
        transport = Mock(side_effect=[{"a": {"ticker": "TSLA", "cik_str": 1318605}}, filings])
        budget = InquiryBudget()
        assets = [{"query": "TSLA", "role": "consider"}]
        blocks = await verified_issuer_filings(assets, budget, transport)
        result = blocks["TSLA.sec_filing"]
        self.assertEqual(result["scope"]["as_of"], "2026-01-02")
        self.assertTrue(result["sources"][0].endswith("0001318605-26-000001-index.htm"))
        self.assertEqual(transport.call_args_list[0].args[0], SEC_TICKERS)
        self.assertEqual(transport.call_args_list[1].args[0], "https://data.sec.gov/submissions/CIK0001318605.json")
        filings["tickers"] = ["OTHER"]
        transport.side_effect = [{"a": {"ticker": "TSLA", "cik_str": 1318605}}, filings]
        self.assertEqual(await verified_issuer_filings(assets, InquiryBudget(), transport), {})
