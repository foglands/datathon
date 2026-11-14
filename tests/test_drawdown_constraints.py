import math
import random
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from datathon.data import MarketData
from datathon.finance import (
    BASE_WEIGHTS,
    FUNDING_SOURCES,
    TARGET_TICKER,
    StressWindow,
    _Constraint,
    solve_funding,
)


def exhaustive_constraints(prepared, baseline, metric, limit, target):
    """Independent exhaustive reference for the screened funding solver."""
    for window_id, (_, dates, prices) in prepared.items():
        for later in range(1, len(dates)):
            for earlier in range(later):
                drops = {
                    ticker: series[later] - (1 - limit) * series[earlier]
                    for ticker, series in prices.items()
                }
                value = math.fsum(baseline[ticker] * drops[ticker] for ticker in drops)
                a, b = (drops[TARGET_TICKER] - drops[source] for source in FUNDING_SOURCES)
                yield _Constraint(metric, value, a, b, window_id, dates[later], dates[earlier], limit)


class DrawdownConstraintTests(unittest.TestCase):
    def test_screening_preserves_feasibility_boundaries_and_witness(self):
        dates = [(date(2024, 1, 2) + timedelta(days=i)).isoformat() for i in range(20)]
        windows = (StressWindow("toy", "Synthetic replay", dates[0], dates[-1]),)
        statuses = set()
        for seed in range(6):
            rng = random.Random(seed)
            data = MarketData(
                {ticker: {day: rng.uniform(.70, 1.30) for day in dates} for ticker in BASE_WEIGHTS},
                dict.fromkeys(dates, 1.0),
            )
            for target in (0.0, 0.1, 0.22):
                for limit in (0.10, 0.25, 0.40):
                    with self.subTest(seed=seed, target=target, limit=limit):
                        options = dict(windows=windows, target=target, metric="max_drawdown", loss_limit=limit)
                        result = solve_funding(data, **options)
                        with patch("datathon.finance._risk_constraints", exhaustive_constraints):
                            reference = solve_funding(data, **options)
                        self.assertEqual(result["status"], reference["status"])
                        statuses.add(result["status"])
                        for key in ("max_total", "full_zst_min", "full_zst_max"):
                            actual, expected = (item["frontier"][key] for item in (result, reference))
                            if expected is None:
                                self.assertIsNone(actual)
                            else:
                                self.assertAlmostEqual(actual, expected, places=9)
                        if reference["certificate"] is not None:
                            self.assertEqual(result["certificate"]["rule"], reference["certificate"]["rule"])
                            self.assertEqual(result["certificate"]["observation_date"],
                                             reference["certificate"]["observation_date"])
                            self.assertEqual(result["certificate"]["peak_date"], reference["certificate"]["peak_date"])
        self.assertTrue({"no_feasible", "feasible_full", "feasible_partial"}.issubset(statuses))
