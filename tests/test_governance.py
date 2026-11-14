import copy
import unittest

from datathon.governance import audit_decision


DATES = ("2022-01-03", "2022-06-13", "2022-12-30")
BASELINE = {"SPY": .35, "XIU.TO": .25, "QQQ": .20, "ZST.TO": .20, "NVDA": 0.0}
PRICES = {
    ticker: dict(zip(DATES, closes))
    for ticker, closes in {
        "SPY": (100, 83, 87),
        "XIU.TO": (100, 85, 87),
        "QQQ": (100, 70, 75),
        "ZST.TO": (100, 100, 100),
        "NVDA": (100, 30, 74),
    }.items()
}
EVIDENCE = {
    "basis": "CAD",
    "price_source": "fixture:prices",
    "fx_source": "fixture:fx",
    "fx_dates": DATES,
}
POLICY = {
    "metric": "terminal_loss", "loss_limit": .14, "reserve_floor": .15, "target": .10,
    "allowed_sources": ("QQQ", "ZST.TO"),
    "windows": ({"id": "stress", "start": DATES[0], "end": DATES[-1]},),
}


def fund(qqq=0, zst=0):
    return {**BASELINE, "QQQ": .20 - qqq, "ZST.TO": .20 - zst, "NVDA": qqq + zst}


def reported(weights, terminal_loss, max_drawdown):
    return {
        "weights": weights,
        "windows": {"stress": {
            "terminal_loss": terminal_loss,
            "max_drawdown": max_drawdown,
            "peak_date": DATES[0],
            "trough_date": DATES[1],
            "observations": 3,
        }},
    }


