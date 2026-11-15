import json
import os
import unittest

from datathon.counterfactual import run_counterfactual
from datathon.data import load_market_data
from datathon.publication import publish_check, publish_report
from datathon.workflow import examples, run_case


@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH to the official starter data.")
class PublicationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_market_data()

    async def test_release_uses_reviewed_values_and_never_copies_model_prose(self):
        report = await run_case(self.data, examples("robert")[0])
        report["explanation"] = "Injected claim: buy more after an 87% return."
        report["agent_commentary"] = report["explanation"]
        report["scenarios"]["proposal"]["windows"]["2022"]["terminal_loss"] = .87
        report["trace"].append({"event": "tool", "role": "profile", "status": "success",
                                "input": {"source_excerpt": "private request"},
                                "output": {"summary": "private request"}})
        published = publish_report(report)
        verified_loss = report["audit"]["verified"]["proposal"]["windows"]["2022"]["terminal_loss"]
        self.assertEqual(published["publication"]["status"], "released")
        self.assertEqual(published["scenarios"]["proposal"]["windows"]["2022"]["terminal_loss"], verified_loss)
        self.assertNotIn("Injected claim", json.dumps(published))
        self.assertNotIn("private request", json.dumps(published))
        self.assertNotEqual(report["scenarios"]["proposal"]["windows"]["2022"]["terminal_loss"], verified_loss)

    async def test_invalid_review_keeps_only_diagnostic_status_and_safe_trace(self):
        case = next(case for case in examples("robert", stress=True) if case.tamper)
        report = await run_case(self.data, case)
        published = publish_report(report)
        self.assertEqual(published["publication"]["status"], "blocked")
        self.assertEqual(published["audit"]["verified"], {})
        self.assertNotIn("scenarios", published)
        self.assertNotIn("alternatives", published)
        self.assertNotIn("claimed", json.dumps(published))
        self.assertTrue(published["trace"])
        self.assertTrue(any(row["status"] == "invalid" for row in published["audit"]["findings"]))

    async def test_audit_only_and_unevaluated_rules_keep_original_scope(self):
        report = await run_case(self.data, examples("robert")[0])
        report["search_alternatives"] = False
        report["assessment_scope"] = "limited"
        report["unassessed_requirements"] = [{"code": "esg", "excerpt": "private ESG clause"}]
        report["requirements"] = [{"code": "esg", "label": "ESG exclusion", "task_status": "unsupported",
                                   "verdict": None, "evidence_ids": [], "excerpt": "private ESG clause"}]
        published = publish_report(report)
        self.assertEqual(published["publication"]["status"], "limited")
        self.assertEqual(set(published["audit"]["verified"]), {"baseline", "proposal"})
        self.assertEqual(set(published["scenarios"]), {"baseline", "proposal"})
        self.assertEqual(published["requirements"][0]["task_status"], "unsupported")
        self.assertNotIn("private ESG clause", json.dumps(published))

    async def test_incomplete_disclosures_keep_verified_original_and_indicate_unresolved_search(self):
        report = await run_case(self.data, examples("amira")[0])
        report["exposure"]["qqq_only"]["lower"] = .01
        published = publish_report(report)
        self.assertEqual(published["publication"]["status"], "limited")
        self.assertEqual(published["audit"]["verified"]["frontier"], {"status": "insufficient_evidence"})
        self.assertAlmostEqual(published["exposure"]["qqq_only"]["lower"], .13390629804835452)
        self.assertIn("proposal", published["audit"]["verified"])

    async def test_challenge_recomputes_public_differences_from_verified_replays(self):
        case = examples("robert")[0]
        report = await run_case(self.data, case)
        check = await run_counterfactual(self.data, case, report, option_id="toggle_loss_metric")
        check["comparison"]["differences"]["proposal_terminal_loss"] = {"before": .55, "after": .89}
        published = publish_check(check)
        self.assertTrue(published["verified"])
        self.assertIsNotNone(published["replay"])
        self.assertNotIn("proposal_terminal_loss", published["comparison"]["differences"])
        self.assertIn("selected_loss_metric", published["comparison"]["differences"])
