"""Check CAD adjusted closes against their original quotes and dated fixings."""

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from datathon.data import MarketData, MarketProvenanceError, load_market_data, market_data_source, verify_cad_conversion
from datathon.finance import StressWindow


START = "2026-01-05"
MISSING_FX = "2026-01-06"
END = "2026-01-07"
WINDOW = StressWindow("test", "CAD conversion test", START, END)


class MarketProvenanceTests(unittest.TestCase):
    def setUp(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "prices_daily.csv").write_text(
                "ticker,date,close,adj_close,currency\n"
                f"ABC,{START},200,100,USD\n"
                f"ABC,{MISSING_FX},180,90,USD\n"
                f"ABC,{END},240,120,USD\n"
                f"ABC.TO,{START},80,40,CAD\n"
                f"ABC.TO,{MISSING_FX},90,45,CAD\n"
                f"ABC.TO,{END},100,50,CAD\n",
                encoding="utf-8",
            )
            (path / "fx_usdcad_daily.csv").write_text(
                f"date,usdcad,cadusd\n{START},1.25,0.8\n{END},1.5,0.666667\n", encoding="utf-8"
            )
            (path / "sources_metadata.csv").write_text(
                "file,source,source_url,retrieved_on\n"
                "prices_daily.csv,Fixture,https://example.com/prices,2026-01-08\n"
                "fx_usdcad_daily.csv,Fixture,https://example.com/fx,2026-01-08\n",
                encoding="utf-8",
            )
            self.market = load_market_data(path)

    def check(self, market=None):
        return verify_cad_conversion(market or self.market, tickers=("ABC", "ABC.TO"), windows=(WINDOW,))

    def test_rebuilds_exact_date_fx_and_preserves_cad_adjusted_closes(self):
        self.assertEqual(self.market.prices["ABC"], {START: 125, END: 180})
        self.assertEqual(self.market.prices["ABC.TO"], {START: 40, MISSING_FX: 45, END: 50})
        verification = self.check()
        self.assertEqual(verification["status"], "verified")
        self.assertEqual(verification["price_field"], "adj_close")
        self.assertEqual(len(verification["source_sha256"]["prices_daily.csv"]), 64)
        self.assertEqual(verification["windows"]["test"], {
            "observations": 2, "price_observations": 4, "missing_fx_dates": [MISSING_FX],
        })

    def test_rejects_inverted_shifted_and_repeated_price_transforms(self):
        for label, ticker, price in (
            ("inverse fixing", "ABC", 120 / 1.5),
            ("prior fixing", "ABC", 120 * 1.25),
            ("duplicate FX", "ABC", 180 * 1.5),
            ("raw close used instead of adjusted", "ABC", 240 * 1.5),
            ("double corporate action adjustment", "ABC", 180 * 2),
            ("CAD position converted", "ABC.TO", 50 * 1.5),
        ):
            with self.subTest(label=label):
                prices = {**self.market.prices, ticker: {**self.market.prices[ticker], END: price}}
                with self.assertRaisesRegex(MarketProvenanceError, f"CAD adjusted close for {ticker}"):
                    self.check(replace(self.market, prices=prices))

    def test_rejects_altered_fixing_even_when_cad_prices_are_unchanged(self):
        with self.assertRaisesRegex(MarketProvenanceError, "USD/CAD fixing"):
            self.check(replace(self.market, fx={**self.market.fx, END: 0.666667}))

    def test_rejects_extra_replay_date_and_altered_source_metadata(self):
        prices = {**self.market.prices, "ABC": {**self.market.prices["ABC"], MISSING_FX: 112.5}}
        with self.assertRaisesRegex(MarketProvenanceError, "replay dates"):
            self.check(replace(self.market, prices=prices, fx={**self.market.fx, MISSING_FX: 1.25}))
        with self.assertRaisesRegex(MarketProvenanceError, "metadata"):
            self.check(replace(self.market, metadata=()))

    def test_requires_provenance_for_loaded_market_with_fixture_compatibility(self):
        self.assertEqual(self.check(MarketData(self.market.prices, self.market.fx))["status"], "not_applicable")
        with self.assertRaisesRegex(MarketProvenanceError, "no frozen"):
            self.check(replace(self.market, source_csvs=()))

    def test_rejects_duplicate_and_invalid_source_observations(self):
        raw = dict(self.market.source_csvs)
        originals = raw["prices_daily.csv"]
        for label, source, message in (
            ("duplicate", originals + f"ABC,{START},200,100,USD\n", "duplicate price key"),
            ("malformed row", originals + "ABC\n", "Malformed CSV row"),
            ("nonpositive close", originals.replace("200,100", "200,0"), "Invalid ABC adjusted close"),
            ("NaN close", originals.replace("200,100", "200,NaN"), "Invalid ABC adjusted close"),
            ("infinite close", originals.replace("200,100", "200,inf"), "Invalid ABC adjusted close"),
        ):
            with self.subTest(label=label):
                with patch("datathon.data._csv_texts", return_value={**raw, "prices_daily.csv": source}):
                    with self.assertRaisesRegex(ValueError, message):
                        load_market_data(__file__)

    def test_resolves_exact_extracted_source_and_detects_csv_changes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            starter = path / "Datathon2026" / "alphaforge_starter"
            starter.mkdir(parents=True)
            for name, contents in self.market.source_csvs:
                (starter / name).write_text(contents, encoding="utf-8")
            selected, version = market_data_source(path)
            self.assertEqual(selected, starter.resolve())
            self.assertEqual(market_data_source(selected), (selected, version))
            self.assertEqual(load_market_data(path).source_csvs, load_market_data(selected).source_csvs)

            metadata = starter / "sources_metadata.csv"
            metadata.write_text(metadata.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertNotEqual(market_data_source(path)[1], version)

    def test_archive_version_changes_when_replaced(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "starter.zip"
            with ZipFile(path, "w") as archive:
                for name, contents in self.market.source_csvs:
                    archive.writestr(f"Datathon2026/alphaforge_starter/{name}", contents)
            selected, version = market_data_source(path)
            self.assertEqual(selected, path.resolve())
            self.assertEqual(load_market_data(selected).source_csvs, self.market.source_csvs)

            with ZipFile(path, "a") as archive:
                archive.writestr("updated.txt", "Updated source archive.")
            self.assertNotEqual(market_data_source(path)[1], version)
