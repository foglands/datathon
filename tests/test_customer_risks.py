"""Generic profiles alter relevance, never the underlying historical arithmetic."""

import asyncio
from copy import deepcopy
from datetime import date, timedelta
import unittest
from unittest.mock import AsyncMock, Mock, patch

from datathon.customer_profile import build_profile, risk_plan
from datathon.customer_report import analyze, report_html
from datathon.customer_risks import (withdrawal_schedule, replay_withdrawals, purchasing_power,
                                     quantify_risks, explicit_rule_checks, historical_details, risk_blocks)
from datathon.customer_workflow import research_question
from datathon.customer_bonds import qualified_bond_disclosures, duration_scenarios, credit_breakdown
from tests.test_customer_research import asset, fx, plan


def history(months=38):
    start = date(2022, 1, 3)
    return [{"date": (start + timedelta(days=i)).isoformat(), "price": 100. if i < 90 else 60.}
            for i in range(months * 31)]


class ProfileDrivenTests(unittest.TestCase):
    def test_crypto_does_not_publish_equity_calendar_annualization(self):
        instrument = asset("BTC-USD")
        instrument["instrument_type"] = "CRYPTOCURRENCY"
        result = historical_details(analyze([instrument], None)[0])
        blocks, _ = risk_blocks([{"id": "historical_market", "status": "assessed", "results": [result], "limitation": "History only"}])
        self.assertIn("annualized volatility withheld", blocks["risk.historical_market"]["text"])
        self.assertNotIn("252-observation", blocks["risk.historical_market"]["text"])

    def test_official_names_are_irrelevant_to_identical_inputs(self):
        reports = []
        for name in ("Amira", "Mateo", "Robert", "Custom customer"):
            request = plan(conditions=[{"kind": "goal", "excerpt": "preserve capital", "source_type": "current_request"}])
            request["name"] = name
            profile = build_profile(request)
            report = analyze([asset()], request["budget"], fx())
            reports.append((profile, report))
        self.assertTrue(all(report == reports[0] for report in reports[1:]))

    def test_contrasting_test_profiles_change_relevance_not_metrics(self):
        conditions = ([{"kind": "goal", "excerpt": "long-term growth"}, {"kind": "willingness", "excerpt": "high risk"}],
                      [{"kind": "esg", "excerpt": "avoid major controversies"}],
                      [{"kind": "capacity", "excerpt": "cannot afford losses"}, {"kind": "horizon", "excerpt": "3 years"}])
        analyses = analyze([asset()], plan()["budget"], fx())
        original = deepcopy(analyses)
        plans = [risk_plan(build_profile(plan(conditions=value)), [asset()], analyses) for value in conditions]
        self.assertIn("controversy", {row["id"] for row in plans[1]})
        self.assertNotIn("controversy", {row["id"] for row in plans[0]})
        self.assertEqual(analyses, original)
        self.assertEqual(explicit_rule_checks(build_profile(plan(conditions=conditions[2])), analyses), [])

    def test_high_willingness_does_not_override_down_payment_need(self):
        request = plan(conditions=[{"kind": "willingness", "excerpt": "high risk willingness"},
            {"kind": "withdrawal", "excerpt": "I need 20000 CAD in two years for a down payment."}])
        profile = build_profile(request)
        schedule, error = withdrawal_schedule(profile)
        self.assertIsNone(error)
        self.assertEqual(schedule["first_month"], 24)
        self.assertEqual(schedule["amount"], 20000)
        self.assertIn("cash_needs", {risk["id"] for risk in risk_plan(profile, [asset()], [])})
        self.assertEqual(explicit_rule_checks(profile, analyze([asset()], None)), [])

    def test_cash_statement_conflicts_are_preserved(self):
        profile = build_profile(plan(conditions=[{"kind": "investment_amount", "excerpt": "Invest 3000 CAD"},
                                                {"kind": "investment_amount", "excerpt": "Invest 6000 CAD"}]))
        self.assertEqual(len(profile["fields"]["investment_amount"]), 2)
        self.assertEqual(profile["conflicts"][0]["field"], "investment_amount")
        self.assertEqual(profile["fields"]["investment_amount"][0]["confirmation"], "extracted_unconfirmed")

    def test_explicit_budget_correction_resolves_conflict_without_erasing_evidence(self):
        request = plan(conditions=[{"kind": "investment_amount", "excerpt": "Invest 3000 CAD"},
                                   {"kind": "investment_amount", "excerpt": "Invest 6000 CAD"}])
        profile = build_profile(request, "Earlier conflicting amounts.\nUser clarification (takes precedence): Use 3000 CAD as the investment amount.")
        self.assertEqual(profile["resolved_budget"]["amount"], 3000)
        self.assertEqual(profile["conflicts"], [])
        self.assertEqual(len(profile["fields"]["investment_amount"]), 3)
        self.assertEqual(profile["fields"]["investment_amount"][0]["confirmation"], "superseded_by_explicit_correction")

    def test_bond_request_triggers_rate_credit_gaps_without_fake_ratings(self):
        profile = build_profile(plan(conditions=[{"kind": "portfolio", "excerpt": "I hold a bond ETF"}]))
        risks = risk_plan(profile, [asset("BND")], [])
        by_id = {risk["id"]: risk for risk in quantify_risks(risks, profile, [], None)}
        for key in ("interest_rate", "credit"):
            self.assertEqual(by_id[key]["status"], "missing_market_data")
            self.assertEqual(by_id[key]["results"], [])

    def test_willingness_never_generates_an_explicit_cap(self):
        for wording in ("low risk", "near retirement", "very cautious", "high risk"):
            profile = build_profile(plan(conditions=[{"kind": "willingness", "excerpt": wording}]))
            self.assertEqual(explicit_rule_checks(profile, analyze([asset()], None)), [])

    def test_explicit_drawdown_breach_and_unknown_pass_are_distinct(self):
        analyses = analyze([asset()], None)
        for cap, expected in ((10, "observed_breach"), (90, "unknown")):
            profile = build_profile(plan(conditions=[{"kind": "loss", "excerpt": f"Maximum drawdown must not exceed {cap}%."}]))
            self.assertEqual(explicit_rule_checks(profile, analyses)[0]["status"], expected)

    def test_partial_evidence_does_not_claim_full_esg_or_liquidity_coverage(self):
        profile = build_profile(plan(conditions=[{"kind": "esg", "excerpt": "avoid controversy"}]))
        risks = risk_plan(profile, [asset()], analyze([asset()], None))
        risks = quantify_risks(risks, profile, analyze([asset()], None), None)
        by_id = {risk["id"]: risk for risk in risks}
        self.assertEqual(by_id["controversy"]["status"], "needs_client_information")
        self.assertEqual(by_id["historical_market"]["status"], "assessed")


