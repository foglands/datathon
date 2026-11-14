"""Verify coverage reporting and isolation from audit decisions."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from datathon.starter_quality import inventory_starter


FIXTURE = {
    "assets_universe.csv": (
        "asset_id,ticker,name,asset_class,market,currency,sector\n"
        "A1,SPY,US equity,etf_equity,NYSE,USD,Equity\n"
        "A2,ZST.TO,Short bonds,etf_bond,TSX,CAD,Bond\n"
        "A3,XIU.TO,Canadian equity,etf_equity,TSX,CAD,Equity\n"
        "A4,QQQ,US growth,etf_equity,NASDAQ,USD,Equity\n"
        "A5,NVDA,NVIDIA,equity,NASDAQ,USD,Technology\n"
    ),
    "prices_daily.csv": "date,ticker,open,high,low,close,adj_close,volume,currency\n" + "".join(
        f"{day},{ticker},10,10,10,10,10,{volume},{currency}\n"
        for day in ("2021-12-31", "2022-09-30", "2022-12-30")
        for ticker, currency, volume in (
            ("SPY", "USD", 20), ("ZST.TO", "CAD", 0), ("XIU.TO", "CAD", 20),
            ("QQQ", "USD", 20), ("NVDA", "USD", 20),
        )
    ),
    "fx_usdcad_daily.csv": "date,usdcad,cadusd\n2021-12-31,1.25,0.8\n2022-12-30,1.25,0.8\n",
    "corporate_actions.csv": (
        "ex_date,ticker,action,value,unit\n2022-09-30,ZST.TO,dividend,0.1,CAD per share\n"
        "2024-06-10,NVDA,split,10.0,split ratio (new:old)\n"
    ),
    "macro_rates.csv": (
        "date,series_id,value,unit,frequency,label,source\n"
        "2022-09-01,CPIAUCSL,300,index,monthly,US CPI,FRED\n"
    ),
    "sources_metadata.csv": (
        "file,content,source,source_url,retrieved_on,coverage,frequency,processing,limitations,terms_of_use\n"
        "macro_rates.csv,CPI,FRED,https://fred.stlouisfed.org,2026-11-13,n/a,monthly,long,Latest vintage,n/a\n"
    ),
    "data_quality_warnings.txt": "No warnings.",
}


class StarterQualityTests(unittest.TestCase):
    def test_calendar_intersection_uses_valid_fixings_and_never_fills_gaps(self):
        with patch("datathon.starter_quality._documents", return_value=FIXTURE), \
                patch("datathon.starter_quality._starter_path", return_value=Path("fixture")):
            report = inventory_starter()
        first, second = report["replay_windows"]
        self.assertEqual((first["common_price_days"], first["common_price_and_fx_days"]), (3, 2))
        self.assertEqual(first["common_price_dates_without_fx"], ["2022-09-30"])
        self.assertTrue(all(first["endpoints_present_after_alignment"].values()))
        self.assertFalse(any(second["endpoints_present_after_alignment"].values()))
        self.assertEqual(report["universe"]["assets"]["SPY"]["valid_price_dates_without_fx"], 1)
        self.assertIsNone(report["universe"]["assets"]["XIU.TO"]["valid_price_dates_without_fx"])
        self.assertEqual(first["portfolio_dividend_rows_by_asset"], {"ZST.TO": 1})
        self.assertFalse(first["portfolio_split_rows"])
        self.assertTrue(report["organizer_build_warnings"]["available"])
        self.assertIn("Descriptive provenance only", report["macro"]["use"])
        self.assertNotIn("verdict", report)

    @unittest.skipUnless(os.getenv("DATATHON_FULL_STARTER_PATH"), "Set the path to all six official CSV tables.")
    def test_full_official_snapshot_counts_and_caveats(self):
        report = inventory_starter(os.environ["DATATHON_FULL_STARTER_PATH"])
        self.assertEqual({name: table["rows"] for name, table in report["tables"].items()}, {
            "assets_universe.csv": 31, "prices_daily.csv": 40049, "fx_usdcad_daily.csv": 1245,
            "corporate_actions.csv": 658, "macro_rates.csv": 8281, "sources_metadata.csv": 6,
        })
        first, second = report["replay_windows"]
        self.assertEqual((first["common_price_days"], first["common_price_and_fx_days"]), (246, 244))
        self.assertEqual(first["common_price_dates_without_fx"], ["2022-09-30", "2022-11-11"])
        self.assertEqual((second["common_price_days"], second["common_price_and_fx_days"]), (67, 67))
        self.assertTrue(all(all(window["endpoints_present_after_alignment"].values()) for window in (first, second)))
        self.assertEqual(report["prices"]["zero_volume_rows"], [{"ticker": "ZST.TO", "date": "2022-07-06"}])
        self.assertEqual(report["corporate_actions"]["event_type_counts"], {"dividend": 651, "split": 7})
        self.assertEqual(report["corporate_actions"]["same_day_split_and_dividend_rows"][0]["split_row"]["ticker"], "CNQ.TO")
        self.assertEqual(len(report["macro"]["series"]), 9)
        self.assertEqual(len(report["source_metadata"]), 6)
