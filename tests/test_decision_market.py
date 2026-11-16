"""Check the general decision market panel against frozen price and FX inputs."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from datathon.data import load_market_data
from datathon.decision_market import MarketDecisionEvidenceError, prepare_market


class DecisionMarketTests(unittest.TestCase):
    def setUp(self):
        self.market = self._load(
            "XIU.TO,2025-01-02,20,CAD\n"
            "XIU.TO,2025-01-03,21,CAD\n"
            "XIU.TO,2025-01-06,19,CAD\n"
            "NVDA,2025-01-02,100,USD\n"
            "NVDA,2025-01-03,120,USD\n"
            "NVDA,2025-01-06,80,USD\n",
            "2025-01-02,1.4\n2025-01-06,1.25\n",
        )

    def _load(self, prices, fixings, *, coverage="2024-12-31 to 2025-04-08"):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "prices_daily.csv").write_text("ticker,date,adj_close,currency\n" + prices, encoding="utf-8")
            (path / "fx_usdcad_daily.csv").write_text("date,usdcad\n" + fixings, encoding="utf-8")
            (path / "sources_metadata.csv").write_text(
                "file,source,source_url,retrieved_on,coverage\n"
                f"prices_daily.csv,Fixture,https://example.com/prices,2025-04-09,{coverage}\n"
                f"fx_usdcad_daily.csv,Fixture,https://example.com/fx,2025-04-09,{coverage}\n",
                encoding="utf-8",
            )
            return load_market_data(path)

    def _upload(self, data, **overrides):
        options = {"upload_source": "https://example.com/adjusted-close", "upload_published_on": "2025-04-08"}
        return prepare_market(self.market, ("AMD",), upload=data, **(options | overrides))

    def test_same_day_fx_local_panel_and_exact_source_line(self):
        result = prepare_market(self.market, ("XIU.TO", "NVDA"))
        full = result["windows"]["full_history"]
        self.assertEqual(result["knowledge_date"], "2025-04-09")
        self.assertEqual(full["dates"], ["2025-01-02", "2025-01-06"])
        self.assertEqual(full["local_prices"], {"NVDA": [100.0, 80.0], "XIU.TO": [20.0, 19.0]})
        self.assertEqual(full["cad_prices"], {"NVDA": [140.0, 100.0], "XIU.TO": [20.0, 19.0]})
        self.assertEqual(full["coverage"]["missing_fx_dates"], ["2025-01-03"])
        self.assertEqual(full["coverage"]["status"], "coverage_not_verified")
        self.assertEqual(result["provenance"]["price_rows"]["NVDA"]["2025-01-06"], {
            "source_file": "prices_daily.csv", "line": 7, "adj_close": "80", "currency": "USD",
            "fx_source_file": "fx_usdcad_daily.csv", "fx_line": 3, "usdcad": "1.25",
        })
        self.assertEqual(set(result["excluded"]), {"2022", "2025"})
        self.assertEqual(
            result["provenance"]["input_digest"],
            prepare_market(self.market, ("NVDA", "XIU.TO"))["provenance"]["input_digest"],
        )

    def test_cad_only_keeps_prices_from_dates_without_fx(self):
        result = prepare_market(self.market, ("XIU.TO",), custom_start="2025-01-01", custom_end="2025-01-04")
        custom = result["windows"]["custom"]
        self.assertEqual(custom["start"], "2025-01-01")
        self.assertEqual(custom["dates"], ["2025-01-02", "2025-01-03"])
        self.assertEqual(custom["coverage"]["missing_fx_dates"], [])
        self.assertEqual(result["windows"]["full_history"]["dates"][-1], "2025-01-06")

    def test_missing_symbol_can_be_supplied_with_qualified_immutable_upload(self):
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            prepare_market(self.market, ("AMD", "NVDA"))
        self.assertEqual(caught.exception.reason, "missing_tickers")
        self.assertEqual(caught.exception.details["tickers"], ["AMD"])

        upload = bytearray(b"ticker,date,adj_close,currency\r\nAMD,2025-01-02,123.4,USD\r\nAMD,2025-01-06,112.2,USD\r\n")
        digest = sha256(upload).hexdigest()
        result = self._upload(upload)
        upload[-3] = ord("X")
        evidence = result["provenance"]
        self.assertEqual(evidence["source_sha256"]["uploaded_prices.csv"], digest)
        self.assertEqual(evidence["price_rows"]["AMD"]["2025-01-02"]["line"], 2)
        self.assertAlmostEqual(result["windows"]["full_history"]["cad_prices"]["AMD"][0], 123.4 * 1.4)
        self.assertEqual(evidence["source_metadata"]["uploaded_prices.csv"]["published_on"], "2025-04-08")

    def test_knowledge_cutoff_qualifies_publication_and_retrieval_separately(self):
        upload = "ticker,date,adj_close,currency\nAMD,2025-01-02,20,CAD\nAMD,2025-01-06,25,CAD\n"
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            self._upload(upload, knowledge_date="2025-04-07")
        self.assertEqual(caught.exception.reason, "source_after_knowledge_date")
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            prepare_market(self.market, ("NVDA",), knowledge_date="2025-04-08")
        self.assertEqual(caught.exception.reason, "source_after_knowledge_date")
        result = self._upload(upload, knowledge_date="2025-04-08")
        self.assertEqual(result["windows"]["full_history"]["cad_prices"], {"AMD": [20.0, 25.0]})
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            self._upload(upload.replace(",CAD", ",USD"), knowledge_date="2025-04-08")
        self.assertEqual(caught.exception.reason, "no_usable_window")
        self.assertIn("USD/CAD snapshot", str(caught.exception))

    def test_rejects_malformed_upload_and_future_observations(self):
        header = "ticker,date,adj_close,currency\n"
        cases = (
            (header + "AMD,2025-01-02,0,CAD\n", {}),
            (header + "AMD,2025-01-02,NaN,CAD\n", {}),
            (header + "AMD,2025-04-09,10,CAD\n", {}),
            (header + "AMD,2025-01-02,10,CAD\nAMD,2025-01-02,12,CAD\n", {}),
            (header + "AMD,2025-01-02,10,CAD\nAMD,2025-01-03,12,USD\n", {}),
            (header + "AMD,2025-01-02,10,CAD,extra\n", {}),
            (header + "AMD,2025-01-02,10,CAD\n", {"upload_source": "javascript:alert(1)"}),
            (header + "AMD,2025-01-02,10,CAD\n", {"upload_published_on": None}),
        )
        for content, options in cases:
            with self.subTest(content=content, options=options), self.assertRaises(MarketDecisionEvidenceError) as caught:
                self._upload(content, **options)
            self.assertEqual(caught.exception.reason, "invalid_upload")

    def test_loaded_prices_and_float_conversion_are_independently_checked(self):
        altered = replace(self.market, prices={**self.market.prices, "NVDA": {"2025-01-02": 142, "2025-01-06": 100}})
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            prepare_market(altered, ("NVDA",))
        self.assertEqual(caught.exception.reason, "price_mismatch")
        with patch("datathon.decision_market._converted_prices", return_value={"NVDA": {"2025-01-02": 100.0,
                                                                                       "2025-01-06": 80.0}}):
            with self.assertRaisesRegex(MarketDecisionEvidenceError, "differs from its source"):
                prepare_market(self.market, ("NVDA",))
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            prepare_market(replace(self.market, source_csvs=()), ("NVDA",))
        self.assertEqual(caught.exception.reason, "corrupt_official_evidence")
        altered_fx = replace(self.market, fx={**self.market.fx, "2025-01-02": 1 / 1.4})
        with self.assertRaises(MarketDecisionEvidenceError) as caught:
            prepare_market(altered_fx, ("NVDA",))
        self.assertEqual(caught.exception.reason, "fx_mismatch")

    def test_organizer_series_remains_on_its_own_adjustment_basis(self):
        upload = "ticker,date,adj_close,currency\nNVDA,2025-01-02,500,USD\nNVDA,2025-01-06,600,USD\n"
        result = prepare_market(self.market, "NVDA", upload=upload, upload_source="https://example.com/prices",
                                upload_published_on="2025-04-10")
        self.assertEqual(result["knowledge_date"], "2025-04-10")
        self.assertEqual(result["windows"]["full_history"]["local_prices"], {"NVDA": [100.0, 80.0]})
        self.assertIn("organizer series was retained for NVDA", result["provenance"]["limitations"][-1])

    def test_pinned_calendar_reports_internal_gaps_and_does_not_apply_to_cad_only(self):
        market = self._load(
            "NVDA,2024-12-31,21,USD\nNVDA,2025-01-06,23,USD\nNVDA,2025-04-08,24,USD\n"
            "XIU.TO,2024-12-31,31,CAD\nXIU.TO,2025-01-06,33,CAD\nXIU.TO,2025-04-08,34,CAD\n",
            "2024-12-31,1.45\n2025-01-06,1.45\n2025-04-08,1.41\n",
        )
        checked = prepare_market(market, ("NVDA", "XIU.TO"))["windows"]["2025"]["coverage"]
        self.assertEqual(checked["status"], "incomplete")
        self.assertIn({"date": "2025-01-02", "reason": "missing_prices_and_fx"}, checked["missing_dates"])
        self.assertIn({"date": "2025-01-09", "reason": "documented_exchange_closure"}, checked["excluded_dates"])
        unknown = prepare_market(market, ("XIU.TO",))["windows"]["2025"]["coverage"]
        self.assertEqual(unknown["status"], "coverage_not_verified")
        self.assertIn({"start": "2025-01-01", "end": "2025-01-03", "weekdays": 3},
                      unknown["by_ticker"]["XIU.TO"]["unverified_weekday_gaps"])

    def test_crypto_raw_utc_gap_is_known_separately_from_joint_cad_calendar(self):
        market = self._load("BTC-USD,2025-01-03,21,USD\nBTC-USD,2025-01-05,22,USD\nBTC-USD,2025-01-06,23,USD\n",
                            "2025-01-03,1.45\n2025-01-06,1.45\n", coverage="2025-01-03 to 2025-01-06")
        coverage = prepare_market(market, ("BTC-USD",))["windows"]["full_history"]["coverage"]
        self.assertEqual(coverage["status"], "incomplete")
        self.assertIsNone(coverage["calendar_id"])
        self.assertEqual(coverage["by_ticker"]["BTC-USD"]["missing_expected_raw_dates"], ["2025-01-04"])
        self.assertEqual(coverage["missing_fx_dates"], ["2025-01-05"])

    def test_constant_local_quotes_isolate_fx_and_never_reconvert_cad(self):
        market = self._load(
            "FOREIGN,2025-01-02,100,USD\nFOREIGN,2025-01-03,100,USD\n"
            "DOMESTIC,2025-01-02,100,CAD\nDOMESTIC,2025-01-03,100,CAD\n",
            "2025-01-02,1.4\n2025-01-03,1.5\n",
        )
        full = prepare_market(market, ("FOREIGN", "DOMESTIC"))["windows"]["full_history"]
        self.assertEqual(full["cad_prices"]["FOREIGN"], [140, 150])
        self.assertEqual(full["cad_prices"]["DOMESTIC"], [100, 100])
        self.assertEqual(full["local_prices"]["FOREIGN"], [100, 100])
