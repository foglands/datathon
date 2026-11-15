"""Exact-answer regressions for governed historical portfolio formulas."""

from math import fsum
import unittest

from datathon.data import MarketData
from datathon.finance import BASE_WEIGHTS, StressWindow, evaluate_portfolio
from datathon.governance import audit_decision


DATES = ("2022-01-03", "2022-01-04", "2022-01-05")
WINDOW = StressWindow("acceptance", "Three-session formula fixture", DATES[0], DATES[-1])
ALL_SPY = dict.fromkeys(BASE_WEIGHTS, 0.0) | {"SPY": 1.0}
BUY_AND_HOLD_PRICES = {
    "QQQ": (100, 130, 90),
    "ZST.TO": (100, 100, 110),
    "NVDA": (100, 30, 200),
}
ORIGINAL = dict.fromkeys(BASE_WEIGHTS, 0.0) | {"QQQ": 0.6, "ZST.TO": 0.4}
AFTER_PURCHASE = {**ORIGINAL, "QQQ": 0.3, "NVDA": 0.3}


def market_with_prices(price_paths, *, scale=1):
    prices = {
        ticker: dict(zip(DATES, (value * scale for value in price_paths.get(ticker, (100, 100, 100)))))
        for ticker in BASE_WEIGHTS
    }
    return MarketData(prices, dict.fromkeys(DATES, 1.25))


