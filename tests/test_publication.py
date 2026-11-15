import json
import os
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from datathon.agents import AgentRun
from datathon.counterfactual import run_counterfactual
from datathon.data import load_market_data
from datathon.publication import publish_check, publish_report
from datathon.review_snapshot import AUDIT_SNAPSHOT_KEY
from datathon.workflow import examples, preset_profile, run_case


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
        case = replace(examples("robert")[0], search_alternatives=False)
        profile = {**preset_profile(case),
                   "unassessed_requirements": [{"code": "esg", "excerpt": "private ESG clause"}]}
        report = await run_case(self.data, case, confirmed_profile=AgentRun("ok", profile))
        published = publish_report(report)
        self.assertEqual(published["publication"]["status"], "limited")
        self.assertEqual(set(published["audit"]["verified"]), {"baseline", "proposal"})
        self.assertEqual(set(published["scenarios"]), {"baseline", "proposal"})
        requirement = next(row for row in published["requirements"] if row["code"] == "esg")
        self.assertEqual(requirement["task_status"], "unsupported")
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

    async def test_after_review_changes_cannot_reuse_core_verification(self):
        case = examples("robert")[0]
        report = await run_case(self.data, case)
        original = publish_report(report)
        self.assertEqual(publish_report(original), original)
        self.assertNotIn(AUDIT_SNAPSHOT_KEY, json.dumps(original))
        self.assertIn("market_data", original["publication"]["versions"]["inputs"])

        with patch("datathon.review_snapshot.POLICY_VERSION", "portfolio-audit-v2"):
            for source in (report, original):
                self.assertEqual(publish_report(source)["publication"]["status"], "blocked")

        for field in ("risk", "policy", "evidence", "scope", "snapshot"):
            with self.subTest(field=field):
                changed = deepcopy(report)
                if field == "risk":
                    changed["audit"]["verified"]["proposal"]["windows"]["2022"]["max_drawdown"] = .99
                elif field == "policy":
                    changed["policy"]["loss_limit"] = .99
                elif field == "evidence":
                    changed["evidence"]["price_source"] = "different dataset"
                elif field == "scope":
                    changed["search_alternatives"] = False
                else:
                    changed.pop(AUDIT_SNAPSHOT_KEY)
                blocked = publish_report(changed)
                self.assertEqual(blocked["publication"]["status"], "blocked")
                self.assertFalse(blocked["publication"]["independent_review_verified"])
                self.assertNotIn("scenarios", blocked)
                self.assertNotIn("policy", blocked)

        second_run = await run_case(self.data, case)
        self.assertNotEqual(original["publication"]["review_id"], publish_report(second_run)["publication"]["review_id"])
        second_run[AUDIT_SNAPSHOT_KEY] = report[AUDIT_SNAPSHOT_KEY]
        self.assertEqual(publish_report(second_run)["decision_reason"], "review_snapshot_mismatch")

    async def test_optional_section_tampering_leaves_other_sections_verified(self):
        case = replace(examples("robert")[0], include_sector=True, search_alternatives=False)
        profile = {**preset_profile(case), "issuer_cap_bps": 1400}
        report = await run_case(self.data, case, confirmed_profile=AgentRun("ok", profile))
        original = publish_report(report)
        self.assertEqual(original["publication"]["section_verification"], {
            "main_audit": "verified", "sector_analysis": "verified", "exposure_change": "verified",
        })

        for source in (report, original):
            with self.subTest(projected="publication" in source):
                changed = deepcopy(source)
                changed["sector_analysis"]["sectors"]["Information Technology"]["after"]["lower"] = .99
                limited = publish_report(changed)
                self.assertEqual(limited["publication"]["status"], "limited")
                self.assertTrue(limited["publication"]["independent_review_verified"])
                self.assertEqual(limited["publication"]["section_verification"]["sector_analysis"], "invalid")
                self.assertNotIn("sector_analysis", limited)
                self.assertEqual(limited["exposure_change"], original["exposure_change"])
                self.assertEqual(limited["scenarios"], original["scenarios"])

    async def test_challenge_rejects_changed_statement_and_stale_replay(self):
        case = examples("robert")[0]
        report = await run_case(self.data, case)
        check = await run_counterfactual(self.data, case, report, option_id="toggle_loss_metric")
        original = publish_check(check)
        self.assertTrue(original["verified"])
        self.assertEqual(publish_check(original), original)

        changed = deepcopy(check)
        changed["statement"] = "Risk is 0% and guaranteed safe."
        withheld = publish_check(changed)
        self.assertFalse(withheld["verified"])
        self.assertNotIn("guaranteed", json.dumps(withheld))

        changed = deepcopy(check)
        changed["replay"]["audit"]["verified"]["proposal"]["max_drawdown"] = .99
        withheld = publish_check(changed)
        self.assertFalse(withheld["verified"])
        self.assertTrue(withheld["baseline"]["publication"]["independent_review_verified"])
        self.assertIsNone(withheld["replay"])

    async def test_challenge_rejects_modified_issuer_action_threshold(self):
        case = examples("amira")[0]
        report = await run_case(self.data, case)
        check = await run_counterfactual(self.data, case, report, option_id="request_issuer_evidence")
        self.assertIsNotNone(publish_check(check)["action"])
        check["action"]["thresholds"]["proposal"]["known_lower"] = .99
        withheld = publish_check(check)
        self.assertFalse(withheld["verified"])
        self.assertIsNone(withheld["action"])
