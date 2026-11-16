"""Certified funding searches over long-only, buy-and-hold CAD portfolios."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction


_ZERO = Fraction(0)
_ONE = Fraction(1)
_METHOD = "exact_rational_lp_v1"
_MAX_CUT_ROUNDS = 512
_MAX_PIVOTS = 10000
_RISK_METRICS = {"terminal_loss", "max_drawdown", "worst_rolling_12m"}


class _Unassessed(ValueError):
    """The inputs or search budget cannot support a certified result."""


@dataclass(frozen=True)
class _Row:
    coefficients: tuple[Fraction, ...]
    bound: Fraction


@dataclass(frozen=True)
class _Window:
    dates: tuple
    prices: dict
    values: tuple[Fraction, ...]
    changes: tuple[tuple[Fraction, ...], ...]


@dataclass(frozen=True)
class _Risk:
    index: int
    window: str
    metric: str
    cap: Fraction
    periods: tuple[tuple[int, int], ...]


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, Fraction)):
        raise _Unassessed(f"{label} must be a finite number.")
    try:
        return Fraction(str(value))
    except ValueError as exc:
        raise _Unassessed(f"{label} must be a finite number.") from exc


def _fraction(value, label):
    value = _number(value, label)
    if not 0 <= value <= 1:
        raise _Unassessed(f"{label} must be a fraction from 0 to 1.")
    return value


def _symbols(symbols, label):
    if not isinstance(symbols, (list, tuple, set, frozenset)) or any(
        not isinstance(symbol, str) or not symbol.strip() for symbol in symbols
    ):
        raise _Unassessed(f"{label} must contain ticker symbols.")
    if isinstance(symbols, (set, frozenset)):
        symbols = sorted(symbols)
    return tuple(dict.fromkeys(symbols))


def _dot(row, point):
    return sum((a * x for a, x in zip(row, point) if a and x), _ZERO)


def _rolling_periods(dates):
    try:
        days = tuple(date.fromisoformat(day) if isinstance(day, str) else day for day in dates)
        if any(type(day) is not date for day in days):
            raise ValueError
    except ValueError as exc:
        raise _Unassessed("Rolling 12-month loss requires ISO observation dates.") from exc
    periods = []
    for end, day in enumerate(days):
        if day.year == 1:
            continue
        try:
            anniversary = day.replace(year=day.year - 1)
        except ValueError:  # A leap day rolls to the last day of February.
            anniversary = day.replace(year=day.year - 1, day=28)
        if anniversary >= days[0]:
            periods.append((bisect_right(days, anniversary, hi=end) - 1, end))
    if not periods:
        raise _Unassessed("Rolling 12-month loss requires a complete 12-month period.")
    return tuple(periods)


def _prepare_window(window, label, weights, sources, target):
    if not isinstance(window, Mapping) or not isinstance(window.get("dates"), (tuple, list)):
        raise _Unassessed(f"{label} is missing aligned observation dates.")
    dates = tuple(window["dates"])
    if (len(dates) < 2 or type(dates[0]) not in (str, int, date)
            or any(type(day) is not type(dates[0]) for day in dates)
            or any(first >= second for first, second in zip(dates, dates[1:]))):
        raise _Unassessed(f"{label} requires at least two increasing observation dates.")
    data = window.get("cad_prices")
    if not isinstance(data, Mapping):
        raise _Unassessed(f"{label} is missing aligned CAD prices.")
    prices = {}
    needed = dict.fromkeys((*sources, target, *(symbol for symbol, weight in weights.items() if weight)))
    for symbol in needed:
        series = data.get(symbol)
        if not isinstance(series, (list, tuple)) or len(series) != len(dates):
            raise _Unassessed(f"{label} is missing aligned CAD prices for {symbol}.")
        values = tuple(_number(value, f"{label} {symbol} price") for value in series)
        if min(values) <= 0:
            raise _Unassessed(f"{label} contains nonpositive CAD prices for {symbol}.")
        prices[symbol] = tuple(value / values[0] for value in values)
    values = tuple(
        sum((weights.get(symbol, _ZERO) * series[i] for symbol, series in prices.items()), _ZERO)
        for i in range(len(dates))
    )
    changes = tuple(tuple(prices[target][i] - prices[source][i] for source in sources)
                    for i in range(len(dates)))
    return _Window(dates, prices, values, changes)


class _Problem:
    def __init__(self, baseline, target, requested, sources, windows, constraints, risk_limits, retain):
        if not isinstance(baseline, Mapping):
            raise _Unassessed("Starting portfolio weights are required.")
        self.weights = {symbol: _fraction(weight, f"{symbol} weight") for symbol, weight in baseline.items()}
        _symbols(tuple(self.weights), "Starting portfolio")
        if sum(self.weights.values()) != 1:
            raise _Unassessed("Starting portfolio weights must add to 100%.")
        _symbols((target,), "Purchase")
        self.target = target
        self.requested = _fraction(requested, "Requested allocation")
        self.sources = _symbols(sources, "Funding sources")
        if target in self.sources:
            raise _Unassessed("A purchase ticker cannot also be a funding source.")
        if any(symbol not in self.weights for symbol in self.sources):
            raise _Unassessed("Every funding source requires a starting weight.")
        retention = set(_symbols(retain, "Holdings to prefer retaining"))
        if retention.difference(self.weights):
            raise _Unassessed("Every holding to prefer retaining requires a starting weight.")
        self.total = (_ONE,) * len(self.sources)
        self.selection = tuple(-_ONE if symbol in retention else _ZERO for symbol in self.sources)
        self.base_rows = {("request", "cap"): _Row(self.total, self.requested)}
        for i, source in enumerate(self.sources):
            self.base_rows["source", source, "available"] = _Row(self.unit(i), self.weights[source])
        self.allocation_bounds = []
        self._allocation_rows(constraints)
        self.windows = {}
        self.risks = {}
        self._risk_rows(windows, risk_limits)

    def unit(self, i):
        return tuple(_ONE if index == i else _ZERO for index in range(len(self.sources)))

    def _allocation_rows(self, constraints):
        if not isinstance(constraints, (list, tuple)):
            raise _Unassessed("Portfolio constraints must be a list of holding-weight bounds.")
        for index, constraint in enumerate(constraints):
            if not isinstance(constraint, Mapping):
                raise _Unassessed(f"Portfolio constraint {index + 1} has an unsupported form.")
            asset_set = constraint.get("asset_set")
            if not isinstance(asset_set, Mapping) or set(asset_set) != {"symbols"} or not asset_set["symbols"]:
                raise _Unassessed(f"Portfolio constraint {index + 1} requires resolved ticker symbols.")
            symbols = _symbols(asset_set["symbols"], "Holding-weight bound")
            unknown = set(symbols).difference((*self.weights, self.target))
            if unknown:
                raise _Unassessed(f"Portfolio constraint {index + 1} has unknown holdings: {', '.join(sorted(unknown))}.")
            initial = sum((self.weights.get(symbol, _ZERO) for symbol in symbols), _ZERO)
            funded = int(self.target in symbols)
            slopes = tuple(Fraction(funded - int(source in symbols)) for source in self.sources)
            minimum = constraint.get("min")
            maximum = constraint.get("max")
            if minimum is None and maximum is None:
                raise _Unassessed(f"Portfolio constraint {index + 1} has no supported weight bound.")
            if minimum is not None:
                minimum = _fraction(minimum, "Minimum holding weight")
                self.base_rows["allocation", index, "min"] = _Row(tuple(-v for v in slopes), initial - minimum)
            if maximum is not None:
                maximum = _fraction(maximum, "Maximum holding weight")
                self.base_rows["allocation", index, "max"] = _Row(slopes, maximum - initial)
            self.allocation_bounds.append((symbols, minimum, maximum))

    def _risk_rows(self, windows, risk_limits):
        if not isinstance(risk_limits, (list, tuple)):
            raise _Unassessed("Historical risk limits must be a list.")
        for index, limit in enumerate(risk_limits):
            metric = limit.get("metric") if isinstance(limit, Mapping) else None
            if not isinstance(metric, str) or metric not in _RISK_METRICS:
                raise _Unassessed(f"Funding search cannot certify the requested historical risk metric {metric!r}.")
            cap = _fraction(limit.get("cap"), f"{metric} cap")
            if not isinstance(windows, Mapping) or not windows:
                raise _Unassessed(f"Aligned market observations are required for {metric}.")
            selection = limit.get("windows", "default")
            if selection in ("default", "all"):
                selection = tuple(windows)
            selection = _symbols(selection, "Historical risk window selection")
            if not selection:
                raise _Unassessed(f"At least one historical risk window is required for {metric}.")
            for name in selection:
                if name not in windows:
                    raise _Unassessed(f"Historical risk window {name} is unavailable.")
                if name not in self.windows:
                    self.windows[name] = _prepare_window(windows[name], name, self.weights, self.sources, self.target)
                window = self.windows[name]
                periods = ()
                if metric == "terminal_loss":
                    periods = ((0, len(window.dates) - 1),)
                elif metric == "worst_rolling_12m":
                    periods = _rolling_periods(window.dates)
                risk = _Risk(index, name, metric, cap, periods)
                self.risks[index, name] = risk
                if metric == "terminal_loss":
                    start, end = periods[0]
                    key = ("risk", index, name, start, end)
                    self.base_rows[key] = self.row(key)

    def row(self, key, size=None):
        if key in self.base_rows:
            return self.base_rows[key]
        if size is not None and key == ("size", "max"):
            return _Row(self.total, size)
        if size is not None and key == ("size", "min"):
            return _Row(tuple(-c for c in self.total), -size)
        if len(key) != 5 or key[0] != "risk":
            raise ValueError("Unknown certificate row.")
        _, index, name, start, end = key
        risk = self.risks.get((index, name))
        window = self.windows.get(name)
        if (not risk or not window or type(start) is not int or type(end) is not int
                or not 0 <= start < end < len(window.dates)
                or risk.metric != "max_drawdown" and (start, end) not in risk.periods):
            raise ValueError("Unknown observation pair in certificate.")
        remaining = 1 - risk.cap
        return _Row(
            tuple(remaining * peak - low for peak, low in zip(window.changes[start], window.changes[end])),
            window.values[end] - remaining * window.values[start],
        )

    def risk_cuts(self, point):
        paths = {}
        for risk in self.risks.values():
            if risk.metric == "terminal_loss":
                continue
            window = self.windows[risk.window]
            if risk.window not in paths:
                paths[risk.window] = tuple(value + _dot(slope, point) for value, slope
                                           in zip(window.values, window.changes))
            observed, start, end = _check_risk(risk, paths[risk.window])
            if observed > risk.cap:
                yield ("risk", risk.index, risk.window, start, end)

    def candidate_weights(self, point):
        weights = self.weights.copy()
        for symbol, amount in zip(self.sources, point):
            weights[symbol] -= amount
        weights[self.target] = weights.get(self.target, _ZERO) + sum(point)
        return weights

    def replay(self, point):
        """Check every requested period directly from candidate weights and original CAD prices."""
        weights = self.candidate_weights(point)
        checks = []
        paths = {}
        for risk in self.risks.values():
            window = self.windows[risk.window]
            if risk.window not in paths:
                paths[risk.window] = tuple(
                    sum((weights[symbol] * series[i] for symbol, series in window.prices.items()), _ZERO)
                    for i in range(len(window.dates))
                )
            values = paths[risk.window]
            observed, start, end = _check_risk(risk, values)
            checks.append({
                "metric": risk.metric, "window": risk.window,
                "cap": float(risk.cap), "value": float(observed),
                "start": str(window.dates[start]), "end": str(window.dates[end]),
                "passed": _meets_risk_bound(risk, values),
            })
        return checks

    def certificate_reasons(self, proof):
        reasons = []
        for term in proof["dual"]:
            family, *key = term["row"]
            if family == "source":
                reasons.append(f"The holdings available to sell from {key[0]} contribute to this bound.")
            elif family == "allocation":
                symbols, _, _ = self.allocation_bounds[key[0]]
                bound = "minimum" if key[1] == "min" else "maximum"
                reasons.append(f"The {bound} weight for {', '.join(symbols)} contributes to this bound.")
            elif family == "risk":
                index, name, start, end = key
                metric = self.risks[index, name].metric.replace("_", " ")
                dates = self.windows[name].dates
                reasons.append(f"The {metric} cap in {name} contributes to this bound from {dates[start]} to {dates[end]}.")
        return list(dict.fromkeys(reasons))


def _max_drawdown(values):
    worst, peak, start, end = _ZERO, 0, 0, 0
    for i, value in enumerate(values[1:], 1):
        if value > values[peak]:
            peak = i
        else:
            drawdown = 1 - value / values[peak]
            if drawdown > worst:
                worst, start, end = drawdown, peak, i
    return worst, start, end


def _check_risk(risk, values):
    if risk.metric == "max_drawdown":
        return _max_drawdown(values)
    periods = ((max(_ZERO, 1 - values[last] / values[first]), first, last) for first, last in risk.periods)
    return max(periods, key=lambda row: row[0])


def _meets_risk_bound(risk, values):
    remaining = 1 - risk.cap
    if risk.metric != "max_drawdown":
        return all(values[end] >= remaining * values[start] for start, end in risk.periods)
    peak = values[0]
    for value in values[1:]:
        if value < remaining * peak:
            return False
        peak = max(peak, value)
    return True


class _Simplex:
    """Two-phase primal simplex for Ax <= b and x >= 0, using exact arithmetic."""

    def __init__(self, rows, objective):
        self.m, self.n = len(rows), len(objective)
        self.basic = list(range(self.n, self.n + self.m))
        self.nonbasic = [*range(self.n), -1]
        self.table = [[*row.coefficients, -_ONE, row.bound] for row in rows]
        self.table.extend([[-c for c in objective] + [_ZERO, _ZERO], [_ZERO] * self.n + [_ONE, _ZERO]])
        self.pivots = 0

    def _pivot(self, row, column):
        self.pivots += 1
        if self.pivots > _MAX_PIVOTS:
            raise _Unassessed("The simplex pivot budget was exhausted before certification.")
        table = self.table
        pivot = table[row][column]
        for i, values in enumerate(table):
            if i == row or not values[column]:
                continue
            rate = values[column] / pivot
            for j in range(self.n + 2):
                if j != column and table[row][j]:
                    values[j] -= table[row][j] * rate
            values[column] = -rate
        table[row] = [value / pivot if j != column else 1 / pivot for j, value in enumerate(table[row])]
        self.basic[row], self.nonbasic[column] = self.nonbasic[column], self.basic[row]

    def _maximize(self, phase):
        goal = self.m + (phase == 1)
        while True:
            # Bland's index ordering avoids cycling on degenerate portfolios.
            entering = [
                j for j, variable in enumerate(self.nonbasic)
                if (phase == 1 or variable != -1) and self.table[goal][j] < 0
            ]
            if not entering:
                return
            column = min(entering, key=self.nonbasic.__getitem__)
            choices = [i for i in range(self.m) if self.table[i][column] > 0]
            if not choices:
                raise _Unassessed("The funding objective has no certified finite bound.")
            row = min(choices, key=lambda i: (self.table[i][-1] / self.table[i][column], self.basic[i]))
            self._pivot(row, column)

    def _dual(self, objective_row):
        multipliers = [_ZERO] * self.m
        for column, variable in enumerate(self.nonbasic):
            if variable >= self.n:
                multipliers[variable - self.n] = self.table[objective_row][column]
        return multipliers

    def solve(self):
        row = min(range(self.m), key=lambda i: self.table[i][-1])
        if self.table[row][-1] < 0:
            self._pivot(row, self.n)
            self._maximize(1)
            if self.table[self.m + 1][-1] < 0:
                return None, self._dual(self.m + 1)
            if -1 in self.basic:
                row = self.basic.index(-1)
                choices = [j for j in range(self.n + 1) if self.table[row][j]]
                if choices:
                    self._pivot(row, min(choices, key=self.nonbasic.__getitem__))
        self._maximize(2)
        point = [_ZERO] * self.n
        for i, variable in enumerate(self.basic):
            if 0 <= variable < self.n:
                point[variable] = self.table[i][-1]
        return tuple(point), self._dual(self.m)


def _serialized(point, rows, multipliers):
    result = {
        "kind": "infeasible" if point is None else "optimal",
        "dual": [{"row": list(key), "multiplier": str(value)}
                 for key, value in zip(rows, multipliers) if value],
    }
    if point is not None:
        result["point"] = [str(amount) for amount in point]
    return result


def _optimize(problem, cuts, objective, size=None):
    for _ in range(_MAX_CUT_ROUNDS):
        rows = {**problem.base_rows, **cuts}
        if size is not None:
            for key in (("size", "max"), ("size", "min")):
                rows[key] = problem.row(key, size)
        point, multipliers = _Simplex(tuple(rows.values()), objective).solve()
        if point is None:
            return point, _serialized(point, rows, multipliers)
        additions = tuple(problem.risk_cuts(point))
        if not additions:
            return point, _serialized(point, rows, multipliers)
        for key in additions:
            cuts[key] = problem.row(key)
    raise _Unassessed("The historical risk cut budget was exhausted before certification.")


def _plain_result(problem, status, certificate=None, maximum=None, point=None, bounds=None):
    if status == "infeasible":
        reasons = [
            "No positive purchase satisfies all supplied funding rules." if maximum == 0 else
            "The supplied funding rules have no feasible allocation within the authorized search."
        ]
    elif status == "smaller_feasible":
        reasons = ["The supplied funding rules limit the purchase to a smaller amount."]
    else:
        reasons = []
    if reasons:
        reasons.extend(problem.certificate_reasons(certificate["maximum"] or certificate["selection"]))
    return {
        "status": status,
        "requested": float(problem.requested),
        "funded": float(sum(point)) if point is not None else 0.0 if maximum == 0 else None,
        "maximum_fundable": float(maximum) if maximum is not None else None,
        "source_amounts": dict(zip(problem.sources, map(float, point))) if point is not None else {},
        "source_bounds": bounds or {},
        "weights": {symbol: float(weight) for symbol, weight in problem.candidate_weights(point).items()}
                   if point is not None else {},
        "risk_checks": problem.replay(point) if point is not None else [],
        "certificate": certificate,
        "reasons": reasons,
    }


def _unassessed(reason):
    return {
        "status": "unassessed", "requested": None, "funded": None, "maximum_fundable": None,
        "source_amounts": {}, "source_bounds": {}, "weights": {}, "risk_checks": [],
        "certificate": None, "reasons": [reason],
    }


def search_funding(baseline, target, requested, sources, windows, constraints, risk_limits, *,
                   allow_smaller=False, retain=()) -> dict:
    """Find exact-size funding or, when authorized, the largest feasible smaller purchase.

    All amounts are shares of initial portfolio value. Bounds on each source are
    marginal bounds at the funded size. Retention breaks ties by minimizing the
    aggregate amount sold from the named holdings. An unsupported rule, missing
    evidence, or exhausted search returns an unassessed result.
    """
    try:
        if type(allow_smaller) is not bool:
            raise _Unassessed("Permission to search smaller amounts must be explicit.")
        problem = _Problem(baseline, target, requested, sources, windows, constraints, risk_limits, retain)
        return _search(problem, allow_smaller)
    except _Unassessed as exc:
        return _unassessed(str(exc))


def _search(problem, allow_smaller):
    cuts = {}
    certificate = {"method": _METHOD, "maximum": None, "selection": None, "source_bounds": {}}
    maximum = None
    size = problem.requested
    if allow_smaller:
        largest, certificate["maximum"] = _optimize(problem, cuts, problem.total)
        if largest is None:
            return _plain_result(problem, "infeasible", certificate)
        maximum = size = sum(largest, _ZERO)
        if size == 0 < problem.requested:
            return _plain_result(problem, "infeasible", certificate, maximum)
    point, certificate["selection"] = _optimize(problem, cuts, problem.selection, size)
    if point is None:
        if allow_smaller:
            raise _Unassessed("The chosen size could not be certified by the funding search.")
        return _plain_result(problem, "infeasible", certificate)
    bounds = {}
    for i, symbol in enumerate(problem.sources):
        direction = problem.unit(i)
        lower, lower_proof = _optimize(problem, cuts, tuple(-c for c in direction), size)
        upper, upper_proof = _optimize(problem, cuts, direction, size)
        if lower is None or upper is None:
            raise _Unassessed(f"The feasible amounts for {symbol} could not be certified.")
        bounds[symbol] = {"min": float(lower[i]), "max": float(upper[i])}
        certificate["source_bounds"][symbol] = {"min": lower_proof, "max": upper_proof}
    status = "feasible" if size == problem.requested else "smaller_feasible"
    return _plain_result(problem, status, certificate, maximum, point, bounds)


def _read_rational(value):
    if type(value) is not str:
        raise ValueError("The certificate must encode exact rational numbers.")
    return Fraction(value)


def _verify_proof(problem, proof, objective, size=None):
    if not isinstance(proof, Mapping) or proof.get("kind") not in ("optimal", "infeasible"):
        raise ValueError("A funding proof is missing or malformed.")
    dual = proof.get("dual")
    if not isinstance(dual, list):
        raise ValueError("The funding proof is missing its dual multipliers.")
    infeasible = proof["kind"] == "infeasible"
    seen = set()
    dual_vector = [_ZERO] * len(problem.sources)
    dual_value = _ZERO
    for term in dual:
        key = tuple(term["row"])
        multiplier = _read_rational(term["multiplier"])
        if key in seen or multiplier <= 0:
            raise ValueError("Dual multipliers require distinct rows and positive coefficients.")
        seen.add(key)
        row = problem.row(key, size)
        dual_value += multiplier * row.bound
        for i, coefficient in enumerate(row.coefficients):
            dual_vector[i] += multiplier * coefficient
    if infeasible:
        if any(coefficient < 0 for coefficient in dual_vector) or dual_value >= 0 or "point" in proof:
            raise ValueError("The multipliers do not prove that the funding rules are infeasible.")
        return None
    if any(a < b for a, b in zip(dual_vector, objective)):
        raise ValueError("The dual multipliers do not bound the funding objective.")
    amounts = proof.get("point")
    if not isinstance(amounts, list) or len(amounts) != len(problem.sources):
        raise ValueError("The funding proof is missing the proposed source amounts.")
    point = tuple(_read_rational(amount) for amount in amounts)
    if not _verify_point(problem, point, size):
        raise ValueError("The proved funding point fails independent replay or portfolio constraints.")
    if _dot(objective, point) != dual_value:
        raise ValueError("The proposed funding point does not meet the certified objective bound.")
    return point


def _verify_point(problem, point, size):
    if any(amount < 0 for amount in point):
        return False
    total = sum(point, _ZERO)
    if total > problem.requested or (size is not None and total != size):
        return False
    weights = problem.candidate_weights(point)
    if sum(weights.values()) != 1 or any(weight < 0 for weight in weights.values()):
        return False
    for symbols, minimum, maximum in problem.allocation_bounds:
        weight = sum((weights.get(symbol, _ZERO) for symbol in symbols), _ZERO)
        if (minimum is not None and weight < minimum) or (maximum is not None and weight > maximum):
            return False
    return all(check["passed"] for check in problem.replay(point))


def _verified_result(problem, certificate, allow_smaller):
    if not isinstance(certificate, Mapping) or certificate.get("method") != _METHOD:
        raise ValueError("The funding certificate has an unsupported method.")
    reported_bounds = certificate.get("source_bounds")
    if not isinstance(reported_bounds, Mapping):
        raise ValueError("The funding certificate is missing its source-bound proofs.")
    maximum_proof = certificate.get("maximum")
    selection_proof = certificate.get("selection")
    maximum = None
    size = problem.requested
    if allow_smaller:
        largest = _verify_proof(problem, maximum_proof, problem.total)
        maximum = size = sum(largest, _ZERO) if largest is not None else None
        if largest is None or size == 0 < problem.requested:
            if reported_bounds or selection_proof is not None:
                raise ValueError("The certificate claims a selection despite proving no feasible purchase.")
            return _plain_result(problem, "infeasible", certificate, maximum)
    elif maximum_proof is not None:
        raise ValueError("The certificate includes a search beyond the authorized purchase size.")
    point = _verify_proof(problem, selection_proof, problem.selection, size)
    if point is None:
        if allow_smaller or reported_bounds:
            raise ValueError("The infeasibility proof contradicts the other funding claims.")
        return _plain_result(problem, "infeasible", certificate)
    if set(reported_bounds) != set(problem.sources):
        raise ValueError("The certificate does not prove the bounds of every approved funding source.")
    bounds = {}
    for i, symbol in enumerate(problem.sources):
        direction = problem.unit(i)
        lower = _verify_proof(problem, reported_bounds[symbol]["min"], tuple(-c for c in direction), size)
        upper = _verify_proof(problem, reported_bounds[symbol]["max"], direction, size)
        if lower is None or upper is None or not lower[i] <= point[i] <= upper[i]:
            raise ValueError(f"The source-bound proofs for {symbol} contradict the chosen funding.")
        bounds[symbol] = {"min": float(lower[i]), "max": float(upper[i])}
    status = "feasible" if size == problem.requested else "smaller_feasible"
    return _plain_result(problem, status, certificate, maximum, point, bounds)


def verify_funding(baseline, target, requested, sources, windows, constraints, risk_limits, *,
                   claimed, allow_smaller=False, retain=()) -> dict:
    """Independently replay a funding result and check its optimality or infeasibility proof."""
    try:
        if type(allow_smaller) is not bool:
            raise _Unassessed("Permission to search smaller amounts must be explicit.")
        problem = _Problem(baseline, target, requested, sources, windows, constraints, risk_limits, retain)
        if not isinstance(claimed, Mapping):
            raise ValueError("The funding claim is missing.")
        if claimed.get("status") == "unassessed" and claimed.get("certificate") is None:
            return {"status": "unassessed", "reasons": ["No certified funding finding was supplied."]}
        expected = _verified_result(problem, claimed.get("certificate"), allow_smaller)
        if any(field not in claimed or claimed[field] != value for field, value in expected.items()):
            raise ValueError("The reported funding differs from the independently verified result.")
    except _Unassessed as exc:
        return {"status": "unassessed", "reasons": [str(exc)]}
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return {"status": "invalid", "reasons": [str(exc)]}
    return {"status": "verified", "reasons": []}
