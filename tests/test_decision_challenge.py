"""Challenge authorization, single-change isolation and reviewed publication."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from datathon.data import load_market_data
from datathon.decision_challenge import prepare_challenge, read_finding, run_challenges
from datathon.decision_release import publish_report, report_json
from datathon.decision_workflow import authorize_funding, confirm_decision, run_decision


class DecisionChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prices_daily.csv").write_text(
                "ticker,date,adj_close,currency\n" + "".join(
                    f"{symbol},{day},{price},CAD\n"
                    for symbol, values in {"A": [100, 110, 105], "B": [100, 100, 100], "T": [100, 80, 90]}.items()
                    for day, price in zip(["2025-01-02", "2025-01-03", "2025-01-06"], values)), encoding="utf-8")
            (root / "fx_usdcad_daily.csv").write_text("date,usdcad\n2025-01-02,1.4\n2025-01-03,1.4\n2025-01-06,1.4\n")
            (root / "sources_metadata.csv").write_text(
                "file,source,source_url,retrieved_on\n"
                "prices_daily.csv,Fixture,https://example.com/prices,2025-01-07\n"
                "fx_usdcad_daily.csv,Fixture,https://example.com/fx,2025-01-07\n")
            cls.market = load_market_data(root)

    def setUp(self):
        self.original = confirm_decision({
            "intent": "audit", "portfolios": [{"label": "Original", "weights": {"A": .4, "B": .6}}],
            "trade": {"symbol": "T", "source": "A", "quantity": 10, "unit": "percentage_points"},
            "constraints": [{"asset_set": {"symbols": ["A"]}, "min": .35}],
        })
        self.report = publish_report(run_decision(self.original, self.market))

    def test_read_only_questions_do_not_run_replay_or_funding(self):
        with patch("datathon.decision_challenge.run_decision") as execute:
            failures = read_finding(self.report, "why_fail")
            self.assertEqual(failures["verdict"], "fail")
            self.assertEqual(len(failures["rules"]), 1)
            self.assertTrue(read_finding(self.report, "uncertain")["gaps"])
            self.assertIsNone(read_finding(self.report, "funding_difference")["funding"])
            execute.assert_not_called()
        self.report["verdict"] = "pass"
        with self.assertRaises(ValueError):
            read_finding(self.report, "why_fail")

    def test_read_only_failure_explanation_does_not_treat_user_labels_as_system_roles(self):
        for intent in ("evaluate", "compare"):
            portfolios = [{"label": "Starting allocation", "weights": {"A": .4, "B": .6}}]
            if intent == "compare":
                portfolios.append({"label": "Other", "weights": {"A": .6, "B": .4}})
            confirmed = confirm_decision({"intent": intent, "portfolios": portfolios,
                                          "constraints": [{"asset_set": {"symbols": ["A"]}, "min": .5}]})
            report = publish_report(run_decision(confirmed, self.market))
            result = read_finding(report, "why_fail")
            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(len(result["rules"]), 1)
            self.assertEqual(result["rules"][0]["candidate"], "Starting allocation")
            self.assertEqual(result["message"], "These checked rules failed.")

    def test_confirmed_floor_change_flips_and_preserves_original_snapshot(self):
        original_body, original_report = self.original.data, report_json(self.report)
        proposals = [prepare_challenge(self.original, field="holding_minimum", value=floor) for floor in (.25, .2, .1)]
        with patch("datathon.decision_workflow.search_funding") as solver:
            result = run_challenges(self.original, self.report, self.market, proposals, acknowledged=True)
            solver.assert_not_called()
        self.assertEqual(result["stopped_reason"], "verdict_changed")
        self.assertEqual(len(result["steps"]), 1)
        step = result["steps"][0]
        self.assertEqual(step["change"]["path"], ["constraints", 0, "min"])
        self.assertEqual(step["before"]["verdict"], "fail")
        self.assertEqual(step["after"]["verdict"], "pass")
        self.assertEqual(step["report"]["publication"]["status"], "released")
        self.assertEqual(self.original.data, original_body)
        self.assertEqual(report_json(self.report), original_report)

    def test_up_to_three_checks_anchor_to_original_and_do_not_accumulate(self):
        proposals = [prepare_challenge(self.original, field="holding_minimum", value=floor) for floor in (.36, .37, .38)]
        result = run_challenges(self.original, self.report, self.market, proposals, acknowledged=True)
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(result["stopped_reason"], "confirmed_checks_complete")
        self.assertEqual([step["change"]["before"] for step in result["steps"]], [.35] * 3)
        for candidate in ([], proposals + proposals[:1]):
            with self.assertRaisesRegex(ValueError, "one and three"):
                run_challenges(self.original, self.report, self.market, candidate, acknowledged=True)

    def test_confirmation_and_fresh_search_authorization_are_required(self):
        proposal = prepare_challenge(self.original, field="purchase_quantity", value=4)
        with patch("datathon.decision_challenge.run_decision") as execute:
            with self.assertRaisesRegex(ValueError, "confirm"):
                run_challenges(self.original, self.report, self.market, [proposal])
            execute.assert_not_called()
        old_auth = authorize_funding(self.original, sources=["A", "B"])
        with self.assertRaisesRegex(ValueError, "different confirmed inputs"):
            run_challenges(self.original, self.report, self.market, [proposal], acknowledged=True,
                           funding_authorizations={0: old_auth})
        new_auth = authorize_funding(proposal.confirmed, sources=["A", "B"])
        result = run_challenges(self.original, self.report, self.market, [proposal], acknowledged=True,
                                funding_authorizations={0: new_auth})
        self.assertTrue(result["steps"][0]["funding_authorized"])
        self.assertEqual(result["steps"][0]["report"]["funding"]["status"], "feasible")

    def test_forged_change_and_unrelated_original_report_are_rejected(self):
        proposal = prepare_challenge(self.original, field="holding_minimum", value=.25)
        forged = proposal.confirmed.data
        forged["trade"]["quantity"] = 5
        proposal = replace(proposal, confirmed=confirm_decision(forged))
        with self.assertRaisesRegex(ValueError, "more than"):
            run_challenges(self.original, self.report, self.market, [proposal], acknowledged=True)
        other = prepare_challenge(self.original, field="purchase_quantity", value=5).confirmed
        with self.assertRaises(ValueError):
            run_challenges(other, self.report, self.market,
                           [prepare_challenge(other, field="purchase_quantity", value=3)], acknowledged=True)

    def test_metric_change_preserves_cap_and_never_silently_changes_two_fields(self):
        draft = self.original.data
        draft["risk_limits"] = [{"metric": "terminal_loss", "cap": .14, "windows": "default"}]
        confirmed = confirm_decision(draft)
        proposal = prepare_challenge(confirmed, field="risk_metric", value="max_drawdown")
        self.assertEqual(proposal.change["unchanged_cap"], .14)
        self.assertEqual(proposal.confirmed.data["risk_limits"][0]["cap"], .14)
        with self.assertRaises(ValueError):
            prepare_challenge(confirmed, field="risk_metric", value="recovery_days")
        for field, value in (("purchase_quantity", 11), ("holding_minimum", .35), ("anything", 0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_challenge(self.original, field=field, value=value)


if __name__ == "__main__":
    unittest.main()
