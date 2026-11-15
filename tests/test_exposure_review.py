"""Known answers and tamper tests for the independent optional reviews."""

import json
import os
import tempfile
import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from datathon.evidence import ISSUER_SCOPE
from datathon.exposure_review import review_issuer_change, review_sector_analysis
from datathon.finance import BASE_WEIGHTS
from datathon.sector import load_sector_catalog, sector_analysis, shared_exposure_change


class ExposureReviewTests(unittest.TestCase):
    def setUp(self):
        configuration = patch.dict(os.environ)
        configuration.start()
        self.addCleanup(configuration.stop)
        for setting in ("DATATHON_SECTOR_CATALOG", "DATATHON_SECTOR_CATALOG_SHA256",
                        "DATATHON_ISSUER_CATALOG", "DATATHON_ISSUER_CATALOG_SHA256"):
            os.environ.pop(setting, None)

    def set_catalog(self, **changes):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "sector.json"
        record = {
            "ticker": "ETF", "taxonomy": "GICS", "version": "example-v1",
            "as_of": "2026-09-01", "available_by": "2026-09-02",
            "source_url": "https://example.com/fund-report", "source_locator": "Section 2",
            "denominator": "equity_sleeve", "weights": {"Energy": 0.4}, "equity_fraction": 0.8,
            **changes,
        }
        source = json.dumps({"taxonomy": "GICS", "version": "example-v1", "records": [record]}).encode()
        path.write_bytes(source)
        os.environ.update(DATATHON_SECTOR_CATALOG=str(path), DATATHON_SECTOR_CATALOG_SHA256=sha256(source).hexdigest())
        return path

    def test_recomputes_sector_lower_upper_and_signed_change(self):
        after = {**BASE_WEIGHTS, "NVDA": 0.10, "ZST.TO": 0.10}
        claimed = sector_analysis(BASE_WEIGHTS, after)
        result = review_sector_analysis(claimed, BASE_WEIGHTS, after)
        self.assertEqual(result["status"], "verified")
        self.assertIsNot(result["verified"], claimed)
        verified = result["verified"]["sectors"]["Information Technology"]
        self.assertEqual(verified["after"], {"lower": 0.10, "upper": 0.9003492803142248})
        self.assertEqual(verified["change"], {"lower": 0.09965071968577517, "upper": 0.10})
        self.assertEqual(result["verified"]["unmapped"]["after"], 0.8003492803142248)
        evidence = result["verified"]["evidence"]["ZST.TO"]
        self.assertEqual(evidence["non_equity_nav_lower"], 0.9965071968577517)
        self.assertEqual(evidence["non_equity_derivation"], {
            "method": "fair_value_nav_display_envelope",
            "formula": "max(0, reported_fair_value - 1) / (reported_net_assets + 1)",
            "reported_fair_value": 4_144_027,
            "reported_net_assets": 4_158_550,
            "display_unit": 1_000,
            "currency": "CAD",
        })

    def test_checks_equity_sleeve_denominator_and_keeps_one_catalog(self):
        path = self.set_catalog()
        catalog = load_sector_catalog()
        # Existing audit can continue with its reviewed snapshot; loading the
        # later changed source for a new audit must fail its pin.
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "size or content check"):
            load_sector_catalog()
        with self.assertRaises(TypeError):
            catalog[1][0].weights["Energy"] = 0.5
        before = {"ETF": 0.2, "UNMAPPED": 0.8}
        claimed = sector_analysis(before, before, catalog=catalog)
        verified = review_sector_analysis(claimed, before, before, catalog=catalog)["verified"]
        self.assertEqual(verified["sectors"]["Energy"]["before"]["lower"], 0.064)
        self.assertEqual(verified["sectors"]["Energy"]["change"], {"lower": 0.0, "upper": 0.0})
        self.assertEqual(verified["evidence"]["ETF"]["sector_nav_lower"]["Energy"], 0.32)
        claimed["sectors"]["Energy"]["before"]["lower"] = 0.08
        self.assertEqual(review_sector_analysis(claimed, before, before, catalog=catalog)["status"], "invalid")

    def test_rejects_fabricated_bounds_taxonomy_and_unknown_share(self):
        after = {**BASE_WEIGHTS, "NVDA": 0.10, "ZST.TO": 0.10}
        original = sector_analysis(BASE_WEIGHTS, after)
        for path, value in (
            (("sectors", "Information Technology", "after", "lower"), 0.99),
            (("sectors", "Information Technology", "change", "upper"), 0.00),
            (("taxonomy", "version"), "unverified"),
            (("unmapped", "after"), 0.10),
            (("evidence", "ZST.TO", "as_of"), "2026-11-15"),
            (("evidence", "ZST.TO", "non_equity_derivation", "reported_net_assets"), 4_000_000),
            (("evidence", "ZST.TO", "non_equity_derivation", "display_unit"), 1),
        ):
            with self.subTest(path=path):
                candidate = deepcopy(original)
                current = candidate
                for key in path[:-1]:
                    current = current[key]
                current[path[-1]] = value
                failure = review_sector_analysis(candidate, BASE_WEIGHTS, after)
                self.assertEqual(failure, {"status": "invalid", "reason": "sector_calculation_mismatch"})

    def test_checks_publication_cutoff_and_restricts_no_evidence(self):
        self.set_catalog(available_by="2026-11-15")
        weights = {"ETF": 1.0}
        claimed = sector_analysis(weights, weights)
        self.assertEqual(claimed["ignored"], {"ETF": "outside_evidence_cutoff"})
        verification = review_sector_analysis(claimed, weights, weights)
        self.assertEqual(verification, {"status": "unavailable", "reason": "no_qualifying_sector_evidence"})
        claimed["unmapped"]["after"] = 0
        self.assertEqual(review_sector_analysis(claimed, weights, weights)["status"], "invalid")

    def test_requalifies_issuer_disclosure_and_cancels_unchanged_unknowns(self):
        raw_snapshot = {
            "scope": ISSUER_SCOPE, "as_of": "2026-10-31",
            "holdings": {"ETF": {"status": "disclosed", "published_on": "2026-11-02", "weight": 0.25,
                                 "url": "https://example.com/fund-report"}},
        }
        context = {"reference_date": "2026-11-14", "publication_cutoff": "2026-11-14", "max_age_days": 180}
        before = {"ETF": 0.2, "UNMAPPED": 0.8}
        after = {"ETF": 0.1, "UNMAPPED": 0.8, "NVDA": 0.1}
        claim = shared_exposure_change(before, after, {"ETF": 0.25, "NVDA": 1.0})
        verified = review_issuer_change(claim, before, after, raw_snapshot=raw_snapshot, issuer_context=context)
        self.assertEqual(verified, {"status": "verified", "verified": {"lower": 0.075, "upper": 0.075}})
        claim["upper"] = 0.99
        verification = review_issuer_change(claim, before, after, raw_snapshot=raw_snapshot, issuer_context=context)
        self.assertEqual(verification, {"status": "invalid", "reason": "issuer_change_mismatch"})

        context["publication_cutoff"] = "2026-11-01"
        verify_unknown = review_issuer_change(
            {"lower": 0.0, "upper": 0.10}, before, after, raw_snapshot=raw_snapshot, issuer_context=context,
        )
        self.assertEqual(verify_unknown, {"status": "verified", "verified": {"lower": 0.0, "upper": 0.10}})


if __name__ == "__main__":
    unittest.main()
