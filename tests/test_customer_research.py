"""Customer workflow, public-source validation and independent financial checks."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun
from datathon.customer_agents import understand, edit_report
from datathon.customer_data import PublicResearch, ResearchUnavailable
from datathon.customer_report import analyze, calculate, review, evidence_blocks, verify_report
from datathon.customer_workflow import research_question


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def asset(symbol="AMD", currency="USD"):
    prices = [100 + index for index in range(15)] + [88 + index for index in range(25)]
    return {"symbol": symbol, "name": symbol, "currency": currency, "price": 113.,
            "price_as_of": "2026-11-13T21:00:00+00:00", "retrieved_at": NOW.isoformat(),
            "price_age_days": 2., "omitted_rows": 0,
            "rows": [{"date": (NOW.date() - timedelta(days=42 - index)).isoformat(), "price": float(price)}
                     for index, price in enumerate(prices)],
            "source": "Synthetic test fixture", "source_url": "https://example.org/prices",
            "adjustment": "synthetic adjusted close"}


def fx():
    return {"rows": [{"date": row["date"], "rate": 1.4} for row in asset()["rows"]],
            "retrieved_at": NOW.isoformat(), "source_url": "https://example.org/fx"}


def plan(**extra):
    return {"mode": "research", "assets": [{"query": "amd", "excerpt": "amd", "role": "consider"}],
            "budget": {"amount": 3000., "currency": "CAD", "excerpt": "3000 CAD"},
            "conditions": [], "origin": "bedrock", "question": "When will you need the money?", "trace": [], **extra}


class PublicSourceTests(unittest.TestCase):
    def payload(self):
        data = asset()
        return {"chart": {"result": [{"meta": {"symbol": "AMD", "currency": "USD", "exchangeTimezoneName": "America/New_York",
                        "regularMarketTime": int((NOW - timedelta(days=2)).timestamp()), "regularMarketPrice": 113.},
                "timestamp": [int(datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc).timestamp()) for row in data["rows"]],
                "indicators": {"adjclose": [{"adjclose": [row["price"] for row in data["rows"]]}]}}]}}

    def test_lowercase_company_name_can_resolve_after_invalid_ticker(self):
        calls = []
        def transport(url):
            calls.append(url)
            if "/chart/APPLE?" in url:
                raise ResearchUnavailable("The source did not return this instrument.")
            if "/search?" in url:
                return {"quotes": [{"symbol": "AAPL", "shortname": "Apple", "quoteType": "EQUITY"}]}
            payload = self.payload()
            payload["chart"]["result"][0]["meta"]["symbol"] = "AAPL"
            return payload
        result = PublicResearch(transport=transport, clock=lambda: NOW).asset("apple")
        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(len(calls), 3)

    def test_malformed_provider_shapes_are_reported_as_unavailable(self):
        for payload in (None, [], {"quotes": None}, {"observations": [None]}):
            source = PublicResearch(transport=lambda url: payload, clock=lambda: NOW)
            for operation in (lambda: source.resolve("Advanced Micro Devices"), source.fx, source.cpi):
                with self.subTest(payload=payload), self.assertRaises(ResearchUnavailable):
                    operation()

    def test_validates_dates_symbol_currency_and_adjusted_prices(self):
        source = PublicResearch(transport=lambda url: self.payload(), clock=lambda: NOW)
        result = source.asset("amd")
        self.assertEqual(result["symbol"], "AMD")
        self.assertEqual(len(result["rows"]), 40)
        self.assertIn("adjusted close", result["adjustment"])
        for kind in ("symbol", "currency", "future", "negative", "missing_adjustment"):
            payload = self.payload()
            entry = payload["chart"]["result"][0]
            if kind == "symbol": entry["meta"]["symbol"] = "NVDA"
            if kind == "currency": entry["meta"]["currency"] = "?"
            if kind == "future": entry["meta"]["regularMarketTime"] = int((NOW + timedelta(days=2)).timestamp())
            if kind == "negative": entry["indicators"]["adjclose"][0]["adjclose"][0] = -1
            if kind == "missing_adjustment": entry["indicators"].pop("adjclose")
            with self.subTest(kind=kind), self.assertRaises(ResearchUnavailable):
                PublicResearch(transport=lambda url: payload, clock=lambda: NOW).asset("AMD")

    def test_current_session_excluded_and_null_rows_disclosed(self):
        payload = self.payload()
        entry = payload["chart"]["result"][0]
        entry["timestamp"].append(int(NOW.timestamp()))
        entry["indicators"]["adjclose"][0]["adjclose"].append(9999)
        entry["indicators"]["adjclose"][0]["adjclose"][1] = None
        result = PublicResearch(transport=lambda url: payload, clock=lambda: NOW).asset("AMD")
        self.assertEqual(len(result["rows"]), 39)
        self.assertEqual(result["omitted_rows"], 1)
        self.assertNotIn(NOW.date().isoformat(), [row["date"] for row in result["rows"]])

    def test_fx_dates_must_be_real_ordered_and_not_future(self):
        for observations in ([{"d": "2026-11-17", "FXUSDCAD": {"v": "1.4"}}],
                             [{"d": "2026-11-13", "FXUSDCAD": {"v": "NaN"}}], []):
            with self.assertRaises(ResearchUnavailable):
                PublicResearch(transport=lambda url: {"observations": observations}, clock=lambda: NOW).fx()

    def test_ambiguous_company_names_do_not_choose_first_listing(self):
        payload = {"quotes": [{"symbol": "ABC", "quoteType": "EQUITY"}, {"symbol": "ABD", "quoteType": "EQUITY"}]}
        with self.assertRaises(ResearchUnavailable):
            PublicResearch(transport=lambda url: payload).resolve("Some Company")


class CalculationTests(unittest.TestCase):
    def test_cad_conversion_is_once_and_sizing_uses_latest_dated_fx(self):
        result, = analyze([asset()], plan()["budget"], fx())
        self.assertEqual(result["basis"], "CAD")
        self.assertAlmostEqual(result["rows"][0]["price"], 140)
        self.assertAlmostEqual(result["valuation"]["price"], 158.2)
        self.assertEqual(result["valuation"]["whole_shares"], 18)
        self.assertAlmostEqual(result["valuation"]["remaining_cash"], 152.4)
        self.assertTrue(review(result["rows"], result["metrics"]))

    def test_missing_fx_never_invents_cad_values(self):
        result, = analyze([asset()], plan()["budget"])
        self.assertEqual(result["basis"], "USD")
        self.assertIsNone(result["valuation"])

    def test_currency_unknown_and_usd_budget_are_not_treated_as_cad(self):
        unknown, = analyze([asset()], {"amount": 3000, "currency": ""}, fx())
        self.assertIsNone(unknown["valuation"])
        usd, = analyze([asset()], {"amount": 3000, "currency": "USD"}, fx())
        self.assertEqual(usd["basis"], "USD")
        self.assertEqual(usd["valuation"]["price"], 113)

    def test_missing_fx_dates_are_dropped_not_forward_filled(self):
        rates = fx()
        rates["rows"].pop(7)
        result, = analyze([asset()], plan()["budget"], rates)
        self.assertEqual(result["missing_fx"], 1)
        self.assertEqual(len(result["rows"]), 39)

    def test_comparisons_share_identical_dates_without_combining_allocations(self):
        second = asset("SPY")
        second["rows"] = second["rows"][5:]
        first, second = analyze([asset(), second], plan()["budget"], fx())
        self.assertEqual(first["metrics"]["start"], second["metrics"]["start"])
        self.assertEqual(first["metrics"]["observations"], 35)
        self.assertEqual(first["alignment_omissions"], 5)

    def test_independent_check_rejects_injected_calculation_or_chart_errors(self):
        for field in ("return", "drawdown", "volatility", "path"):
            def corrupt(rows):
                result = calculate(rows)
                if field == "path": result["path"][3]["index"] += 1
                else: result[field] += .01
                return result
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "independent"):
                analyze([asset()], None, calculator=corrupt)

    def test_stale_quotes_and_preferences_cannot_become_positive_verdicts(self):
        old = asset()
        old["price_age_days"] = 30
        results = analyze([old], None)
        blocks, required = evidence_blocks(plan(conditions=[{"kind": "preference", "excerpt": "avoid controversies"}]), results, [])
        self.assertEqual(required, "AMD.stale")
        self.assertIn("preference_gap", blocks)


class AgentAndWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_extraction_preserves_lowercase_asset_and_explicit_budget(self):
        question = "i want to invest stock share of amd with 3000 cad"
        runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            tools[0].handler(mode="research", assets=[{"query": "amd", "excerpt": question, "role": "consider"}],
                conditions=[], budget_text="3000", currency="CAD", budget_excerpt="3000 cad", question_to_ask="When do you need the money?")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await understand(question, runtime)
        self.assertEqual(result["assets"][0]["query"], "amd")
        self.assertEqual(result["budget"]["amount"], 3000)
        self.assertEqual(result["origin"], "bedrock")

    async def test_model_cannot_invent_amount_or_currency(self):
        runtime = AsyncMock()
        async def run(role, payload, *, tools, stop_after_tool):
            with self.assertRaises(ValueError):
                tools[0].handler(mode="research", assets=[], conditions=[], budget_text="3000", currency="CAD",
                                 budget_excerpt="$3000", question_to_ask="When?")
            return AgentRun("error", {})
        runtime.run.side_effect = run
        result = await understand("Invest $3000 in amd", runtime)
        self.assertNotEqual((result.get("budget") or {}).get("currency"), "CAD")

    async def test_local_fallback_is_labelled_and_preserves_cash_amount(self):
        result = await understand("i want to invest stock share of amd with 3000 cad", None)
        self.assertEqual(result["origin"], "local")
        self.assertEqual(result["budget"]["amount"], 3000)

    async def test_funding_and_existing_holdings_are_not_fetched_as_purchase_candidates(self):
        provider = AsyncMock()
        provider.asset = unittest.mock.Mock(return_value=asset())
        provider.fx = unittest.mock.Mock(return_value=fx())
        intake = plan(assets=[{"query": "amd", "role": "consider"}, {"query": "msft", "role": "funding"}])
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=intake)):
            result = await research_question("Buy AMD by selling MSFT", provider=provider)
        provider.asset.assert_called_once_with("amd")
        self.assertIn("portfolio_gap", result["blocks"])
        self.assertTrue(verify_report(result))
        result["analyses"][0]["metrics"]["return"] += .1
        self.assertFalse(verify_report(result))

    async def test_explicit_base_currency_does_not_require_an_invented_budget(self):
        provider = unittest.mock.Mock()
        provider.asset.return_value = asset()
        provider.fx.return_value = fx()
        intake = plan(budget=None, conditions=[{"kind": "base_currency", "excerpt": "Use CAD as my base currency"}])
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=intake)):
            report = await research_question("Research AMD in CAD", provider=provider)
        self.assertEqual(report["analyses"][0]["basis"], "CAD")
        self.assertIsNone(report["analyses"][0]["valuation"])
        provider.fx.assert_called_once()

    async def test_provider_failure_does_not_publish_fictional_numbers(self):
        provider = unittest.mock.Mock()
        provider.asset.side_effect = ResearchUnavailable("Source unavailable")
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan())):
            result = await research_question("AMD 3000 CAD", provider=provider)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["analyses"], [])
        self.assertTrue(result["errors"])

    async def test_model_cannot_omit_required_evidence_or_conflict(self):
        runtime = AsyncMock()
        blocks = {"risk": {"text": "Material risk"}, "return": {"text": "Historical return"}}
        async def run(role, payload, *, tools, stop_after_tool):
            with self.assertRaises(ValueError):
                tools[0].handler(takeaway_id="return", evidence_ids=["return"])
            tools[0].handler(takeaway_id="risk", evidence_ids=["risk"])
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await edit_report(plan(), blocks, runtime, "risk")
        self.assertEqual(result["takeaway"], "risk")
        self.assertIn("return", result["order"])

    async def test_model_prose_is_withheld_when_separate_review_rejects_it(self):
        runtime = AsyncMock()
        blocks = {"fact": {"title": "Observed history", "text": "Historical return alone cannot predict future performance."}}
        sections = [{"heading": heading, "text": "The available history does not establish a future outcome.", "evidence_ids": ["fact"]}
                    for heading in ("How I read your idea", "The main trade-off", "My research conclusion")]
        async def run(role, payload, *, tools, stop_after_tool):
            self.assertEqual(payload["required_tool"], stop_after_tool)
            if role == "customer_report":
                tools[0].handler(takeaway_id="fact", evidence_ids=["fact"], explanations=sections)
            else:
                tools[0].handler(accepted=False, reason="unsupported_claim")
            return AgentRun("ok", {})
        runtime.run.side_effect = run
        result = await edit_report(plan(), blocks, runtime)
        self.assertNotIn("explanations", result)
        self.assertFalse(result["explanation_review"]["accepted"])

    async def test_model_cannot_insert_spelled_out_financial_quantities(self):
        runtime = AsyncMock()
        blocks = {"fact": {"text": "Checked history"}}
        async def run(role, payload, *, tools, stop_after_tool):
            sections = [{"heading": heading, "text": "This investment lost half its value after two years.", "evidence_ids": ["fact"]}
                        for heading in ("How I read your idea", "The main trade-off", "My research conclusion")]
            with self.assertRaises(ValueError):
                tools[0].handler(takeaway_id="fact", evidence_ids=["fact"], explanations=sections)
            return AgentRun("error", {})
        runtime.run.side_effect = run
        result = await edit_report(plan(), blocks, runtime)
        self.assertNotIn("explanations", result)


if __name__ == "__main__":
    unittest.main()
