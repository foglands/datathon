"""Verify attribution bounds and sector evidence scope independently of models."""

import json
import os
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from datathon.finance import BASE_WEIGHTS
from datathon.sector import sector_analysis, shared_exposure_change


def reviewed_row(ticker, **changes):
    return {
        "ticker": ticker, "taxonomy": "GICS", "version": "example-v1",
        "as_of": "2026-09-01", "available_by": "2026-09-02",
        "source_url": "https://example.com/segment-report", "source_locator": "Synthetic test, section 2",
        "denominator": "nav", "weights": {"Energy": 0.4},
        **changes,
    }


class SectorEvidenceTests(unittest.TestCase):
    def setUp(self):
        configuration = patch.dict(os.environ)
        configuration.start()
        self.addCleanup(configuration.stop)
        os.environ.pop("DATATHON_SECTOR_CATALOG", None)
        os.environ.pop("DATATHON_SECTOR_CATALOG_SHA256", None)

    def set_catalog(self, *rows):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "sector.json"
        data = json.dumps({"taxonomy": "GICS", "version": "example-v1", "records": rows}).encode()
        path.write_bytes(data)
        configuration = patch.dict("os.environ", DATATHON_SECTOR_CATALOG=str(path),
                                   DATATHON_SECTOR_CATALOG_SHA256=sha256(data).hexdigest())
        configuration.start()
        self.addCleanup(configuration.stop)
        return path

    def test_signed_change_cancels_unchanged_unknown(self):
        first = {"unmapped": 0.2, "reserve": 0.8}
        second = {"unmapped": 0.2, "reserve": 0.7, "direct": 0.1}
        change = shared_exposure_change(first, second, {"reserve": (0, 0.5), "direct": 1.0})
        self.assertAlmostEqual(change["lower"], 0.05)
        self.assertAlmostEqual(change["upper"], 0.10)
        reverse = shared_exposure_change(second, first, {"reserve": (0, 0.5), "direct": 1.0})
        self.assertAlmostEqual(reverse["lower"], -0.10)
        self.assertAlmostEqual(reverse["upper"], -0.05)

    def test_default_technology_change_and_unknown_mass(self):
        before = BASE_WEIGHTS
        after = {**before, "NVDA": 0.10, "ZST.TO": 0.10}
        report = sector_analysis(before, after)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["denominator"], "portfolio_value")
        technology = report["sectors"]["Information Technology"]
        self.assertAlmostEqual(technology["before"]["lower"], 0)
        self.assertAlmostEqual(technology["after"]["lower"], 0.10)
        self.assertAlmostEqual(technology["change"]["lower"], 0.0837)
        self.assertAlmostEqual(technology["change"]["upper"], 0.10)
        self.assertAlmostEqual(report["unmapped"]["after"], 0.8163)
        self.assertEqual(set(report["evidence"]), {"NVDA", "ZST.TO"})
        self.assertEqual(report["ignored"]["QQQ"], "unavailable")

    def test_equity_sleeve_denominator_and_taxonomy_cutoffs(self):
        self.set_catalog(
            reviewed_row("ETF", denominator="equity_sleeve", equity_fraction=0.8),
            reviewed_row("ICB", taxonomy="ICB"),
            reviewed_row("STALE", as_of="2025-12-01", available_by="2026-01-01"),
            reviewed_row("FUTURE", as_of="2026-11-13", available_by="2026-11-15"),
        )
        weights = {"ETF": 0.2, "ICB": 0.2, "STALE": 0.2, "FUTURE": 0.2, "OTHER": 0.2}
        report = sector_analysis(weights, weights)
        self.assertAlmostEqual(report["sectors"]["Energy"]["before"]["lower"], 0.064)
        self.assertAlmostEqual(report["sectors"]["Energy"]["before"]["upper"], 0.96)
        self.assertEqual(report["sectors"]["Energy"]["change"], {"lower": 0.0, "upper": 0.0})
        self.assertAlmostEqual(report["unmapped"]["before"], 0.896)
        self.assertEqual(report["ignored"], {"FUTURE": "outside_evidence_cutoff", "ICB": "taxonomy_mismatch",
                                             "OTHER": "unavailable", "STALE": "stale_evidence"})

    def test_wrong_denominator_and_catalog_tampering_are_rejected(self):
        path = self.set_catalog(reviewed_row("ETF", denominator="equity_sleeve"))
        with self.assertRaisesRegex(ValueError, "catalog is invalid"):
            sector_analysis({"ETF": 1.0}, {"ETF": 1.0})
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "size or content check"):
            sector_analysis({"ETF": 1.0}, {"ETF": 1.0})

    def test_later_public_material_does_not_resolve_earlier_decision(self):
        weights = {"NVDA": 0.5, "ZST.TO": 0.5}
        report = sector_analysis(weights, weights, publication_cutoff="2026-11-13")
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["unmapped"], {"before": 1.0, "after": 1.0})
