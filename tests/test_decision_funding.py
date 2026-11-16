import copy
import unittest
from fractions import Fraction
from random import Random
from unittest.mock import patch

from datathon.decision_funding import search_funding, verify_funding


def market(prices, dates=None):
    if dates is None:
        dates = ["2021-01-04", "2021-06-04", "2022-01-04"]
    return {"sample": {"dates": dates, "cad_prices": prices}}


class DecisionFundingTests(unittest.TestCase):
    def checked(self, args, **policy):
        result = search_funding(*args, **policy)
        self.assertEqual(verify_funding(*args, **policy, claimed=result), {"status": "verified", "reasons": []})
        return result

    def test_three_sources_have_independent_bounds_and_a_checked_retention_preference(self):
        starting = {"AAA": .4, "BBB": .35, "CCC": .15, "NEW": .1}
        constraints = [
            {"asset_set": {"symbols": ["AAA", "BBB"]}, "min": .55},
            {"asset_set": {"symbols": ["BBB"]}, "min": .25},
        ]
        args = (starting, "NEW", .3, ["AAA", "BBB", "CCC"], {}, constraints, [])
        result = self.checked(args, retain=("AAA",))
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["source_amounts"], {"AAA": .05, "BBB": .1, "CCC": .15})
        self.assertEqual(result["weights"], {"AAA": .35, "BBB": .25, "CCC": 0.0, "NEW": .4})
        self.assertEqual(result["source_bounds"], {"AAA": {"min": .05, "max": .2},
                                                  "BBB": {"min": 0.0, "max": .1},
                                                  "CCC": {"min": .1, "max": .15}})

    def test_terminal_limit_proves_infeasibility_or_maximum_only_with_permission(self):
        windows = market({"A": [100, 100, 100], "B": [50, 50, 50], "T": [100, 90, 50]})
        risk = [{"metric": "terminal_loss", "cap": .0725, "windows": "all"}]
        args = ({"A": .5, "B": .5}, "T", .25, ["A", "B"], windows, [], risk)
        unavailable = self.checked(args)
        self.assertEqual(unavailable["status"], "infeasible")
        self.assertIsNone(unavailable["certificate"]["maximum"])
        self.assertEqual(unavailable["certificate"]["selection"]["kind"], "infeasible")
        largest = self.checked(args, allow_smaller=True)
        self.assertEqual(largest["status"], "smaller_feasible")
        self.assertEqual(largest["funded"], .145)
        self.assertEqual(largest["maximum_fundable"], .145)
        self.assertEqual(largest["risk_checks"][0]["value"], .0725)

        changed = copy.deepcopy(unavailable)
        changed["certificate"]["selection"]["dual"][0]["multiplier"] = "-1"
        self.assertEqual(verify_funding(*args, claimed=changed)["status"], "invalid")
        self.assertEqual(verify_funding(*args, claimed=largest)["status"], "invalid")

    def test_drawdown_checks_every_peak_to_trough_pair_before_certification(self):
        dates = ["2021-01-04", "2021-03-01", "2021-05-03", "2021-08-02", "2022-01-04"]
        windows = market({"A": [100, 100, 100, 100, 100], "T": [100, 200, 90, 150, 120]}, dates)
        risk = [{"metric": "max_drawdown", "cap": .2, "windows": ["sample"]},
                {"metric": "terminal_loss", "cap": 0, "windows": ["sample"]}]
        args = ({"A": 1}, "T", .4, ["A"], windows, [], risk)
        result = self.checked(args, allow_smaller=True)
        self.assertEqual(result["maximum_fundable"], 2 / 9)
        self.assertEqual(result["certificate"]["maximum"]["point"], ["2/9"])
        self.assertEqual(result["risk_checks"][0]["start"], dates[1])
        self.assertEqual(result["risk_checks"][0]["end"], dates[2])
        self.assertEqual(result["risk_checks"][1]["value"], 0)

        altered_windows = copy.deepcopy(windows)
        altered_windows["sample"]["cad_prices"]["T"][3] = 50
        new_args = (*args[:4], altered_windows, *args[5:])
        self.assertEqual(verify_funding(*new_args, allow_smaller=True, claimed=result)["status"], "invalid")

        with patch("datathon.decision_funding._MAX_CUT_ROUNDS", 1):
            exhausted = search_funding(*args, allow_smaller=True)
        self.assertEqual(exhausted["status"], "unassessed")
        self.assertIn("budget was exhausted", exhausted["reasons"][0])
        self.assertIsNone(exhausted["certificate"])

    def test_rolling_loss_uses_last_observation_on_or_before_calendar_lookback(self):
        dates = ["2020-01-02", "2020-01-03", "2020-12-31", "2021-01-04", "2021-01-05"]
        windows = market({"A": [100, 100, 100, 100, 100], "T": [100, 200, 200, 100, 120]}, dates)
        risk = [{"metric": "worst_rolling_12m", "cap": .091}]
        args = ({"A": 1}, "T", .1, ["A"], windows, [], risk)
        result = self.checked(args)
        check = result["risk_checks"][0]
        self.assertEqual(check["value"], 1 / 11)
        self.assertEqual((check["start"], check["end"]), (dates[1], dates[3]))

    def test_unsupported_rules_and_missing_data_are_never_relaxed(self):
        baseline = {"A": 1}
        windows = market({"A": [100, 100, 100], "T": [100, 80, 100]})
        args = (baseline, "T", .1, ["A"], windows)
        cases = [
            ([], [{"metric": "recovery_days", "cap": 180}], "recovery_days"),
            ([], [{"metric": "max_drawdown", "cap": .2, "windows": ["absent"]}], "unavailable"),
            ([{"asset_set": {"issuer": "Unknown"}, "max": .2}], [], "resolved ticker symbols"),
            ([], [{"metric": "worst_rolling_12m", "cap": .2, "windows": ["sample"]}], "12-month period"),
        ]
        short_windows = market({"A": [100, 100, 100], "T": [100, 80, 100]},
                               ["2021-01-04", "2021-06-04", "2021-12-03"])
        for constraints, risk, message in cases:
            with self.subTest(message=message):
                selected = (*args[:4], short_windows) if message == "12-month period" else args
                result = search_funding(*selected, constraints, risk, allow_smaller=True)
                self.assertEqual(result["status"], "unassessed")
                self.assertIn(message, result["reasons"][0])
                self.assertIsNone(result["certificate"])

    def test_zero_maximum_is_proved_and_no_trade_is_selected(self):
        args = ({"A": 1}, "T", .1, ["A"], {},
                [{"asset_set": {"symbols": ["A"]}, "min": 1}], [])
        result = self.checked(args, allow_smaller=True)
        self.assertEqual(result["status"], "infeasible")
        self.assertEqual(result["maximum_fundable"], 0)
        self.assertEqual(result["source_amounts"], {})

    def test_release_values_and_source_amounts_must_match_proof(self):
        args = ({"A": .4, "B": .6}, "T", .15, ["A", "B"], {}, [], [])
        result = self.checked(args)
        for field in ("funded", "source_amounts", "source_bounds", "weights"):
            with self.subTest(field=field):
                changed = copy.deepcopy(result)
                changed[field] = None
                self.assertEqual(verify_funding(*args, claimed=changed)["status"], "invalid")

    def test_seeded_n_source_search_matches_closed_form_capacity_and_loss_bounds(self):
        random = Random(20261115)
        for run in range(24):
            count = 2 + run % 4
            cuts = [0, *sorted(random.sample(range(1, 100), count - 1)), 100]
            amounts = [right - left for left, right in zip(cuts, cuts[1:])]
            symbols = [f"SOURCE{run}_{index}" for index in range(count)]
            starting = {symbol: amount / 100 for symbol, amount in zip(symbols, amounts)}
            floors = {symbol: random.randint(0, amount) / 100 for symbol, amount in zip(symbols, amounts)}
            requested = random.randint(1, 50) / 100
            cap = random.randint(1, 20) / 100
            prices = {symbol: [100, 100, 100] for symbol in symbols}
            prices["UNSEEN_TARGET"] = [100, 90, 50]
            constraints = [{"asset_set": {"symbols": [symbol]}, "min": floors[symbol]} for symbol in symbols]
            args = (starting, "UNSEEN_TARGET", requested, symbols, market(prices), constraints,
                    [{"metric": "terminal_loss", "cap": cap}])
            with self.subTest(run=run, sources=count):
                result = self.checked(args, allow_smaller=True, retain=symbols[:1])
                capacity = sum(Fraction(str(starting[s])) - Fraction(str(floors[s])) for s in symbols)
                exact = min(Fraction(str(requested)), capacity, 2 * Fraction(str(cap)))
                self.assertEqual(result["maximum_fundable"], float(exact))
                if exact:
                    self.assertAlmostEqual(sum(result["source_amounts"].values()), float(exact))
                    self.assertLessEqual(result["risk_checks"][0]["value"], cap)
                    for source in symbols:
                        self.assertGreaterEqual(result["weights"][source], floors[source])

    def test_infeasibility_certificate_cannot_be_reused_after_constraint_is_relaxed(self):
        args = ({"A": .4, "B": .6}, "NEW", .3, ["A", "B"], {},
                [{"asset_set": {"symbols": ["A", "B"]}, "min": .8}], [])
        proof = self.checked(args)
        self.assertEqual(proof["status"], "infeasible")
        relaxed = (*args[:5], [{"asset_set": {"symbols": ["A", "B"]}, "min": .5}], [])
        self.assertEqual(verify_funding(*relaxed, claimed=proof)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
