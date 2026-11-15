"""The paired cohort uses generated, reproducible input contracts."""

from hashlib import sha256
import os
import unittest

from datathon.paired_benchmark import _authorization_preserved, _calls, _evaluate, generate_cases
from datathon.scope import ReplayScope
from datathon.workflow import profile_policy


class GeneratedCohortTests(unittest.TestCase):
    def test_inputs_are_reproducible_per_seed_and_vary_across_seeds(self):
        cases = generate_cases(123)
        self.assertEqual(cases, generate_cases(123))
        self.assertNotEqual(cases, generate_cases(456))
        self.assertEqual(len(cases), len({entry["id"] for entry in cases}))
        self.assertEqual({entry["kind"] for entry in cases}, {"audit", "review", "profile"})

    def test_generated_structured_inputs_are_valid_across_seeds(self):
        for seed in range(25):
            for entry in generate_cases(seed):
                if entry["kind"] == "profile":
                    continue
                with self.subTest(seed=seed, case=entry["id"]):
                    scope = ReplayScope(entry["weights_bps"], include_2023=entry["include_2023"])
                    policy = profile_policy(
                        entry["profile"], baseline=scope.baseline, search_alternatives=entry["search"],
                    )
                    self.assertLessEqual(policy["target"], scope.baseline[policy["initial_source"]])
                    self.assertEqual(sum(entry["weights_bps"].values()), 10000)

    def test_original_audit_rejects_solver_calls_and_values(self):
        report = {"search_alternatives": False, "audit": {"verified": {}}}
        self.assertTrue(_authorization_preserved({}, report, False))
        self.assertFalse(_authorization_preserved(
            {"trace": [{"tool_name": "solve_funding_range"}]}, report, False,
        ))
        changed = {**report, "audit": {"verified": {"frontier": {}}}}
        self.assertFalse(_authorization_preserved({}, changed, False))
        self.assertFalse(_authorization_preserved({}, {**report, "search_alternatives": True}, True))

    def test_response_receipts_are_hashed_and_failed_calls_are_counted(self):
        request_id = "fixture-request-id"
        rows = [
            {"event": "bedrock", "http_status": 200, "status": "success", "request_id": request_id, "total_tokens": 12},
            {"event": "bedrock", "http_status": 429, "status": "error"},
            {"event": "tool", "status": "deterministic_fallback"},
        ]
        result = _calls(rows)
        self.assertEqual(result["request_id_hashes"], [sha256(request_id.encode()).hexdigest()[:12]])
        self.assertEqual(result["successful_converse"], 1)
        self.assertEqual(result["failed_converse"], 1)
        self.assertEqual(result["observed_tokens"], 12)
        self.assertEqual(result["routing_fallbacks"], 1)
        self.assertNotIn(request_id, repr(result))


@unittest.skipUnless(os.getenv("DATATHON_STARTER_PATH"), "Requires the official starter market data.")
class ReviewManifestTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_can_verify_replay_in_both_search_scopes(self):
        case = next(entry for entry in generate_cases(789) if entry["kind"] == "review")
        for authorized in (False, True):
            with self.subTest(authorized=authorized):
                result = await _evaluate({
                    "case": {**case, "search": authorized},
                    "mode": "offline",
                    "data": os.environ["DATATHON_STARTER_PATH"],
                })
                self.assertTrue(result["passed"], result)
