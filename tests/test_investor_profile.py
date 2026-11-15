"""Verify contextual priority suggestions preserve confirmed choices."""

import json
import unittest

from datathon.investor_profile import InvestorProfile, suggest_priority


class InvestorProfileTests(unittest.TestCase):
    def test_objective_and_withdrawal_horizon_change_suggested_priority(self):
        self.assertEqual(suggest_priority("Growth", "Within 1 year"), "max_drawdown")
        self.assertEqual(suggest_priority("Growth", "1 to 5 years"), "terminal_loss")
        self.assertEqual(suggest_priority("Growth", "More than 5 years"), "terminal_return")
        self.assertEqual(suggest_priority("Capital preservation", "More than 5 years"), "max_drawdown")
        self.assertEqual(suggest_priority("Fund a planned withdrawal", "More than 5 years"), "terminal_loss")

    def test_risk_willingness_influences_growth_without_overriding_near_term_withdrawal(self):
        self.assertEqual(suggest_priority("Growth", "More than 5 years", "Low"), "max_drawdown")
        self.assertEqual(suggest_priority("Growth", "More than 5 years", "High"), "terminal_return")
        self.assertEqual(suggest_priority("Growth", "Within 1 year", "High"), "max_drawdown")
        self.assertEqual(suggest_priority("Capital preservation", "More than 5 years", "High"), "max_drawdown")
        profile = InvestorProfile("Growth", "More than 5 years", "max_drawdown", risk_tolerance="Low")
        self.assertIn("low stated willingness", profile.explanation)
        self.assertEqual(profile.report()["risk_tolerance"], "Low")

    def test_confirmed_priority_controls_focus_and_is_preserved_in_export(self):
        profile = InvestorProfile("Growth", "Within 1 year", "terminal_return", require_esg=True)
        self.assertIsNone(profile.audit_focus)
        self.assertIn("withdrawal within one year", profile.explanation)
        self.assertIn("confirmed comparison priority is terminal return", profile.explanation)
        self.assertEqual(json.loads(json.dumps(profile.report())), {
            "objective": "Growth",
            "withdrawal_time": "Within 1 year",
            "priority": "terminal_return",
            "require_esg": True,
            "risk_tolerance": None,
            "explanation": profile.explanation,
        })

    def test_profile_rejects_unconfirmed_or_unsupported_inputs(self):
        with self.assertRaisesRegex(ValueError, "objective"):
            InvestorProfile("Unknown", "Within 1 year", "max_drawdown")
        with self.assertRaisesRegex(ValueError, "horizon"):
            InvestorProfile("Growth", "Unknown", "max_drawdown")
        with self.assertRaisesRegex(ValueError, "priority"):
            InvestorProfile("Growth", "Within 1 year", [])
        with self.assertRaisesRegex(ValueError, "ESG evidence"):
            InvestorProfile("Growth", "Within 1 year", "max_drawdown", require_esg="yes")
        with self.assertRaisesRegex(ValueError, "willingness"):
            InvestorProfile("Growth", "Within 1 year", "max_drawdown", risk_tolerance="max")

    def test_plain_and_partial_requests_can_keep_or_select_a_priority(self):
        self.assertIsNone(suggest_priority())
        self.assertIsNone(suggest_priority("Growth"))
        self.assertEqual(suggest_priority("Capital preservation"), "max_drawdown")
        self.assertEqual(suggest_priority(withdrawal_time="Within 1 year"), "max_drawdown")
        self.assertIsNone(InvestorProfile().report()["priority"])
        self.assertIsNone(InvestorProfile("Capital preservation").audit_focus)
        explicit = InvestorProfile(priority="max_drawdown")
        self.assertEqual(explicit.audit_focus, "max_drawdown")
        self.assertIn("confirmed comparison priority is maximum drawdown", explicit.explanation)
