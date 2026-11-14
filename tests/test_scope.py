"""Verify a confirmed custom portfolio and an unused, fixed starter-data window."""

import copy
import os
import unittest

from datathon.agents import AgentRun
from datathon.counterfactual import run_counterfactual
from datathon.data import load_market_data
from datathon.scope import ReplayScope
from datathon.workflow import Case, examples, preset_profile, profile_policy, run_case


HOLDOUT_WEIGHTS = {"SPY": 3000, "XIU.TO": 2000, "QQQ": 1000, "ZST.TO": 3700, "NVDA": 300}


def holdout_profile():
    return {
        **preset_profile(examples("robert")[0]),
        "target_bps": 2200,
        "limit_bps": 1600,
    }


class ReplayScopeTests(unittest.IsolatedAsyncioTestCase):
    def test_weights_are_validated_and_frozen_at_construction(self):
        with self.assertRaisesRegex(ValueError, "totaling exactly 100%"):
            ReplayScope({**HOLDOUT_WEIGHTS, "ZST.TO": 3699})
        with self.assertRaisesRegex(ValueError, "all five supported weights"):
            ReplayScope({**HOLDOUT_WEIGHTS, "TLT": 0})
        with self.assertRaisesRegex(ValueError, "all five supported weights"):
            ReplayScope({**HOLDOUT_WEIGHTS, "NVDA": 300.0})
        original = dict(HOLDOUT_WEIGHTS)
        scope = ReplayScope(original)
        original["ZST.TO"] = 0
        self.assertEqual(scope.baseline["ZST.TO"], .37)
        self.assertEqual(scope.baseline["NVDA"], .03)

    def test_profile_checks_trade_against_the_confirmed_starting_fund(self):
        with self.assertRaisesRegex(ValueError, "exceeds the starting ZST.TO position"):
            profile_policy(holdout_profile())
        scoped_policy = profile_policy(holdout_profile(), baseline=ReplayScope(HOLDOUT_WEIGHTS).baseline)
        self.assertEqual(scoped_policy["target"], .22)

    @unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH for the official-data holdout.")
    async def test_independent_holdout_and_follow_up_preserve_the_custom_scope(self):
        market = load_market_data()
        scope = ReplayScope(HOLDOUT_WEIGHTS, True, "Fund a planned withdrawal", "Within 1 year")
        case = Case("confirmed-scope", "Fictional request", "terminal_loss", .16, .15, scope=scope)
        report = await run_case(market, case, confirmed_profile=AgentRun("ok", holdout_profile()))
        self.assertEqual(report["confirmed_scope"], scope.report())
        self.assertEqual(report["policy"]["reserve_floor"], .15)
        self.assertEqual(report["evidence"]["windows"], ["2022", "2023", "2025"])
        self.assertEqual(report["decision_reason"], "feasible_partial")
        verified = report["audit"]["verified"]
        self.assertEqual(verified["baseline"]["weights"], scope.baseline)
        self.assertAlmostEqual(verified["proposal"]["weights"]["NVDA"], .25)
        self.assertAlmostEqual(verified["proposal"]["weights"]["ZST.TO"], .15)
        window = verified["proposal"]["windows"]["2023"]
        shown = report["scenarios"]["proposal"]["windows"]["2023"]
        self.assertEqual((shown["start"], shown["end"], window["observations"]),
                         ("2023-07-31", "2023-10-31", 63))
        # Independently derived from raw adjusted-close and FX CSVs using Decimal.
        self.assertAlmostEqual(window["terminal_loss"], .04757859020935288)
        self.assertAlmostEqual(window["max_drawdown"], .08019026898343411)
        self.assertAlmostEqual(verified["frontier"]["max_total"], .21049911108903806)
        self.assertTrue(verified["maximum"]["passes"])

        original = copy.deepcopy(report)
        check = await run_counterfactual(market, case, report, option_id="toggle_loss_metric")
        self.assertEqual(check["status"], "verified")
        self.assertEqual(check["changed_fields"], ["metric"])
        self.assertEqual(check["replay"]["confirmed_scope"], original["confirmed_scope"])
        self.assertEqual(check["replay"]["policy"], {**report["policy"], "metric": "max_drawdown"})
        self.assertEqual(report, original)
