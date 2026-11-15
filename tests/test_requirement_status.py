import json
import os
import unittest

from datathon.agents import AgentRun
from datathon.data import load_market_data
from datathon.publication import publish_report
from datathon.requirement_status import apply_requirement_status, unassessed_codes
from datathon.workflow import examples, preset_profile, run_case
from dataclasses import replace


class RequirementStatusTests(unittest.TestCase):
    def test_marks_verified_violation_and_unassessed_condition_separately(self):
        report = {
            "status": "fail",
            "policy": {"loss_limit": .14, "metric": "max_drawdown", "issuer_cap": .18},
            "evidence": {"price_source": "starter:prices", "fx_source": "starter:fx",
                         "evidence_ids": ["starter:prices", "issuer:QQQ:2026-06-30"]},
            "audit": {"verified": {"proposal": {"windows": {"2022": {}}}},
                      "findings": [{"metric_id": "proposal.max_drawdown.policy", "status": "fail"},
                                   {"metric_id": "proposal.issuer_weight.policy", "status": "insufficient_evidence"}]},
        }
        codes = unassessed_codes([{"code": "esg", "excerpt": "an unexported original phrase"},
                                  {"code": "esg"}, {"code": "not-a-controlled-code"}])
        apply_requirement_status(report, codes)
        rows = {item["code"]: item for item in report["requirements"]}
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["assessment_scope"], "limited")
        self.assertEqual(rows["loss_limit"]["verdict"], "fail")
        self.assertEqual(rows["issuer_cap"]["verdict"], "unknown")
        self.assertEqual(rows["alternatives"]["task_status"], "skipped_outside_scope")
        self.assertEqual(rows["esg"]["task_status"], "unsupported")
        self.assertEqual(rows["issuer_cap"]["evidence_ids"], ["issuer:QQQ:2026-06-30"])
        self.assertNotIn("unexported", json.dumps(report))
        self.assertEqual(codes, ("esg", "other_binding"))

    def test_blocked_report_never_claims_checked_requirements(self):
        report = {"status": "invalid", "search_alternatives": True,
                  "policy": {"reserve_floor": .15},
                  "audit": {"verified": {"proposal": {"windows": {"2022": {}}}},
                            "findings": [{"metric_id": "proposal.reserve_weight.policy", "status": "pass"}]}}
        apply_requirement_status(report)
        self.assertEqual(report["assessment_scope"], "unavailable")
        self.assertTrue(all(item["verdict"] is None for item in report["requirements"]))


@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Requires the official validation data")
class PublishedScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_limited_review_keeps_public_sector_bounds_and_blocks_funding_search(self):
        case = replace(examples("robert")[0], include_sector=True, search_alternatives=True)
        profile = {**preset_profile(case), "issuer_cap_bps": 1400,
                   "unassessed_requirements": [{"code": "sector", "excerpt": "private candidate phrase"}]}
        report = await run_case(load_market_data(), case, confirmed_profile=AgentRun("ok", profile))
        public = publish_report(report)
        self.assertFalse(report["search_alternatives"])
        self.assertNotIn("alternatives", public)
        self.assertEqual(public["assessment_scope"], "limited")
        self.assertNotIn("private candidate phrase", json.dumps(public))
        bounds = public["sector_analysis"]["sectors"]["Information Technology"]["change"]
        self.assertAlmostEqual(bounds["lower"], .0837)
        self.assertAlmostEqual(bounds["upper"], .10)
        self.assertIn("exposure_change", public)
        self.assertTrue(any(row["code"] == "sector" and row["task_status"] == "unsupported"
                            for row in public["requirements"]))
