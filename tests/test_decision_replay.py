from copy import deepcopy
from math import isclose, sqrt
from statistics import stdev
from datetime import date, timedelta
from random import Random
from unittest import TestCase

from datathon.decision_replay import evaluate, stress_percentile, verify, verify_stress_percentile


class DecisionReplayTest(TestCase):
    def setUp(self):
        self.dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-05", "2024-01-10"]
        self.weights = {"ASSET": 1.0}
        self.prices = {"ASSET": [100, 110, 88, 110, 100]}

    def checked(self, weights, dates, prices, local=None):
        claimed = evaluate(weights, dates, prices, local)
        return verify(weights, dates, prices, claimed, local)

    def test_recovery_and_sample_volatility(self):
        checked = self.checked(self.weights, self.dates, self.prices)
        self.assertAlmostEqual(checked["terminal_return"], 0)
        self.assertAlmostEqual(checked["terminal_loss"], 0)
        self.assertAlmostEqual(checked["max_drawdown"], 0.2)
        self.assertEqual(checked["peak_date"], "2024-01-02")
        self.assertEqual(checked["trough_date"], "2024-01-03")
        self.assertEqual(checked["recovery_status"], "recovered")
        self.assertEqual(checked["recovery_date"], "2024-01-05")
        self.assertEqual(checked["recovery_days"], 3)
        self.assertEqual(checked["days_underwater"], 3)
        self.assertAlmostEqual(
            checked["annualized_volatility"], sqrt(252) * stdev([0.1, -0.2, 0.25, -1 / 11]),
        )

    def test_unrecovered_drawdown_and_first_tied_peak(self):
        prices = {"ASSET": [100, 120, 120, 90, 95]}
        checked = self.checked(self.weights, self.dates, prices)
        self.assertEqual(checked["peak_date"], "2024-01-02")
        self.assertEqual(checked["trough_date"], "2024-01-05")
        self.assertEqual(checked["recovery_status"], "unrecovered")
        self.assertIsNone(checked["recovery_date"])
        self.assertIsNone(checked["recovery_days"])
        self.assertEqual(checked["days_underwater"], 8)
        self.assertAlmostEqual(checked["terminal_loss"], 0.05)

    def test_first_equal_worst_drawdown_is_selected(self):
        prices = {"ASSET": [100, 80, 100, 80, 90]}
        checked = self.checked(self.weights, self.dates, prices)
        self.assertEqual(checked["peak_date"], "2024-01-01")
        self.assertEqual(checked["trough_date"], "2024-01-02")
        self.assertEqual(checked["recovery_date"], "2024-01-03")

    def test_no_drawdown_and_insufficient_risk_samples(self):
        checked = self.checked(self.weights, self.dates[:2], {"ASSET": [10, 30]})
        self.assertAlmostEqual(checked["terminal_return"], 2)
        self.assertEqual(checked["max_drawdown"], 0)
        self.assertEqual(checked["recovery_status"], "no_drawdown")
        self.assertEqual(checked["recovery_days"], 0)
        self.assertEqual(checked["days_underwater"], 0)
        self.assertIsNone(checked["annualized_volatility"])
        self.assertEqual(checked["rolling"]["12m"]["observation_count"], 0)
        self.assertIsNone(checked["rolling"]["36m"]["worst_return"])
        self.assertIsNone(checked["worst_month"]["return"])
        self.assertIsNone(checked["fx_decomposition"])

    def test_rolling_calendar_anniversaries_and_earliest_tie(self):
        dates = [
            "2020-02-28", "2020-02-29", "2020-03-01", "2021-02-27", "2021-02-28", "2021-03-01",
            "2023-02-28", "2023-03-01", "2024-02-29",
        ]
        prices = {"ASSET": [100, 200, 100, 40, 50, 20, 30, 10, 5]}
        rolling = self.checked(self.weights, dates, prices)["rolling"]
        self.assertEqual(rolling["12m"]["observation_count"], 5)
        self.assertEqual(rolling["12m"]["start_date"], "2023-02-28")
        self.assertEqual(rolling["12m"]["end_date"], "2024-02-29")
        self.assertAlmostEqual(rolling["12m"]["worst_return"], -5 / 6)
        self.assertEqual(rolling["36m"]["observation_count"], 3)
        self.assertEqual(rolling["36m"]["start_date"], "2020-03-01")
        self.assertEqual(rolling["36m"]["end_date"], "2023-03-01")
        self.assertAlmostEqual(rolling["36m"]["worst_return"], -0.9)

    def test_worst_month_requires_consecutive_complete_period(self):
        dates = ["2023-01-31", "2023-02-28", "2023-03-31", "2023-05-31", "2023-06-15"]
        prices = {"ASSET": [100, 90, 99, 60, 30]}
        monthly = self.checked(self.weights, dates, prices)["worst_month"]
        self.assertEqual(monthly["month"], "2023-02")
        self.assertEqual(monthly["observation_count"], 2)
        self.assertEqual(monthly["start_date"], "2023-01-31")
        self.assertEqual(monthly["end_date"], "2023-02-28")
        self.assertAlmostEqual(monthly["return"], -0.1)

    def test_weighted_attribution_and_reconciled_fx_decomposition(self):
        weights = {"FIRST": 0.6, "SECOND": 0.4, "ZERO": 0}
        cad = {"FIRST": [100, 132, 99], "SECOND": [100, 110, 100], "ZERO": [5, 15, 10]}
        local = {"FIRST": [100, 110, 90], "SECOND": [100, 110, 100], "ZERO": [3, 4, 5]}
        checked = self.checked(weights, self.dates[:3], cad, local)
        fx = checked["fx_decomposition"]
        self.assertAlmostEqual(checked["terminal_return"], -0.006)
        self.assertAlmostEqual(checked["attribution"]["FIRST"], -0.006)
        self.assertAlmostEqual(checked["attribution"]["ZERO"], 0)
        self.assertAlmostEqual(checked["drawdown_attribution"]["FIRST"], 0.6 * 0.33 / 1.232)
        self.assertAlmostEqual(checked["drawdown_attribution"]["SECOND"], 0.4 * 0.1 / 1.232)
        self.assertAlmostEqual(sum(checked["drawdown_attribution"].values()), checked["max_drawdown"])
        self.assertAlmostEqual(fx["by_ticker"]["SECOND"]["fx_impact"], 0)
        self.assertAlmostEqual(fx["local_return"], -0.06)
        self.assertAlmostEqual(fx["fx_return"], 0.06)
        self.assertAlmostEqual(fx["interaction_return"], -0.006)
        self.assertAlmostEqual(fx["fx_impact"], 0.054)
        self.assertTrue(isclose(fx["cad_return"], fx["local_return"] + fx["fx_impact"]))

    def test_tampering_with_recovery_rolling_attribution_or_fx_is_rejected(self):
        local = {"ASSET": [100, 109, 90, 109, 80]}
        calculated = evaluate(self.weights, self.dates, self.prices, local)
        cases = [
            (("recovery_days",), 2),
            (("rolling", "36m", "observation_count"), 7),
            (("annualized_volatility",), 0),
            (("drawdown_attribution", "ASSET"), 1),
            (("fx_decomposition", "by_ticker", "ASSET", "fx_impact"), 0),
        ]
        for path, changed in cases:
            with self.subTest(path=path):
                claimed = deepcopy(calculated)
                group = claimed
                for key in path[:-1]:
                    group = group[key]
                group[path[-1]] = changed
                with self.assertRaisesRegex(ValueError, r"\.".join(path)):
                    verify(self.weights, self.dates, self.prices, claimed, local)
        del calculated["observations"]
        with self.assertRaisesRegex(ValueError, "Independent replay verification"):
            verify(self.weights, self.dates, self.prices, calculated, local)

    def test_invalid_prices_dates_and_weights_are_rejected(self):
        bad = [
            ({"ASSET": True}, self.dates, self.prices, None),
            ({"ASSET": 0.9}, self.dates, self.prices, None),
            (self.weights, list(reversed(self.dates)), self.prices, None),
            (self.weights, self.dates, {"ASSET": [100, 110, 88, 110, 0]}, None),
            (self.weights, self.dates, {"ASSET": [100, 110, 88, 110, float("nan")]}, None),
            (self.weights, self.dates, {"ASSET": [5e-324, 100, 88, 110, 1e308]}, None),
            (self.weights, self.dates, {"ASSET": [100, 110, 88, 110]}, None),
            (self.weights, self.dates, self.prices, {"OTHER": [100, 110, 88, 110, 100]}),
        ]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                evaluate(*args)

    def test_stress_percentiles_match_interval_length_and_use_half_ties(self):
        prices = {"ASSET": [100, 110, 88, 96.8, 95]}
        args = (self.weights, self.dates, prices, self.dates[1], self.dates[3])
        claimed = stress_percentile(*args)
        checked = verify_stress_percentile(*args, claimed)
        self.assertEqual(checked["matched_observation_intervals"], 2)
        self.assertEqual(checked["observation_count"], 3)
        self.assertAlmostEqual(checked["terminal_return"]["value"], -0.12)
        self.assertAlmostEqual(checked["terminal_return"]["percentile"], 1 / 3)
        self.assertAlmostEqual(checked["max_drawdown"]["value"], 0.2)
        self.assertAlmostEqual(checked["max_drawdown"]["percentile"], 2 / 3)
        claimed["max_drawdown"]["percentile"] = 0.25
        with self.assertRaisesRegex(ValueError, r"max_drawdown\.percentile"):
            verify_stress_percentile(*args, claimed)

    def test_stress_percentile_with_one_window_and_missing_endpoints(self):
        args = (self.weights, self.dates, self.prices)
        claimed = stress_percentile(*args, self.dates[0], self.dates[-1])
        self.assertEqual(claimed["observation_count"], 1)
        self.assertEqual(claimed["terminal_return"]["percentile"], 0.5)
        self.assertEqual(claimed["max_drawdown"]["percentile"], 0.5)
        with self.assertRaisesRegex(ValueError, "present in the aligned observation dates"):
            stress_percentile(*args, self.dates[0], "2024-01-04")
        with self.assertRaisesRegex(ValueError, "at least one price change"):
            stress_percentile(*args, self.dates[0], self.dates[0])

    def test_named_stress_uses_same_initial_allocation_as_its_direct_replay(self):
        weights = {"ALPHA": .5, "BETA": .5}
        prices = {"ALPHA": [100, 200, 100, 80, 120], "BETA": [100, 100, 120, 140, 130]}
        args = (weights, self.dates, prices, self.dates[1], self.dates[3])
        ranks = verify_stress_percentile(*args, stress_percentile(*args))
        direct = self.checked(weights, self.dates[1:4], {key: values[1:4] for key, values in prices.items()})
        self.assertAlmostEqual(direct["terminal_return"], -.1)
        self.assertAlmostEqual(ranks["terminal_return"]["value"], direct["terminal_return"])
        self.assertAlmostEqual(ranks["max_drawdown"]["value"], direct["max_drawdown"])
        # Starting the whole path once would overweight ALPHA in the later
        # interval and report a 26.67% loss rather than the requested 10%.
        self.assertNotAlmostEqual(ranks["terminal_return"]["value"], 2.2 / 3 - 1)

    def test_seeded_unseen_allocations_preserve_attribution_and_scaling(self):
        random = Random(20261115)
        dates = [(date(2021, 1, 1) + timedelta(days=day)).isoformat() for day in range(1100)]
        for run in range(8):
            symbols = [f"R{run}S{index}" for index in range(1 + run % 4)]
            parts = [random.randint(1, 20) for _ in symbols]
            weights = {symbol: value / sum(parts) for symbol, value in zip(symbols, parts)}
            prices = {}
            for symbol in symbols:
                path = [random.uniform(20, 300)]
                for _ in dates[1:]:
                    path.append(path[-1] * random.uniform(.96, 1.045))
                prices[symbol] = path
            result = self.checked(weights, dates, prices, prices)
            scaled = self.checked(weights, dates, {key: [x * 7 for x in row] for key, row in prices.items()})
            with self.subTest(run=run):
                self.assertAlmostEqual(sum(result["attribution"].values()), result["terminal_return"])
                self.assertAlmostEqual(sum(result["drawdown_attribution"].values()), result["max_drawdown"])
                self.assertAlmostEqual(result["fx_decomposition"]["fx_impact"], 0)
                for metric in ("terminal_return", "terminal_loss", "max_drawdown", "annualized_volatility"):
                    self.assertAlmostEqual(result[metric], scaled[metric])
                self.assertEqual(result["recovery_days"], scaled["recovery_days"])

    def test_chart_path_is_independently_verified_at_every_observation(self):
        claimed = evaluate(self.weights, self.dates, self.prices)
        checked = verify(self.weights, self.dates, self.prices, claimed)
        self.assertEqual([row["date"] for row in checked["observed_path"]], self.dates)
        self.assertEqual(checked["observed_path"][0], {"date": self.dates[0], "value": 1., "drawdown": 0.})
        self.assertAlmostEqual(checked["observed_path"][2]["value"], .88)
        self.assertAlmostEqual(checked["observed_path"][2]["drawdown"], .2)
        for field, value in (("value", .99), ("drawdown", .01), ("date", "2024-01-04")):
            with self.subTest(field=field):
                altered = deepcopy(claimed)
                altered["observed_path"][2][field] = value
                with self.assertRaisesRegex(ValueError, r"observed_path\[2\]"):
                    verify(self.weights, self.dates, self.prices, altered)
        claimed["observed_path"].pop(2)
        with self.assertRaisesRegex(ValueError, "observed_path"):
            verify(self.weights, self.dates, self.prices, claimed)