class FormulaAcceptanceTests(unittest.TestCase):
    def replay_and_review(self, market, baseline, proposal, *, target=0.0, loss_limit=None):
        portfolios = {"baseline": baseline, "proposal": proposal}
        replay = {
            leg: evaluate_portfolio(market, weights, windows=(WINDOW,))
            for leg, weights in portfolios.items()
        }
        review = audit_decision(
            prices_cad=market.prices,
            baseline=baseline,
            proposal=proposal,
            policy={
                "metric": "terminal_loss",
                "loss_limit": loss_limit,
                "reserve_floor": 0.0,
                "target": target,
                "allowed_sources": ("QQQ",),
                "windows": (WINDOW,),
            },
            metrics=replay,
            evidence={
                "basis": "CAD",
                "price_source": "fixture:prices",
                "fx_source": "fixture:fx",
                "fx_dates": tuple(market.fx),
            },
            search_alternatives=False,
        )
        self.assertNotIn(review["status"], {"invalid", "insufficient_evidence"}, review["findings"])
        return replay, review

    def assert_risk(self, result, *, terminal_return, terminal_loss, max_drawdown, peak, trough):
        self.assertAlmostEqual(result["terminal_return"], terminal_return, places=12)
        self.assertAlmostEqual(result["terminal_loss"], terminal_loss, places=12)
        self.assertAlmostEqual(result["max_drawdown"], max_drawdown, places=12)
        self.assertEqual((result["peak_date"], result["trough_date"]), (DATES[peak], DATES[trough]))
        self.assertEqual(result["observations"], len(DATES))
        self.assertAlmostEqual(fsum(result["attribution"].values()), terminal_return, places=12)
        self.assertAlmostEqual(fsum(result["drawdown_attribution"].values()), max_drawdown, places=12)

    def assert_single_asset_path(self, closes, **expected):
        market = market_with_prices({"SPY": closes})
        replay, review = self.replay_and_review(market, ALL_SPY, ALL_SPY)
        for calculations in (replay, review["verified"]):
            self.assert_risk(calculations["proposal"]["windows"][WINDOW.id], **expected)

    def test_loss_path_measures_drawdown_from_the_intermediate_peak(self):
        self.assert_single_asset_path(
            (100, 120, 90), terminal_return=-0.10, terminal_loss=0.10, max_drawdown=0.25, peak=1, trough=2,
        )

    def test_profitable_path_retains_its_intraperiod_drawdown(self):
        self.assert_single_asset_path(
            (100, 90, 120), terminal_return=0.20, terminal_loss=0.0, max_drawdown=0.10, peak=0, trough=1,
        )

    def test_constant_prices_and_fx_have_zero_risk_and_return(self):
        self.assert_single_asset_path(
            (100, 100, 100), terminal_return=0.0, terminal_loss=0.0, max_drawdown=0.0, peak=0, trough=0,
        )

    def test_uniform_price_scaling_preserves_risk_and_contributions(self):
        original_replay, original_review = self.replay_and_review(
            market_with_prices(BUY_AND_HOLD_PRICES), ORIGINAL, AFTER_PURCHASE, target=0.3,
        )
        scaled_replay, scaled_review = self.replay_and_review(
            market_with_prices(BUY_AND_HOLD_PRICES, scale=7), ORIGINAL, AFTER_PURCHASE, target=0.3,
        )
        for original, scaled in ((original_replay, scaled_replay),
                                 (original_review["verified"], scaled_review["verified"])):
            for leg in ("baseline", "proposal"):
                left, right = (item[leg]["windows"][WINDOW.id] for item in (original, scaled))
                for field in ("terminal_return", "terminal_loss", "max_drawdown"):
                    self.assertAlmostEqual(left[field], right[field], places=12)
                for field in ("attribution", "drawdown_attribution"):
                    for ticker in BASE_WEIGHTS:
                        self.assertAlmostEqual(left[field][ticker], right[field][ticker], places=12)

    def test_signed_contributions_use_buy_and_hold_and_each_portfolios_own_peak(self):
        replay, review = self.replay_and_review(
            market_with_prices(BUY_AND_HOLD_PRICES), ORIGINAL, AFTER_PURCHASE, target=0.3,
        )
        for leg, path in (("baseline", (1.0, 1.18, 0.98)), ("proposal", (1.0, 0.88, 1.31))):
            result = replay[leg]["windows"][WINDOW.id]
            for value, expected in zip(result["values"], path, strict=True):
                self.assertAlmostEqual(value, expected, places=12)
        for calculations in (replay, review["verified"]):
            baseline = calculations["baseline"]["windows"][WINDOW.id]
            self.assert_risk(baseline, terminal_return=-0.02, terminal_loss=0.02,
                             max_drawdown=10 / 59, peak=1, trough=2)
            self.assertAlmostEqual(baseline["attribution"]["QQQ"], -0.06, places=12)
            self.assertAlmostEqual(baseline["attribution"]["ZST.TO"], 0.04, places=12)
            self.assertAlmostEqual(baseline["drawdown_attribution"]["QQQ"], 12 / 59, places=12)
            self.assertAlmostEqual(baseline["drawdown_attribution"]["ZST.TO"], -2 / 59, places=12)

            proposal = calculations["proposal"]["windows"][WINDOW.id]
            self.assert_risk(proposal, terminal_return=0.31, terminal_loss=0.0,
                             max_drawdown=0.12, peak=0, trough=1)
            self.assertAlmostEqual(proposal["attribution"]["QQQ"], -0.03, places=12)
            self.assertAlmostEqual(proposal["attribution"]["NVDA"], 0.30, places=12)
            self.assertAlmostEqual(proposal["drawdown_attribution"]["QQQ"], -0.09, places=12)
            self.assertAlmostEqual(proposal["drawdown_attribution"]["NVDA"], 0.21, places=12)

    def test_limit_check_uses_unrounded_loss(self):
        for close, expected_status in ((86.0, "pass"), (85.996, "fail")):
            with self.subTest(close=close):
                market = market_with_prices({"SPY": (100, 100, close)})
                _, review = self.replay_and_review(market, ALL_SPY, ALL_SPY, loss_limit=0.14)
                rule = next(row for row in review["findings"] if row["metric_id"] == "proposal.terminal_loss.policy")
                self.assertEqual(review["status"], expected_status)
                self.assertEqual(rule["status"], expected_status)
                self.assertEqual(f"{rule['actual']:.2%}", "14.00%")
