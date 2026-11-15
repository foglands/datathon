import json
import unittest

from datathon.requirement_status import apply_requirement_status, unassessed_codes


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
        self.assertEqual(rows["alternatives"]["task_status"], "skipped_not_requested")
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
