"""Exercise dated disclosure boundaries and conservative exposure weights."""

import json
import unittest

from datathon.data import issuer_evidence
from datathon.evidence import ISSUER_SCOPE, validate_issuer_snapshot
from datathon.finance import BASE_WEIGHTS


class IssuerEvidenceTests(unittest.TestCase):
    def qualify(self, snapshot, **settings):
        return validate_issuer_snapshot(snapshot, **{
            "reference_date": "2026-11-14",
            "publication_cutoff": "2026-11-14",
            "assets": BASE_WEIGHTS,
            **settings,
        })

    def test_frozen_snapshot_uses_disclosed_fractions_and_keeps_assumptions_unknown(self):
        snapshot = issuer_evidence()
        result = self.qualify(snapshot)
        self.assertEqual(result["scope"], ISSUER_SCOPE)
        self.assertEqual(result["issuer_weights"], {
            "SPY": snapshot["holdings"]["SPY"]["weight"],
            "XIU.TO": None,
            "QQQ": snapshot["holdings"]["QQQ"]["weight"],
            "ZST.TO": None,
            "NVDA": 1.0,
        })
        xiu = result["holdings"]["XIU.TO"]
        self.assertEqual((xiu["status"], xiu["reported_weight"], xiu["weight"]), ("scope_assumption", 0.0, None))
        self.assertEqual(snapshot, issuer_evidence())

    def test_publication_must_be_available_by_cutoff_and_reference_date(self):
        snapshot = issuer_evidence()
        cases = (
            ({"publication_cutoff": "2026-08-27"}, "future"),
            ({"publication_cutoff": "2026-08-28"}, "disclosed"),
            ({"reference_date": "2026-08-27"}, "future"),
            ({"reference_date": "2026-08-28"}, "disclosed"),
        )
        for dates, expected in cases:
            with self.subTest(dates=dates):
                row = self.qualify(snapshot, **dates)["holdings"]["QQQ"]
                self.assertEqual(row["status"], expected)
                self.assertEqual(row["published_on"], "2026-08-28")
                if expected == "future":
                    self.assertIsNone(row["weight"])

    def test_observation_freshness_is_inclusive(self):
        snapshot = issuer_evidence()
        at_limit = self.qualify(snapshot, reference_date="2026-12-27")["holdings"]["QQQ"]
        past_limit = self.qualify(snapshot, reference_date="2026-12-28")["holdings"]["QQQ"]
        self.assertEqual((at_limit["status"], at_limit["age_days"]), ("disclosed", 180))
        self.assertEqual((past_limit["status"], past_limit["age_days"]), ("stale", 181))
        self.assertIsNone(past_limit["weight"])
        self.assertEqual(past_limit["reported_weight"], at_limit["weight"])
        self.assertEqual(past_limit["published_on"], at_limit["published_on"])
        self.assertIsNone(self.qualify(snapshot, max_age_days=30)["issuer_weights"]["QQQ"])

    def test_bad_holding_records_become_unknown_without_affecting_other_holdings(self):
        cases = (
            ({"as_of": "2026-07-01"}, "invalid"),
            ({"published_on": "2026-02-29"}, "invalid"),
            ({"published_on": "2026-06-29"}, "invalid"),
            ({"published_on": None}, "unknown"),
            ({"scope": "NVIDIA derivative notional"}, "invalid"),
            ({"issuer_id": "CUSIP:123456789"}, "invalid"),
            ({"url": "file:///tmp/filing"}, "invalid"),
            ({"weight": True}, "invalid"),
            ({"weight": 8.0}, "invalid"),
            ({"weight": float("nan")}, "invalid"),
        )
        for change, expected in cases:
            with self.subTest(change=change):
                snapshot = issuer_evidence()
                snapshot["holdings"]["QQQ"].update(change)
                result = self.qualify(snapshot)
                self.assertEqual(result["holdings"]["QQQ"]["status"], expected)
                self.assertIsNone(result["issuer_weights"]["QQQ"])
                self.assertIsNotNone(result["issuer_weights"]["SPY"])
                if "url" in change:
                    self.assertIsNone(result["holdings"]["QQQ"]["url"])
                json.dumps(result, allow_nan=False)

    def test_bad_or_absent_snapshot_never_changes_direct_exposure(self):
        snapshot = issuer_evidence()
        for source, status in (
            (None, "unknown"), ({**snapshot, "scope": "Any issuer"}, "invalid"),
            ({**snapshot, "as_of": "2026-11-15"}, "future"),
        ):
            with self.subTest(status=status):
                result = self.qualify(source)
                self.assertEqual(result["holdings"]["QQQ"]["status"], status)
                self.assertIsNone(result["issuer_weights"]["QQQ"])
                self.assertEqual(result["issuer_weights"]["NVDA"], 1.0)

    def test_missing_holding_has_no_observation_date_or_age(self):
        snapshot = issuer_evidence()
        del snapshot["holdings"]["QQQ"]
        result = self.qualify(snapshot)
        self.assertEqual(result["as_of"], "2026-06-30")
        qqq = result["holdings"]["QQQ"]
        self.assertEqual(qqq["status"], "unknown")
        self.assertIsNone(qqq["as_of"])
        self.assertIsNone(qqq["age_days"])

    def test_invalid_date_context_is_rejected(self):
        for settings in ({"reference_date": "2026-02-30"}, {"publication_cutoff": "20261114"},
                         {"max_age_days": -1}, {"max_age_days": True}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.qualify(issuer_evidence(), **settings)
