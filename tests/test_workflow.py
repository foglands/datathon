import unittest
from unittest.mock import patch

from datathon.__main__ import validate_case
from datathon.agents import AgentRun
from datathon.workflow import interpret_request, profile_policy


PROFILE = {
    "status": "ok", "target_bps": 800, "initial_source": "QQQ", "allowed_sources": ["QQQ"],
    "metric": "terminal_loss", "limit_bps": 1300, "reserve_floor_bps": 1800,
    "allow_smaller": False, "prefer_reserve": None,
}


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_policy_uses_user_amount_source_and_explicit_size_rule(self):
        policy = profile_policy(PROFILE)
        self.assertEqual((policy["target"], policy["initial_source"], policy["allowed_sources"]), (.08, "QQQ", ("QQQ",)))
        self.assertEqual((policy["loss_limit"], policy["reserve_floor"]), (.13, .18))
        self.assertIs(policy["allow_smaller"], False)

    def test_unstated_size_permission_and_conflicting_source_need_clarification(self):
        with self.assertRaisesRegex(ValueError, "smaller purchase"):
            profile_policy({**PROFILE, "allow_smaller": None})
        with self.assertRaisesRegex(ValueError, "excluded"):
            profile_policy({**PROFILE, "allowed_sources": ["ZST.TO"]})

    async def test_ambiguous_model_response_bypasses_policy_compilation(self):
        class Runtime:
            async def run(self, role, payload, *, run_id):
                return AgentRun("needs_input", {"status": "needs_input", "summary": "Terminal loss or maximum drawdown?"})

        with patch("datathon.workflow.profile_policy") as compile_policy:
            _, policy, clarification = await interpret_request("I can lose at most 14%.", Runtime(), "test")
        self.assertIsNone(policy)
        self.assertIn("maximum drawdown", clarification)
        compile_policy.assert_not_called()

    def test_fixture_rejects_wrong_verdict_and_wrong_verified_boundary(self):
        result = {"case": "robert_terminal", "status": "fail", "alternatives": {"status": "feasible_full"},
                  "audit": {"verified": {"frontier": {"full_zst_max": .02631671476152258}, "maximum": {"passes": True}}}}
        self.assertTrue(validate_case(result))
        self.assertFalse(validate_case({**result, "status": "pass"}))
        result["audit"]["verified"]["frontier"]["full_zst_max"] = .05
        self.assertFalse(validate_case(result))