class WithdrawalAndInflationTests(unittest.TestCase):
    def test_withdrawals_expose_shortfalls_and_separate_no_withdrawal_path(self):
        profile = build_profile(plan(conditions=[{"kind": "withdrawal", "excerpt": "Withdraw 500 CAD monthly for 24 months, starting next month."}]))
        schedule, error = withdrawal_schedule(profile)
        self.assertIsNone(error)
        result = replay_withdrawals(history(), 3000, schedule)
        self.assertEqual(result["total_requested"], 12000)
        self.assertGreater(result["shortfall"], 9000)
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(result["without_withdrawals"], 1800)
        self.assertGreater(result["withdrawals_during_declines"], 0)
        self.assertTrue(all(point["with_withdrawals"] >= 0 for point in result["path"]))

    def test_short_history_does_not_become_a_long_term_success_estimate(self):
        schedule = {"amount": 500, "first_month": 24, "count": 1, "frequency": "once"}
        with self.assertRaisesRegex(ValueError, "shorter"):
            replay_withdrawals(history(6), 3000, schedule)

    def test_missing_withdrawal_start_or_currency_asks_instead_of_assuming(self):
        for excerpt in ("Withdraw 500 CAD monthly for 24 months.", "Withdraw $500 monthly for 24 months, starting next month."):
            profile = build_profile(plan(conditions=[{"kind": "withdrawal", "excerpt": excerpt}]))
            schedule, missing = withdrawal_schedule(profile)
            self.assertIsNone(schedule)
            self.assertTrue(missing)

    def test_cpi_deflates_cad_returns_with_month_alignment(self):
        rows = [{"date": "2025-01-31", "price": 100}, {"date": "2025-02-28", "price": 110}, {"date": "2025-03-31", "price": 115}]
        cpi = {"rows": [{"month": "2025-01", "index": 100}, {"month": "2025-02", "index": 105}], "source_url": "https://example.org/cpi"}
        result = purchasing_power(rows, cpi)
        self.assertEqual(result["end"], "2025-02-28")
        self.assertAlmostEqual(result["real_return"], 1.1 / 1.05 - 1)
        self.assertLess(result["real_return"], result["nominal_return"])

    def test_complete_stated_weights_are_used_for_withdrawal_replay(self):
        a, b = asset("SPY", "CAD"), asset("AGG", "CAD")
        a["rows"] = history()
        b["rows"] = [{**row, "price": 100} for row in history()]
        request = plan(conditions=[{"kind": "portfolio", "excerpt": "60% SPY and 40% AGG"},
                                  {"kind": "withdrawal", "excerpt": "Withdraw 500 CAD in 6 months."}])
        profile = build_profile(request)
        self.assertEqual(profile["weights"], {"SPY": .6, "AGG": .4})
        analyses = analyze([a, b], request["budget"])
        risks = quantify_risks(risk_plan(profile, [a, b], analyses), profile, analyses, request["budget"])
        cash = next(risk for risk in risks if risk["id"] == "cash_needs")
        self.assertEqual(cash["results"][0]["symbol"], "Stated portfolio")
        self.assertEqual(len(cash["results"]), 1)

    def test_dated_bond_disclosure_has_reviewed_duration_and_unknown_residual(self):
        records, gaps = qualified_bond_disclosures(["AGG", "BND"], "2026-11-16")
        self.assertIn("BND", gaps)
        duration = duration_scenarios(records["AGG"])
        self.assertAlmostEqual(duration["scenarios"][1]["approximate_price_change"], -.057)
        credit = credit_breakdown(records["AGG"])
        self.assertAlmostEqual(credit["unclassified_or_rounding_weight"], .0001)
        self.assertEqual(credit["reported_below_investment_grade"], 0)
        self.assertIn("Treasury", credit["sector_weights"])

    def test_future_or_stale_bond_disclosures_are_not_used(self):
        for day in ("2026-11-15", "2027-01-16"):
            records, gaps = qualified_bond_disclosures(["AGG"], day)
            self.assertEqual(records, {})
            self.assertIn("AGG", gaps)


class ExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_contains_charts_and_escapes_user_markup(self):
        provider = Mock(asset=Mock(return_value=asset()), fx=Mock(return_value=fx()))
        with patch("datathon.customer_workflow.understand", AsyncMock(return_value=plan())):
            report = await research_question('<script>alert("test")</script> AMD', provider=provider)
        html = report_html(report)
        self.assertEqual(html.count('<svg '), 2)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('observed', html)


if __name__ == "__main__":
    unittest.main()
