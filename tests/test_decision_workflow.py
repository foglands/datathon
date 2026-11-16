"""Integration checks for publication, confirmation and separate search authorization."""

import os
from copy import deepcopy
import unittest
from unittest.mock import patch

from datathon.data import load_market_data
from datathon.decision_release import publish_report, report_json, validate_report_inputs
from datathon.decision_workflow import authorize_funding, confirm_decision, run_decision
from datathon import decision_workflow


@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set the official starter path.")
class DecisionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = load_market_data()

    def draft(self, **overrides):
        return {"intent": "audit", "portfolios": [{"label": "Original", "weights":
                {"SPY": .35, "XIU.TO": .25, "QQQ": .20, "ZST.TO": .20}}],
                "trade": {"symbol": "NVDA", "source": "ZST.TO", "quantity": 10, "unit": "percentage_points"},
                "risk_limits": [{"metric": "terminal_loss", "cap": .14, "windows": "default"}],
                "constraints": [{"asset_set": {"symbols": ["ZST.TO"]}, "min": .15}],
                "profile": {"objective": "Capital preservation", "risk_tolerance": "Low"}, **overrides}

    def test_three_paths_replay_and_original_never_searches(self):
        comparison = self.draft(intent="compare", risk_limits=[], constraints=[], priority="max_drawdown",
                                portfolios=[{"label": "First", "weights": {"SPY": 1}},
                                            {"label": "Second", "weights": {"QQQ": 1}}])
        evaluation = self.draft(intent="evaluate", risk_limits=[], constraints=[],
                               portfolios=[{"label": "Non-demo", "weights": {"SPY": .6, "GLD": .4}}])
        with patch("datathon.decision_workflow.search_funding") as solver:
            for draft in (comparison, evaluation, self.draft()):
                with self.subTest(action=draft["intent"]):
                    report = publish_report(run_decision(confirm_decision(draft), self.market))
                    self.assertEqual(report["publication"]["status"], "released", report)
                    self.assertEqual(report["intent"], draft["intent"])
                    self.assertTrue(report["options"])
                    self.assertIsNone(report.get("funding"))
                    self.assertTrue(report_json(report))
            solver.assert_not_called()
        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(report["profile_tensions"])

    def test_authorized_robert_boundary_and_new_decision_rejects_reuse(self):
        original = confirm_decision(self.draft())
        auth = authorize_funding(original, sources=["QQQ", "ZST.TO"])
        report = publish_report(run_decision(original, self.market, funding=auth))
        self.assertEqual(report["publication"]["status"], "released")
        self.assertEqual(report["funding"]["status"], "feasible")
        validate_report_inputs(report, original)
        self.assertAlmostEqual(report["funding"]["source_bounds"]["ZST.TO"]["max"], 0.0263167, places=6)
        different = confirm_decision(self.draft(risk_limits=[{"metric":"max_drawdown", "cap":.14}]))
        with self.assertRaisesRegex(ValueError, "different"):
            run_decision(different, self.market, funding=auth)
        new_search = authorize_funding(different, sources=["QQQ", "ZST.TO"])
        report = publish_report(run_decision(different, self.market, funding=new_search))
        self.assertEqual(report["funding"]["status"], "infeasible")
        self.assertTrue(report["funding"]["certificate"])

    def test_market_or_numeric_tampering_fails_closed(self):
        confirmed = confirm_decision(self.draft())
        with patch("datathon.decision_workflow.evaluate", return_value={"max_drawdown": .99}):
            with self.assertRaises(ValueError):
                run_decision(confirmed, self.market)
        with self.assertRaisesRegex(ValueError, "Confirm"):
            run_decision(self.draft(), self.market)

    def test_rule_tampering_is_detected_even_when_metrics_are_correct(self):
        genuine = decision_workflow._candidate_rules
        def altered(*args, **kwargs):
            result = genuine(*args, **kwargs)
            result[0]["status"] = "pass" if result[0]["status"] != "pass" else "fail"
            return result
        with patch("datathon.decision_workflow._candidate_rules", side_effect=altered):
            with self.assertRaisesRegex(ValueError, "Independent rule verification"):
                run_decision(confirm_decision(self.draft()), self.market)

    def test_capital_uses_initial_and_actual_peak_denominators(self):
        draft = self.draft(capital={"value": 100000, "currency": "CAD"})
        report = publish_report(run_decision(confirm_decision(draft), self.market))
        row = report["options"]["Original proposal"]["windows"]["2022"]
        self.assertAlmostEqual(row["terminal_loss_amount"], row["terminal_loss"] * 100000)
        self.assertAlmostEqual(row["drawdown_loss_amount"], row["max_drawdown"] * row["drawdown_peak_amount"])
        self.assertGreater(row["drawdown_peak_amount"], 100000)
        self.assertEqual(report["capital"], {"value": 100000.0, "currency": "CAD"})
        amounts = [value for value in report["metric_records"].values() if value["metric"].endswith("_amount")]
        self.assertTrue(amounts)
        self.assertTrue(all(value["unit"] == "CAD" for value in amounts))

    def test_invalid_capital_and_conversion_mismatch_need_new_confirmation(self):
        for capital in ({"value": -1, "currency": "CAD"}, {"value": float("nan"), "currency": "CAD"},
                        {"value": True, "currency": "CAD"}, {"value": 100, "currency": "USD"}):
            with self.subTest(capital=capital), self.assertRaises(ValueError):
                confirm_decision(self.draft(capital=capital))
        draft = self.draft(capital={"value": 100000, "currency": "CAD"})
        draft["trade"] = {**draft["trade"], "unit": "shares", "portfolio_value_cad": 200000}
        with self.assertRaisesRegex(ValueError, "same confirmed capital"):
            confirm_decision(draft)

    def test_unsupported_condition_stays_unknown_and_search_is_unassessed(self):
        draft = self.draft(constraints=[{"asset_set": {"liquidity_bucket": "unmeasured"}, "max": .05}],
                           risk_limits=[])
        confirmed = confirm_decision(draft)
        with patch("datathon.decision_workflow.search_funding") as solver:
            report = publish_report(run_decision(confirmed, self.market,
                funding=authorize_funding(confirmed, sources=["QQQ", "ZST.TO"])))
            solver.assert_not_called()
        self.assertEqual(report["verdict"], "unknown")
        self.assertEqual(report["funding"]["status"], "unassessed")
        self.assertEqual(report["publication"]["status"], "released")

    def test_unsupported_axes_remain_unknown_at_trivial_interval_boundaries(self):
        for boundary in ({"min": 0}, {"max": 1}, {"min": 0, "max": 1}):
            draft = self.draft(constraints=[{"asset_set": {"custom_unsupported": "anything"}, **boundary}],
                               risk_limits=[])
            report = publish_report(run_decision(confirm_decision(draft), self.market))
            self.assertEqual(report["verdict"], "unknown", boundary)
            constraints = [row for row in report["rules"] if row["id"].startswith("exposure-")]
            self.assertTrue(constraints)
            self.assertTrue(all(row["status"] == "unknown" and row["headroom"] is None for row in constraints))

    def test_proven_failure_does_not_hide_an_unassessed_rule(self):
        draft = self.draft(constraints=[{"asset_set": {"custom_unsupported": "anything"}, "max": 1}])
        report = publish_report(run_decision(confirm_decision(draft), self.market))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["status"], "limited")
        self.assertEqual(next(row for row in report["governance"] if row["id"] == "rule_coverage")["status"], "flag")
        self.assertTrue(any("unassessed" in gap for gap in report["gaps"]))

    def test_display_labels_never_exclude_non_audit_binding_rules(self):
        for label in ("Starting allocation", "Original proposal", "Ordinary label"):
            draft = self.draft(intent="evaluate", portfolios=[{"label": label, "weights": {"SPY": 1}}],
                               constraints=[], risk_limits=[{"metric": "max_drawdown", "cap": 0}])
            report = publish_report(run_decision(confirm_decision(draft), self.market))
            self.assertEqual(report["verdict"], "fail", label)
            self.assertTrue(all(rule["status"] == "fail" for rule in report["rules"]))
        draft = self.draft(intent="compare", portfolios=[{"label": "Starting allocation", "weights": {"SPY": 1}},
                                                           {"label": "Original proposal", "weights": {"QQQ": 1}}],
                           constraints=[], risk_limits=[{"metric": "max_drawdown", "cap": 0}])
        report = publish_report(run_decision(confirm_decision(draft), self.market))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["profile_tensions"], [])

    def test_one_ineligible_candidate_does_not_hide_eligible_metric_ranking(self):
        draft = self.draft(intent="compare", priority="max_drawdown", ranking_window="2022",
                           portfolios=[{"label": "Equity", "weights": {"QQQ": 1}},
                                       {"label": "Reserve", "weights": {"ZST.TO": 1}}],
                           constraints=[], risk_limits=[{"metric": "max_drawdown", "cap": .12, "windows": ["2022"]}])
        report = publish_report(run_decision(confirm_decision(draft), self.market))
        self.assertEqual([row["candidate"] for row in report["ranking"]["order"]], ["Reserve"])

    def test_exported_certificate_reproduces_independent_funding_verification(self):
        from datathon.decision_market import prepare_market
        from datathon.decision_funding import verify_funding
        confirmed = confirm_decision(self.draft())
        authorization = authorize_funding(confirmed, sources=["QQQ", "ZST.TO"])
        report = publish_report(run_decision(confirmed, self.market, funding=authorization))
        panel = prepare_market(self.market, ["SPY", "XIU.TO", "QQQ", "ZST.TO", "NVDA"])
        funding = report["funding"]
        self.assertTrue(funding["certificate"]["source_bounds"])
        checked = verify_funding(confirmed.data["portfolios"][0]["weights"], "NVDA", .1,
                                 authorization.sources, panel["windows"], confirmed.data["constraints"],
                                 funding["resolved_risk_limits"], claimed=funding, allow_smaller=False)
        self.assertEqual(checked["status"], "verified", checked)
        funding["certificate"]["source_bounds"]["ZST.TO"]["max"]["point"][0] = "1"
        checked = verify_funding(confirmed.data["portfolios"][0]["weights"], "NVDA", .1,
                                 authorization.sources, panel["windows"], confirmed.data["constraints"],
                                 funding["resolved_risk_limits"], claimed=funding, allow_smaller=False)
        self.assertEqual(checked["status"], "invalid")
