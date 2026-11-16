"""Customer workflow, public-source validation and independent financial checks."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun
from datathon.customer_agents import understand, edit_report
from datathon.customer_data import PublicResearch, ResearchUnavailable, StarterResearch, UnavailableResearch
from datathon.customer_workflow import default_provider
from datathon.data import MarketData
from datathon.customer_report import analyze, calculate, review, evidence_blocks, report_html, verify_report
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

    async def test_explicit_ticker_wins_over_model_selected_company_name(self):
        question = "How bad have Tesla (TSLA) losses been? I need the money for retirement."
        runtime = AsyncMock()

        async def run(role, payload, *, tools, stop_after_tool):
            tools[0].handler(mode="research", assets=[{"query": "Tesla", "excerpt": "Tesla", "role": "consider"}],
                conditions=[], budget_text="", currency="", budget_excerpt="", question_to_ask="")
            return AgentRun("ok", {})

        runtime.run.side_effect = run
        result = await understand(question, runtime)
        self.assertEqual(result["assets"], [{"query": "TSLA", "excerpt": "TSLA", "role": "consider"}])

    async def test_disclosure_report_remains_available_without_price_permission(self):
        from datathon.customer_ui import EXAMPLES

        provider = UnavailableResearch("No daily prices configured.")
        expected = {"AI and Bitcoin": ("SPY.disclosure", "IBIT.disclosure"),
            "Growth with ESG preferences": ("ESGU.disclosure", "ESGU-SPY.disclosure"),
            "A stock before retirement": ("TSLA.disclosure",)}
        for name, evidence_ids in expected.items():
            with self.subTest(case=name):
                result = await research_question(EXAMPLES[name], provider=provider)
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["analyses"], [])
                self.assertTrue(set(evidence_ids) <= result["blocks"].keys())
                self.assertTrue(verify_report(result))
                page = report_html(result)
                self.assertNotIn("<svg", page)
                self.assertIn(result["blocks"][evidence_ids[0]]["sources"][0], page)
        self.assertIn("73.39%", result["blocks"]["TSLA.disclosure"]["text"])

    async def test_local_fallback_is_labelled_and_preserves_cash_amount(self):
        result = await understand("i want to invest stock share of amd with 3000 cad", None)
        self.assertEqual(result["origin"], "local")
        self.assertEqual(result["budget"]["amount"], 3000)

    async def test_case_tickers_survive_failed_bedrock_intake(self):
        from datathon.customer_ui import EXAMPLES
        runtime = AsyncMock()
        runtime.run.return_value = AgentRun("error", {})
        expected = [("SPY", "NVDA", "IBIT"), ("ESGU", "SPY"), ("TSLA",)]
        for question, symbols in zip(EXAMPLES.values(), expected, strict=True):
            with self.subTest(symbols=symbols):
                result = await understand(question, runtime)
                self.assertEqual(result["origin"], "local")
                self.assertEqual(result["mode"], "research")
                self.assertEqual(tuple(asset["query"] for asset in result["assets"]), symbols)
                self.assertTrue(all(asset["excerpt"] in question for asset in result["assets"]))

    async def test_fallback_does_not_treat_quoted_advice_as_a_research_request(self):
        result = await understand('My advisor said "Buy Tesla (TSLA)." How do investment risks work?', None)
        self.assertEqual(result["assets"], [])

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

    async def test_comparison_fetches_existing_holding_without_assigning_its_purchase_budget(self):
        from unittest.mock import Mock

        provider = Mock(asset=Mock(side_effect=asset), fx=Mock(return_value=fx()))
        assets = [{"query": "SPY", "excerpt": "SPY", "role": "holding"},
                  {"query": "NVDA", "excerpt": "NVDA", "role": "consider"},
                  {"query": "IBIT", "excerpt": "IBIT", "role": "consider"}]
        planning = {"origin": "local", "checks": [{"tool": "product_comparison"}]}
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan(assets=assets))), \
             patch("datathon.customer_workflow.plan_analysis", AsyncMock(return_value=planning)):
            result = await research_question("I hold SPY and am considering NVDA and IBIT.", provider=provider)
        analysis = {row["asset"]["symbol"]: row for row in result["analyses"]}
        self.assertEqual(set(analysis), {"SPY", "NVDA", "IBIT"})
        self.assertIsNone(analysis["SPY"]["valuation"])
        self.assertIsNotNone(analysis["NVDA"]["valuation"])

    async def test_reports_market_configuration_as_one_issue_for_multiple_symbols(self):
        from datathon.customer_ui import _issues

        question = "Compare ESGU and SPY."
        provider = UnavailableResearch("Daily price history has no source configured.")
        result = await research_question(question, provider=provider)
        issues = [issue for issue in _issues(result) if issue["stage"] == "Source data"]
        self.assertEqual(len(issues), 1)
        self.assertIn("ESGU", issues[0]["reason"])
        self.assertIn("SPY", issues[0]["reason"])
        self.assertIn("app operator", issues[0]["action"])

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


def starter_market():
    prices = "ticker,date,open,high,low,close,adj_close,volume,currency\n"
    fx = {}
    for index in range(30):
        day = (NOW.date() - timedelta(days=40 - index)).isoformat()
        prices += f"SPY,{day},1,1,1,{100 + index},{100 + index},1000,USD\n"
        prices += f"XIU.TO,{day},1,1,1,{30 + index / 10},{30 + index / 10},500,CAD\n"
        fx[day] = 1.35 + index / 1000
    return MarketData({"SPY": {}, "XIU.TO": {}}, fx, ({"file": "prices_daily.csv", "source": "organizer", "source_url": "https://example.org/starter", "retrieved_on": "2026-11-12"},),
                      "starter.zip", official_starter=True, source_csvs=(("prices_daily.csv", prices),))


class StarterFirstTests(unittest.TestCase):
    def test_price_preparation_checks_common_dates_for_all_three_examples(self):
        from hashlib import sha256
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.prepare_price_archive import EXAMPLE_GROUPS, prepare_archive

        with TemporaryDirectory() as temp:
            source = Path(temp)
            output = source / "snapshot.zip"
            observations = asset()["rows"]
            symbols = sorted({symbol for group in EXAMPLE_GROUPS for symbol in group})
            prices = "date,ticker,adj_close,currency\n" + "".join(
                f"{row['date']},{symbol},{row['price']},USD\n"
                for symbol in symbols for row in (observations[10:] if symbol == "IBIT" else observations))
            (source / "prices_daily.csv").write_text(prices, encoding="utf-8")
            (source / "fx_usdcad_daily.csv").write_text("date,usdcad\n" + "".join(
                f"{row['date']},1.4\n" for row in observations), encoding="utf-8")
            (source / "sources_metadata.csv").write_text(
                "file,source,source_url,retrieved_on,terms_of_use,processing,limitations,price_basis\n"
                "prices_daily.csv,Fixture,https://example.org/fixture,2026-11-16,https://example.org/terms,"
                "Split adjustments,Fixture only,split_adjusted_price\n"
                "fx_usdcad_daily.csv,FX fixture,https://example.org/fx,2026-11-16,https://example.org/terms,"
                "CAD per USD,Fixture only,\n", encoding="utf-8")
            digest, coverage = prepare_archive(source, output, verify_examples=True)
            self.assertEqual(digest, sha256(output.read_bytes()).hexdigest())
            self.assertEqual([entry[-1] for entry in coverage], [30, 40, 40])
            (source / "prices_daily.csv").write_text(prices.replace(",IBIT,", ",VTI,"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing example prices for IBIT"):
                prepare_archive(source, output, verify_examples=True)
            self.assertEqual(digest, sha256(output.read_bytes()).hexdigest())

    def test_covered_instrument_comes_from_the_frozen_archive_with_hash(self):
        fallback = PublicResearch(transport=lambda url: (_ for _ in ()).throw(AssertionError("public source must not be called")), clock=lambda: NOW)
        research = StarterResearch(starter_market(), fallback=fallback, clock=lambda: NOW)
        result = research.asset("spy")
        self.assertEqual(result["symbol"], "SPY")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(result["coverage"], "organizer dataset")
        self.assertEqual(len(result["dataset_sha256"]), 64)
        self.assertEqual(result["source_url"], "https://example.org/starter")
        self.assertEqual(len(result["trading"]), 30)
        self.assertEqual(research.fx()["rows"][0]["rate"], 1.35)
        self.assertIn("organizer", research.fx()["source"])

    def test_uncovered_instrument_uses_fallback_and_is_labelled(self):
        payload = PublicSourceTests().payload()
        fallback = PublicResearch(transport=lambda url: payload, clock=lambda: NOW)
        research = StarterResearch(starter_market(), fallback=fallback, clock=lambda: NOW)
        result = research.asset("AMD")
        self.assertEqual(result["source"], "Yahoo Finance")
        self.assertEqual(result["coverage"], "outside organizer dataset; public fallback source")

    def test_without_fallback_the_gap_is_explained_not_invented(self):
        research = StarterResearch(starter_market(), fallback=None, clock=lambda: NOW)
        with self.assertRaises(ResearchUnavailable) as caught:
            research.asset("AMD")
        self.assertIn("AMD is outside the daily price coverage", str(caught.exception))
        self.assertIn("SPY", str(caught.exception))

    def test_workflow_prefers_the_archive_and_can_disable_the_public_source(self):
        import os
        from unittest.mock import patch as patch_env
        with patch_env.dict(os.environ, {}, clear=True):
            self.assertIsNone(default_provider(starter_market()).fallback)
            self.assertIsInstance(default_provider(None), UnavailableResearch)
        with patch_env.dict(os.environ, {"DATATHON_PUBLIC_FALLBACK": "0"}):
            provider = default_provider(starter_market())
            self.assertIsInstance(provider, StarterResearch)
            self.assertIsNone(provider.fallback)
            self.assertIsInstance(default_provider(None), UnavailableResearch)
        with patch_env.dict(os.environ, {"DATATHON_PUBLIC_FALLBACK": "1"}):
            provider = default_provider(starter_market())
            self.assertIsInstance(provider.fallback, PublicResearch)
            self.assertIsInstance(default_provider(None), PublicResearch)

    def test_private_archive_verifies_digest_and_retains_csv_provenance(self):
        from hashlib import sha256
        from io import BytesIO
        from zipfile import ZipFile
        from datathon.hosted_market import HostedArchiveError, load_hosted_market_data

        frozen = starter_market()
        zipped = BytesIO()
        with ZipFile(zipped, "w") as archive:
            archive.writestr("alphaforge_starter/prices_daily.csv", dict(frozen.source_csvs)["prices_daily.csv"])
            archive.writestr("alphaforge_starter/fx_usdcad_daily.csv", "date,usdcad\n" + "\n".join(
                f"{day},{value}" for day, value in frozen.fx.items()))
            archive.writestr("alphaforge_starter/sources_metadata.csv",
                "file,source,source_url,retrieved_on,terms_of_use\n"
                "prices_daily.csv,Fixture,https://example.org/data,2026-11-12,https://example.org/terms\n")
        payload = zipped.getvalue()
        client = unittest.mock.Mock()
        client.get_object.side_effect = lambda **_: {"Body": BytesIO(payload), "ContentLength": len(payload)}
        uri = "s3://private-data/prices.zip"
        market = load_hosted_market_data(uri, sha256(payload).hexdigest(), "us-east-1", client=client)
        client.get_object.assert_called_once_with(Bucket="private-data", Key="prices.zip")
        self.assertEqual(market.source_path, "")
        self.assertFalse(market.official_starter)
        self.assertEqual(StarterResearch(market).asset("SPY")["terms_url"], "https://example.org/terms")
        with self.assertRaisesRegex(HostedArchiveError, "SHA-256"):
            load_hosted_market_data(uri, "0" * 64, "us-east-1", client=client)

    def test_end_to_end_report_from_archive_only(self):
        provider = StarterResearch(starter_market(), fallback=None, clock=lambda: NOW)
        request = "I am considering 3000 CAD in SPY."
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan(assets=[{"query": "SPY", "excerpt": "SPY", "role": "consider"}]))):
            report = asyncio.run(research_question(request, provider=provider))
        self.assertTrue(report["analyses"])
        self.assertEqual(report["analyses"][0]["asset"]["source"], StarterResearch.SOURCE)
        self.assertIsNotNone(report["fx"])


class StarterMergeSafetyTests(unittest.TestCase):
    def test_raw_close_is_used_for_sizing_and_adjusted_close_for_history(self):
        market=starter_market()
        name,prices=market.source_csvs[0]
        prices=prices.replace(',129,129,1000,USD', ',258,129,1000,USD')
        from dataclasses import replace
        source=StarterResearch(replace(market, source_csvs=((name,prices),)),clock=lambda:NOW)
        found=source.asset('SPY')
        self.assertEqual(found['price'],258.)
        self.assertEqual(found['rows'][-1]['price'],129.)
        self.assertEqual(found['price_field'],'close')

    def test_adjusted_only_archive_withholds_share_sizing(self):
        from dataclasses import replace
        import csv,io
        market=starter_market();name,prices=market.source_csvs[0]
        rows=list(csv.DictReader(io.StringIO(prices)))
        output=io.StringIO();fields=['ticker','date','adj_close','currency']
        writer=csv.DictWriter(output,fieldnames=fields,lineterminator='\n');writer.writeheader()
        writer.writerows({k:row[k] for k in fields} for row in rows)
        source=StarterResearch(replace(market,source_csvs=((name,output.getvalue()),)),clock=lambda:NOW)
        found=source.asset('SPY')
        self.assertEqual(found['price_field'],'adj_close')
        self.assertIsNone(analyze([found],{'amount':3000.,'currency':'USD'})[0]['valuation'])

    def test_public_name_resolution_retains_archive_price_precedence(self):
        from unittest.mock import Mock
        fallback=Mock()
        fallback.resolve_security.return_value={'symbol':'SPY','query':'SPDR fund'}
        source=StarterResearch(starter_market(),fallback=fallback,clock=lambda:NOW)
        result=source.asset('SPDR fund')
        self.assertEqual(result['source'],StarterResearch.SOURCE)
        self.assertEqual(result['resolution']['query'],'SPDR fund')
        fallback.asset.assert_not_called()

    def test_fallback_coverage_metadata_matches_its_digest(self):
        from datathon.review_snapshot import fingerprint
        fallback=PublicResearch(transport=lambda url:PublicSourceTests().payload(),clock=lambda:NOW)
        found=StarterResearch(starter_market(),fallback=fallback,clock=lambda:NOW).asset('AMD')
        self.assertEqual(found['digest'],fingerprint({k:v for k,v in found.items() if k!='digest'}))
