"""Use synthetic catalog disclosures only to test the trusted re-audit boundary."""

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from datathon.agents import AgentRun
from datathon.counterfactual import issuer_disclosure_options, run_counterfactual
from datathon.data import issuer_evidence, load_market_data
from datathon.evidence import ISSUER_SCOPE, add_issuer_disclosures, validate_issuer_snapshot
from datathon.workflow import examples, preset_profile, run_case
from tests.test_tool_routing import MARKET


USE_BY_DATE = {"reference_date": "2026-11-14", "publication_cutoff": "2026-11-14"}


def synthetic_disclosure(identifier, ticker, **updates):
    return {
        "id": identifier, "ticker": ticker, "as_of": "2026-09-30", "published_on": "2026-10-10",
        "weight": 0.0, "url": "https://example.com/synthetic-fixture-no-market-evidence",
        "source": "Synthetic test disclosure", "source_document_sha256": "1" * 64,
        "source_locator": "Synthetic holdings test only", **updates,
    }


def configured_catalog(path, records):
    raw = json.dumps({"issuer_id": "CUSIP:67066G104", "scope": ISSUER_SCOPE, "disclosures": records}).encode()
    Path(path).write_bytes(raw)
    return patch.dict(os.environ, {"DATATHON_ISSUER_CATALOG": str(path),
                                   "DATATHON_ISSUER_CATALOG_SHA256": sha256(raw).hexdigest()})


class ReviewedIssuerReauditTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        official = os.environ.get("DATATHON_STARTER_PATH")
        cls.market = load_market_data(official) if official else MARKET

    async def asyncSetUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.catalog_path = Path(folder.name) / "fixture.json"
        self.case, = examples("amira")
        self.original = await run_case(self.market, self.case, confirmed_profile=AgentRun("ok", preset_profile(self.case)))
        self.assertEqual(self.original["decision_reason"], "issuer_evidence_insufficient")

    async def replay(self, ids, **replay_options):
        return await run_counterfactual(
            self.market, self.case, self.original, option_id="request_issuer_evidence",
            issuer_disclosure_ids=ids, **replay_options,
        )

    async def test_full_and_partial_reaudit_preserve_original_and_distinct_fund_dates(self):
        original = deepcopy(self.original)
        xiu = synthetic_disclosure("xiu", "XIU.TO")
        zst = synthetic_disclosure("zst", "ZST.TO", as_of="2026-06-30")
        with configured_catalog(self.catalog_path, [xiu, zst]):
            self.assertEqual(set(issuer_disclosure_options(self.original)), {"xiu", "zst"})
            partial = await self.replay(["xiu"])
            complete = await self.replay(["xiu", "zst"])
        self.assertTrue(partial["verified"])
        self.assertEqual(partial["action"]["remaining_holding_gaps"], {"ZST.TO": "scope_assumption_is_unverified"})
        self.assertEqual(partial["replay"]["decision_reason"], "issuer_evidence_insufficient")
        self.assertEqual((complete["status"], complete["reason"]), ("verified", "issuer_reaudit_verified"))
        self.assertEqual(complete["action"]["remaining_holding_gaps"], {})
        self.assertEqual(complete["comparison"]["replay"]["solver_status"], "feasible_full")
        self.assertTrue(complete["replay"]["audit"]["verified"]["maximum"]["passes"])
        self.assertEqual(complete["replay"]["status"], "fail")
        self.assertEqual(complete["changed_fields"], [])
        self.assertEqual(self.original, original)
        for key in ("policy", "scenarios"):
            self.assertEqual(complete["replay"][key], original[key])
        self.assertIn("issuer:XIU.TO:2026-09-30", complete["replay"]["evidence"]["evidence_ids"])
        self.assertIn("issuer:ZST.TO:2026-06-30", complete["replay"]["evidence"]["evidence_ids"])
        self.assertEqual(len(complete["action"]["reviewed_disclosures"]), 2)
        json.dumps(complete, allow_nan=False)

    async def test_bad_pin_unknown_conflicting_stale_and_future_records_do_not_replay(self):
        xiu = synthetic_disclosure("xiu", "XIU.TO")
        older = synthetic_disclosure("earlier-xiu", "XIU.TO", as_of="2026-07-30")
        stale = synthetic_disclosure("stale", "ZST.TO", as_of="2026-05-01")
        future = synthetic_disclosure("future", "ZST.TO", published_on="2026-11-15")
        qqq = synthetic_disclosure("known-qqq", "QQQ")
        spy = AsyncMock()
        with configured_catalog(self.catalog_path, [xiu, older, stale, future, qqq]):
            self.assertEqual(set(issuer_disclosure_options(self.original)), {"xiu", "earlier-xiu"})
            for ids, reason in [
                (["https://example.com/fake"], "disclosure_not_eligible"),
                (["known-qqq"], "disclosure_not_eligible"),
                (["stale"], "disclosure_not_eligible"),
                (["future"], "disclosure_not_eligible"),
                (["xiu", "earlier-xiu"], "conflicting_disclosures"),
                ([{"ticker": "XIU.TO", "weight": 0}], "invalid_issuer_selection"),
            ]:
                with self.subTest(ids=ids):
                    self.assertEqual((await self.replay(ids, replayer=spy))["reason"], reason)
            with self.catalog_path.open("ab") as source:
                source.write(b" ")
            self.assertEqual((await self.replay(["xiu"], replayer=spy))["reason"], "issuer_catalog_unavailable")
        spy.assert_not_awaited()

    async def test_reaudit_rejects_reviewed_policy_or_market_mutation(self):
        xiu = synthetic_disclosure("xiu", "XIU.TO")

        async def altered(data, case, runtime, **kwargs):
            result = await run_case(data, case, runtime, **kwargs)
            result["audit"]["verified"]["proposal"]["windows"]["2022"]["terminal_loss"] = 0
            return result

        with configured_catalog(self.catalog_path, [xiu]):
            result = await self.replay(["xiu"], replayer=altered)
        self.assertEqual(result["reason"], "issuer_reaudit_not_verified")
        self.assertFalse(result["verified"])
        self.assertIsNone(result["replay"])

    async def test_unpinned_row_tampering_and_stale_requalification_keep_weight_unknown(self):
        xiu = synthetic_disclosure("xiu", "XIU.TO")
        with configured_catalog(self.catalog_path, [xiu]):
            raw = add_issuer_disclosures(issuer_evidence(), ("xiu",), assets=["XIU.TO"], **USE_BY_DATE)
            result = validate_issuer_snapshot(raw, max_age_days=30, **USE_BY_DATE)
            self.assertEqual(result["holdings"]["XIU.TO"]["status"], "stale")
            self.assertIsNone(result["issuer_weights"]["XIU.TO"])
            raw["holdings"]["XIU.TO"]["weight"] = .07
            result = validate_issuer_snapshot(raw, **USE_BY_DATE)
        self.assertEqual(result["holdings"]["XIU.TO"]["reason"], "unrecognized_reviewed_disclosure")
        self.assertIsNone(result["issuer_weights"]["XIU.TO"])
