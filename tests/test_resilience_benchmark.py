"""Regression checks for the paired workflow fault benchmark."""

import unittest
from types import SimpleNamespace

from datathon.resilience_benchmark import ARMS, SCENARIOS, _audit_arguments, _evaluate, _market_input
from datathon.workflow import run_case
from tests.test_tool_routing import MARKET


class ResilienceBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_matched_faults_recover_or_withhold_before_releasing_results(self):
        args = SimpleNamespace(mode="scripted", model="scripted-model", region="us-east-1")
        references = {}
        by_scenario = {}
        for scenario in SCENARIOS:
            data = _market_input(MARKET, scenario)
            fixture = scenario.fixture.workflow_case()
            key = (fixture.id, scenario.drop_fx_endpoint)
            if key not in references:
                references[key] = await run_case(data, fixture, **_audit_arguments(scenario))
            rows = {}
            for arm in ARMS:
                with self.subTest(scenario=scenario.id, arm=arm):
                    row = await _evaluate(data, scenario, arm, references[key], args)
                    self.assertTrue(row["checked_outcome"], row)
                    self.assertFalse(row["unsafe_release"])
                    self.assertEqual(row["converse"], 0)
                    self.assertIsNone(row["input_tokens"])
                    self.assertEqual(row["injected_fault_observed"], scenario.scripted_fault is not None)
                    rows[arm] = row
            by_scenario[scenario.id] = rows

        invalid = by_scenario["persistent_invalid_route"]
        self.assertEqual(invalid["staged"]["routing_fallbacks"], 1)
        self.assertTrue(invalid["staged"]["verified_recovery"])
        self.assertTrue(invalid["bundled"]["held_eligible_control"])
        self.assertFalse(invalid["bundled"]["completed_independent_review"])

        corrected = by_scenario["corrected_invalid_route"]
        for arm, row in corrected.items():
            self.assertTrue(row["verified_recovery"])
            self.assertEqual(row["validated_tool_rejections"], 1)
            self.assertEqual(row["routing_fallbacks"], int(arm == "staged"))
        self.assertEqual(corrected["staged"]["scripted_tool_attempts"] + 1,
                         corrected["bundled"]["scripted_tool_attempts"])

        absent = by_scenario["absent_review_callback"]
        for row in absent.values():
            self.assertFalse(row["completed_independent_review"])
            self.assertFalse(row["eligible_alternative"])

        tampered = by_scenario["corrupted_candidate"]
        for row in tampered.values():
            self.assertTrue(row["completed_independent_review"])
            self.assertEqual(row["status"], "invalid")
            self.assertFalse(row["eligible_alternative"])