def holdings_snapshot():
    return {
        "as_of": "2026-06-30",
        "holdings": {
            **{ticker: {"weight": .076, "status": "disclosed", "published_on": "2026-08-28",
                        "url": "https://example.com/fixture/filing"} for ticker in ("SPY", "QQQ")},
            **{ticker: {"weight": 0.0, "status": "scope_assumption",
                        "url": "https://example.com/fixture/issuer"} for ticker in ("XIU.TO", "ZST.TO")},
        },
    }


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.proposal = fund(zst=.10)
        self.best = fund(qqq=.10)
        self.metrics = {
            "baseline": reported(BASELINE, .128, .157),
            "proposal": reported(self.proposal, .154, .227),
            "maximum": reported(self.best, .129, .197),
            "solver_status": "feasible_full",
            "frontier": {
                "requested_total": .10, "max_total": .10, "full_possible": True,
                "full_zst_min": 0.0, "full_zst_max": .044,
                "full_zst_min_binding": "funding_domain", "full_zst_max_binding": "terminal_loss",
            },
        }

    def audit(self, **overrides):
        inputs = {
            "prices_cad": PRICES, "baseline": BASELINE, "proposal": self.proposal,
            "maximum": self.best, "policy": POLICY, "metrics": self.metrics, "evidence": EVIDENCE,
        }
        return audit_decision(**{**inputs, **overrides})

    def findings(self, result):
        return {row["metric_id"]: row for row in result["findings"]}

    def test_terminal_cap_fails_request_but_supports_full_counterfactual(self):
        audit = self.audit()
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(audit["verified"]["maximum"]["passes"])
        self.assertEqual(audit["verified"]["solver_status"], "feasible_full")
        self.assertAlmostEqual(audit["verified"]["frontier"]["full_zst_max"], .044)
        self.assertAlmostEqual(audit["verified"]["frontier"]["best_funding"]["QQQ"], .10)

    def test_drawdown_yields_independent_no_solution_and_rejects_bad_witness(self):
        policy = {**POLICY, "metric": "max_drawdown"}
        certificate = {
            "type": "single_constraint", "rule": "max_drawdown", "window_id": "stress",
            "observation_date": DATES[1], "peak_date": DATES[0], "bound": .14,
            "affine_constant": -.017, "coefficients": {"QQQ": -.4, "ZST.TO": -.7},
            "max_slack": -.017,
        }
        metrics = {**self.metrics, "solver_status": "no_feasible", "frontier": None, "certificate": certificate}
        audit = self.audit(maximum=None, policy=policy, metrics=metrics)
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(audit["verified"]["no_feasible_confirmed"])
        self.assertEqual(self.findings(audit)["frontier.certificate"]["status"], "pass")
        certificate["coefficients"]["QQQ"] = .4
        tampered = self.audit(maximum=None, policy=policy, metrics=metrics)
        self.assertEqual(tampered["status"], "invalid")

    def test_metric_and_frontier_tampering_withhold_result(self):
        self.metrics["proposal"]["windows"]["stress"]["terminal_loss"] = .01
        self.metrics["frontier"]["full_zst_max"] = .05
        audit = self.audit()
        self.assertEqual(audit["status"], "invalid")
        self.assertEqual(self.findings(audit)["proposal.stress.terminal_loss"]["status"], "invalid")
        self.assertEqual(self.findings(audit)["frontier.full_zst_max"]["status"], "invalid")

    def test_copied_candidate_pass_and_funding_are_verified(self):
        candidate = {"weights": self.best, "funding": {"QQQ": .05, "ZST.TO": .05}, "passes": False}
        audit = self.audit(maximum=candidate)
        self.assertEqual(audit["status"], "invalid")
        self.assertEqual(self.findings(audit)["maximum.funding"]["status"], "invalid")
        self.assertEqual(self.findings(audit)["maximum.passes"]["status"], "invalid")

    def test_missing_frozen_endpoint_or_currency_provenance_blocks_decision(self):
        prices = copy.deepcopy(PRICES)
        del prices["NVDA"][DATES[-1]]
        audit = self.audit(prices_cad=prices)
        self.assertEqual(audit["status"], "insufficient_evidence")
        self.assertEqual(audit["verified"], {})
        audit = self.audit(evidence={**EVIDENCE, "fx_source": ""})
        self.assertEqual(audit["status"], "insufficient_evidence")

    def test_unsupported_funding_source_is_invalid(self):
        policy = {**POLICY, "allowed_sources": ("QQQ",)}
        audit = self.audit(policy=policy)
        self.assertEqual(audit["status"], "invalid")
        self.assertEqual(self.findings(audit)["input.validation"]["status"], "invalid")

    def test_known_exposure_can_exceed_cap_despite_other_unknown_positions(self):
        policy = {**POLICY, "loss_limit": None, "reserve_floor": 0, "issuer_cap": .14}
        evidence = {**EVIDENCE, "issuer_snapshot": holdings_snapshot()}
        metrics = {**self.metrics, "solver_status": "insufficient_issuer_evidence", "frontier": None}
        audit = self.audit(maximum=None, policy=policy, evidence=evidence, metrics=metrics)
        exposure = self.findings(audit)["proposal.issuer_weight.policy"]
        self.assertEqual(audit["status"], "fail")
        self.assertGreater(exposure["actual"]["lower"], .14)
        self.assertEqual(audit["verified"]["frontier"]["status"], "insufficient_evidence")

    def test_missing_qqq_cannot_be_treated_as_zero(self):
        policy = {**POLICY, "loss_limit": None, "reserve_floor": 0, "issuer_cap": .14,
                  "issuer_exposure": {"SPY": .076, "QQQ": 0.0, "XIU.TO": 0.0, "ZST.TO": 0.0}}
        snapshot = holdings_snapshot()
        snapshot["holdings"]["QQQ"].update(weight=None, status="unknown", url=None)
        evidence = {**EVIDENCE, "issuer_snapshot": snapshot, "permitted_scope_assumptions": ("XIU.TO", "ZST.TO")}
        metrics = {**self.metrics, "solver_status": "insufficient_issuer_evidence", "frontier": None}
        audit = self.audit(maximum=None, policy=policy, evidence=evidence, metrics=metrics)
        exposure = self.findings(audit)["proposal.issuer_weight.policy"]
        self.assertEqual(audit["status"], "insufficient_evidence")
        self.assertLess(exposure["actual"]["lower"], .14)
        self.assertGreater(exposure["actual"]["upper"], .14)

    def test_scope_assumptions_require_explicit_opt_in(self):
        policy = {**POLICY, "loss_limit": None, "reserve_floor": 0, "issuer_cap": .14}
        evidence = {**EVIDENCE, "issuer_snapshot": holdings_snapshot(),
                    "permitted_scope_assumptions": ("XIU.TO", "ZST.TO")}
        full_zst_max = (.14 - (.10 + .45 * .076)) / .076
        metrics = {**self.metrics, "frontier": {**self.metrics["frontier"], "full_zst_max": full_zst_max,
                                               "full_zst_max_binding": "issuer_cap"}}
        audit = self.audit(policy=policy, evidence=evidence, metrics=metrics)
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(audit["verified"]["maximum"]["passes"])
        self.assertAlmostEqual(audit["verified"]["frontier"]["full_zst_max"], full_zst_max)

    def test_partial_counterfactual_respects_only_permitted_source(self):
        partial = fund(zst=.012 / .26)
        policy = {**POLICY, "allowed_sources": ("ZST.TO",)}
        terminal_loss = .14
        drawdown = .157 + .7 * partial["NVDA"]
        metrics = {
            **self.metrics, "maximum": reported(partial, terminal_loss, drawdown),
            "frontier": None, "solver_status": "feasible_partial",
        }
        audit = self.audit(maximum=partial, policy=policy, metrics=metrics)
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(audit["verified"]["maximum"]["passes"])
        self.assertEqual(audit["verified"]["solver_status"], "feasible_partial")
        self.assertAlmostEqual(audit["verified"]["frontier"]["max_total"], .012 / .26)

    def test_dates_free_concentration_certificate_is_recomputed(self):
        policy = {**POLICY, "loss_limit": None, "reserve_floor": 0, "issuer_cap": .02}
        evidence = {**EVIDENCE, "issuer_snapshot": holdings_snapshot()}
        certificate = {
            "type": "single_constraint", "rule": "issuer_cap", "window_id": None,
            "observation_date": None, "peak_date": None, "bound": .02,
            "affine_constant": .02 - .55 * .076, "coefficients": {"QQQ": -.924, "ZST.TO": -1.0},
            "max_slack": .02 - .55 * .076,
        }
        metrics = {**self.metrics, "solver_status": "no_feasible", "frontier": None, "certificate": certificate}
        audit = self.audit(maximum=None, policy=policy, evidence=evidence, metrics=metrics)
        self.assertTrue(audit["verified"]["no_feasible_confirmed"])
        self.assertEqual(self.findings(audit)["frontier.certificate"]["status"], "pass")
        certificate["rule"] = "reserve_floor"
        tampered = self.audit(maximum=None, policy=policy, evidence=evidence, metrics=metrics)
        self.assertEqual(tampered["status"], "invalid")
