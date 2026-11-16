"""Historical buy-and-hold metrics with an independent calculation check."""

from bisect import bisect_left, bisect_right
from calendar import monthrange
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, localcontext
from itertools import accumulate, groupby
from math import fsum, isclose, isfinite, sqrt
from numbers import Real
from statistics import stdev


_ANNUAL_SESSIONS = 252
_ROLLING_MONTHS = (12, 36)
_TIE_TOLERANCE = 1e-12


def _number(value, label, *, positive=False):
    if isinstance(value, (Real, Decimal)) and not isinstance(value, bool):
        try:
            converted = float(value)
        except (OverflowError, ValueError):
            converted = float("nan")
        if isfinite(converted) and converted >= 0 and (not positive or converted > 0):
            return converted
    constraint = "positive" if positive else "nonnegative"
    raise ValueError(f"{label} must be finite and {constraint}.")


def _series(prices, tickers, count, label):
    if not isinstance(prices, Mapping) or not set(tickers) <= prices.keys():
        raise ValueError(f"{label} prices must cover every weighted ticker.")
    result = {}
    for ticker in tickers:
        row = prices[ticker]
        try:
            if isinstance(row, (str, bytes, Mapping)):
                raise TypeError
            values = tuple(_number(value, f"{label} price for {ticker}", positive=True) for value in row)
        except TypeError as exc:
            raise ValueError(f"{label} prices for {ticker} must be an ordered series.") from exc
        if len(values) != count:
            raise ValueError(f"{label} prices for {ticker} must match the observation dates.")
        if not isfinite(max(values) / min(values)):
            raise ValueError(f"{label} price range for {ticker} exceeds numeric limits.")
        result[ticker] = values
    return result


def _inputs(weights, dates, cad_prices, local_prices):
    if not isinstance(weights, Mapping) or not weights or any(
        not isinstance(ticker, str) or not ticker.strip() for ticker in weights
    ):
        raise ValueError("Provide a nonempty mapping of ticker weights.")
    weights = {ticker: _number(value, f"Weight for {ticker}") for ticker, value in weights.items()}
    if any(weight > 1.0 for weight in weights.values()) or not isclose(
        fsum(weights.values()), 1.0, abs_tol=1e-10, rel_tol=0
    ):
        raise ValueError("Portfolio weights must sum to one.")
    try:
        raw_dates = tuple(dates)
        days = tuple(date.fromisoformat(value) for value in raw_dates)
    except (TypeError, ValueError) as exc:
        raise ValueError("Provide observation dates in YYYY-MM-DD format.") from exc
    if len(days) < 2 or any(first >= second for first, second in zip(days, days[1:])):
        raise ValueError("Provide at least two strictly increasing observation dates.")
    if any(value != day.isoformat() for value, day in zip(raw_dates, days)):
        raise ValueError("Provide observation dates in YYYY-MM-DD format.")
    cad = _series(cad_prices, weights, len(days), "CAD")
    local = _series(local_prices, weights, len(days), "Local") if local_prices is not None else None
    return weights, days, cad, local


def _month_number(day):
    return day.year * 12 + day.month - 1


def _anniversary(day, months):
    year, month = divmod(_month_number(day) - months, 12)
    if year < 1:
        return None
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _period(start, end):
    return {
        "start_date": start.isoformat() if start is not None else None,
        "end_date": end.isoformat() if end is not None else None,
    }


def _minimum_period(days, observations, *, key):
    if not observations:
        return {key: None, "observation_count": 0, **_period(None, None)}
    minimum = min(change for change, _, _ in observations)
    change, first, last = next(row for row in observations if row[0] <= minimum + _TIE_TOLERANCE)
    return {
        key: change, "observation_count": len(observations), **_period(days[first], days[last]),
    }


def _rolling(days, values):
    result = {}
    for months in _ROLLING_MONTHS:
        observations = []
        for last, day in enumerate(days):
            previous = _anniversary(day, months)
            if previous is None or previous < days[0]:
                continue
            first = bisect_right(days, previous, hi=last) - 1
            observations.append((values[last] / values[first] - 1.0, first, last))
        result[f"{months}m"] = _minimum_period(days, observations, key="worst_return")
    return result


def _monthly(days, values):
    ends = {}
    for index, day in enumerate(days):
        ends[_month_number(day)] = index
    last_month = _month_number(days[-1])
    if days[-1].day != monthrange(days[-1].year, days[-1].month)[1]:
        ends.pop(last_month)
    observations = [
        (values[last] / values[ends[month - 1]] - 1.0, ends[month - 1], last)
        for month, last in ends.items() if month - 1 in ends
    ]
    result = _minimum_period(days, observations, key="return")
    endpoint = result["end_date"]
    return {"month": endpoint[:7] if endpoint else None, **result}


def _recovery(days, peak, trough, recovered):
    if peak == trough:
        return {
            "recovery_status": "no_drawdown", "recovery_date": None,
            "recovery_days": 0, "days_underwater": 0,
        }
    if recovered is None:
        return {
            "recovery_status": "unrecovered", "recovery_date": None,
            "recovery_days": None, "days_underwater": (days[-1] - days[peak]).days,
        }
    return {
        "recovery_status": "recovered", "recovery_date": days[recovered].isoformat(),
        "recovery_days": (days[recovered] - days[peak]).days,
        "days_underwater": (days[recovered] - days[peak]).days,
    }


def _fx_decomposition(weights, paths, local):
    if local is None:
        return None
    by_ticker = {}
    for ticker, weight in weights.items():
        local_growth = local[ticker][-1] / local[ticker][0]
        cad_growth = paths[ticker][-1]
        fx_growth = _number(cad_growth / local_growth, f"FX movement for {ticker}", positive=True)
        local_return = weight * (local_growth - 1.0)
        fx_return = weight * (fx_growth - 1.0)
        interaction = local_return * (fx_growth - 1.0)
        by_ticker[ticker] = {
            "cad_return": weight * (cad_growth - 1.0),
            "local_return": local_return, "fx_return": fx_return,
            "interaction_return": interaction, "fx_impact": fx_return + interaction,
        }
    return {
        **{key: fsum(row[key] for row in by_ticker.values()) for key in next(iter(by_ticker.values()))},
        "by_ticker": by_ticker,
    }


def _cad_paths(weights, cad):
    paths = {ticker: tuple(value / series[0] for value in series) for ticker, series in cad.items()}
    values = [fsum(weight * paths[ticker][index] for ticker, weight in weights.items())
              for index in range(len(next(iter(paths.values()))))]
    return values, paths


def evaluate(weights, dates, cad_prices, local_prices=None):
    """Value fixed weights in CAD and calculate historical returns and risk.

    Rolling windows use the last available observation on or before the calendar
    anniversary of each eligible end date. Monthly returns use consecutive
    calendar month closes and exclude a trailing partial month. Recovery dates
    refer to the maximum drawdown and durations are calendar days from its
    peak until the previous peak value is recovered. Volatility
    uses sample close-to-close returns annualized over 252 sessions. FX impact
    includes the interaction between local asset performance and exchange rates.
    Equal worst observations select the earliest end date.
    """
    weights, days, cad, local = _inputs(weights, dates, cad_prices, local_prices)
    total = fsum(weights.values())
    weights = {ticker: weight / total for ticker, weight in weights.items()}
    values, paths = _cad_paths(weights, cad)
    running_peaks = []
    peak = 0
    for index, value in enumerate(values):
        if value > values[peak] * (1.0 + _TIE_TOLERANCE):
            peak = index
        running_peaks.append(peak)
    drawdowns = [1.0 - value / values[peak] for value, peak in zip(values, running_peaks)]
    worst = max(drawdowns)
    trough = next(index for index, decline in enumerate(drawdowns) if decline >= worst - _TIE_TOLERANCE)
    peak = running_peaks[trough]
    recovered = next((index for index in range(trough + 1, len(values))
                      if values[index] >= values[peak] * (1.0 - _TIE_TOLERANCE)), None)
    terminal_return = values[-1] / values[0] - 1.0
    daily = [following / prior - 1.0 for prior, following in zip(values, values[1:])]
    return {
        **_period(days[0], days[-1]), "observations": len(days),
        "terminal_return": terminal_return, "terminal_loss": max(0.0, -terminal_return),
        "max_drawdown": drawdowns[trough], "peak_date": days[peak].isoformat(),
        "trough_date": days[trough].isoformat(), **_recovery(days, peak, trough, recovered),
        "rolling": _rolling(days, values), "worst_month": _monthly(days, values),
        "annualized_volatility": (
            _number(stdev(daily) * sqrt(_ANNUAL_SESSIONS), "Annualized volatility") if len(daily) >= 2 else None
        ),
        "attribution": {ticker: weight * (paths[ticker][-1] - 1.0)
                        for ticker, weight in weights.items()},
        "drawdown_attribution": {
            ticker: weight * (paths[ticker][peak] - paths[ticker][trough]) / values[peak]
            for ticker, weight in weights.items()
        },
        "observed_path": [{"date": day.isoformat(), "value": value, "drawdown": decline}
                          for day, value, decline in zip(days, values, drawdowns)],
        "fx_decomposition": _fx_decomposition(weights, paths, local),
    }


def _independent_paths(weights, cad, local):
    with localcontext() as context:
        context.prec = 40
        amounts = {ticker: Decimal(str(weight)) for ticker, weight in weights.items()}
        total = sum(amounts.values())
        holding_values = {}
        fx = None if local is None else {}
        for ticker, amount in amounts.items():
            series = tuple(Decimal(str(value)) for value in cad[ticker])
            initial_cad_value = series[0]
            allocation = amount / total
            shares = allocation / initial_cad_value
            holding_values[ticker] = tuple(shares * price for price in series)
            if fx is not None:
                opening, closing = map(lambda value: Decimal(str(value)), (local[ticker][0], local[ticker][-1]))
                starting_fx = series[0] / opening
                ending_fx = series[-1] / closing
                currency_growth = ending_fx / starting_fx
                _number(currency_growth, f"FX movement for {ticker}", positive=True)
                currency_result = allocation * (currency_growth - 1)
                local_result = allocation * (closing / opening - 1)
                cad_result = holding_values[ticker][-1] - holding_values[ticker][0]
                fx_effect = cad_result - local_result
                fx[ticker] = {
                    "cad_return": float(cad_result), "local_return": float(local_result),
                    "fx_return": float(currency_result), "interaction_return": float(fx_effect - currency_result),
                    "fx_impact": float(fx_effect),
                }
        values = [float(sum(column)) for column in zip(*holding_values.values())]
        return values, holding_values, fx


def _independent_periods(days, values):
    rolling = {}
    for years in (1, 3):
        rows = []
        first = -1
        for last, day in enumerate(days):
            if day.year <= years:
                continue
            try:
                anniversary = day.replace(year=day.year - years)
            except ValueError:
                anniversary = day.replace(year=day.year - years, day=28)
            while first + 1 < last and days[first + 1] <= anniversary:
                first += 1
            if first >= 0:
                rows.append(((values[last] - values[first]) / values[first], first, last))
        rolling[f"{years * 12}m"] = _minimum_period(days, rows, key="worst_return")

    month_ends = [
        (year, month, max(index for index, _ in group))
        for (year, month), group in groupby(enumerate(days), key=lambda row: (row[1].year, row[1].month))
    ]
    observations = []
    for (first_year, first_month, first), (year, month, last) in zip(month_ends, month_ends[1:]):
        if 12 * (year - first_year) + month - first_month != 1:
            continue
        if last == len(days) - 1 and days[last].day < monthrange(year, month)[1]:
            continue
        observations.append(((values[last] - values[first]) / values[first], first, last))
    monthly = _minimum_period(days, observations, key="return")
    return rolling, {"month": monthly["end_date"][:7] if monthly["end_date"] else None, **monthly}


def _new_peak(previous, row):
    return row if row[1] > previous[1] * (1.0 + _TIE_TOLERANCE) else previous


def _independent_results(weights, days, cad, local):
    values, holdings, fx = _independent_paths(weights, cad, local)
    max_levels = list(accumulate(enumerate(values), _new_peak))
    declines = [(level - value) / level for value, (_, level) in zip(values, max_levels)]
    bound = max(declines) - _TIE_TOLERANCE
    trough = next(index for index, decline in enumerate(declines) if decline >= bound)
    peak, level = max_levels[trough]
    later = (i for i in range(trough + 1, len(days)) if (level - values[i]) / level <= _TIE_TOLERANCE)
    recovered = next(later, None)
    change = (values[-1] - values[0]) / values[0]
    increments = [(values[index] - values[index - 1]) / values[index - 1]
                  for index in range(1, len(days))]
    volatility = None
    if len(increments) > 1:
        scale = max(abs(value) for value in increments)
        if scale:
            normalized = [value / scale for value in increments]
            average = fsum(normalized) / len(normalized)
            dispersion = fsum((value - average) ** 2 for value in normalized)
            volatility = _number(scale * sqrt(_ANNUAL_SESSIONS * dispersion / (len(increments) - 1)),
                                 "Annualized volatility")
        else:
            volatility = 0.0
    recovered_on = None if recovered is None or peak == trough else days[recovered]
    peak_day, trough_day = days[peak].toordinal(), days[trough].toordinal()
    recovery_days = None
    if peak == trough:
        recovery_status, recovery_days, days_underwater = "no_drawdown", 0, 0
    elif recovered_on is None:
        recovery_status, days_underwater = "unrecovered", days[-1].toordinal() - peak_day
    else:
        recovery_status = "recovered"
        recovery_days = recovered_on.toordinal() - peak_day
        days_underwater = recovered_on.toordinal() - peak_day
    rolling, monthly = _independent_periods(days, values)
    fx_totals = None
    if fx is not None:
        fx_totals = {
            key: float(sum(Decimal(str(row[key])) for row in fx.values())) for key in next(iter(fx.values()))
        }
        fx_totals["by_ticker"] = fx
    return {
        **_period(days[0], days[-1]), "observations": len(days),
        "terminal_return": change, "terminal_loss": -change if change < 0 else 0.0,
        "max_drawdown": declines[trough], "peak_date": days[peak].isoformat(),
        "trough_date": days[trough].isoformat(), "recovery_status": recovery_status,
        "recovery_date": recovered_on.isoformat() if recovered_on is not None else None,
        "recovery_days": recovery_days, "days_underwater": days_underwater,
        "rolling": rolling, "worst_month": monthly, "annualized_volatility": volatility,
        "attribution": {ticker: float(path[-1] - path[0]) for ticker, path in holdings.items()},
        "drawdown_attribution": {ticker: float(path[peak] - path[trough]) / level
                                 for ticker, path in holdings.items()},
        "observed_path": [{"date": day.isoformat(), "value": values[index],
                           "drawdown": (max_levels[index][1] - values[index]) / max_levels[index][1]}
                          for index, day in enumerate(days)],
        "fx_decomposition": fx_totals,
    }


def _require_match(expected, claimed, path="metrics"):
    if isinstance(expected, dict):
        if isinstance(claimed, Mapping) and expected.keys() == claimed.keys():
            for key, value in expected.items():
                _require_match(value, claimed[key], f"{path}.{key}")
            return
    elif isinstance(expected, list):
        if isinstance(claimed, list) and len(claimed) == len(expected):
            for index, (value, actual) in enumerate(zip(expected, claimed)):
                _require_match(value, actual, f"{path}[{index}]")
            return
    elif type(expected) is float:
        if (isinstance(claimed, Real) and not isinstance(claimed, bool)
                and isfinite(claimed) and isclose(expected, claimed, rel_tol=1e-10, abs_tol=1e-12)):
            return
    elif type(expected) is type(claimed) and claimed == expected:
        return
    raise ValueError(f"Independent replay verification rejected {path}.")


def verify(weights, dates, cad_prices, claimed, local_prices=None):
    """Return the independently recomputed metrics or raise for a rejected claim."""
    inputs = _inputs(weights, dates, cad_prices, local_prices)
    checked = _independent_results(*inputs)
    _require_match(checked, claimed)
    return checked


def _stress_bounds(days, start_date, end_date):
    try:
        start = days.index(date.fromisoformat(start_date))
        end = days.index(date.fromisoformat(end_date))
    except (TypeError, ValueError) as exc:
        raise ValueError("Stress endpoints must both be present in the aligned observation dates.") from exc
    if start >= end:
        raise ValueError("The stress window must contain at least one price change.")
    return start, end


def _stress_record(days, start, end, intervals, samples, metrics):
    return {
        **_period(days[start], days[end]), "matched_observation_intervals": intervals,
        "observation_count": samples, "percentile_method": "empirical_midrank", **metrics,
    }


def stress_percentile(weights, dates, cad_prices, start_date, end_date):
    """Rank exact stress endpoints against all equal-length windows of the supplied history.

    Length is the number of aligned observation intervals. Percentiles are
    fractions from zero to one, with half weight for ties. Low return ranks
    and high drawdown ranks indicate more severe outcomes. The supplied stress
    window is included in the reference distribution. Each candidate window
    starts with the same supplied allocation and then holds its units fixed;
    holdings do not drift from the start of the full history into later windows.
    """
    weights, days, prices, _ = _inputs(weights, dates, cad_prices, None)
    first, last = _stress_bounds(days, start_date, end_date)
    intervals = last - first
    total = fsum(weights.values())
    weights = {ticker: weight / total for ticker, weight in weights.items()}
    ratios, drawdowns = [], []
    for start in range(len(days) - intervals):
        end = start + intervals
        values = [fsum(weight * prices[ticker][i] / prices[ticker][start]
                       for ticker, weight in weights.items()) for i in range(start, end + 1)]
        ratios.append(values[-1] / values[0] - 1.0)
        peak = values[0]
        max_drawdown = 0.0
        for value in values[1:]:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, 1.0 - value / peak)
        drawdowns.append(max_drawdown)
    metrics = {}
    for name, samples in (("terminal_return", ratios), ("max_drawdown", drawdowns)):
        observed = samples[first]
        lower = sum(value < observed - _TIE_TOLERANCE for value in samples)
        upper = sum(value > observed + _TIE_TOLERANCE for value in samples)
        ties = len(samples) - lower - upper
        metrics[name] = {"value": observed, "percentile": (lower + 0.5 * ties) / len(samples)}
    return _stress_record(days, first, last, intervals, len(ratios), metrics)


def verify_stress_percentile(weights, dates, cad_prices, start_date, end_date, claimed):
    """Independently recompute a named stress ranking and verify the result."""
    weights, days, prices, _ = _inputs(weights, dates, cad_prices, None)
    first, last = _stress_bounds(days, start_date, end_date)
    intervals = last - first
    periods = []
    # Reconstruct actual units separately at each window's own opening price.
    # Decimal valuation is deliberately independent of the float ratio loop.
    with localcontext() as context:
        context.prec = 40
        allocations = {ticker: Decimal(str(weight)) for ticker, weight in weights.items()}
        total = sum(allocations.values())
        quotes = {ticker: tuple(Decimal(str(value)) for value in prices[ticker]) for ticker in weights}
        for start in range(len(days) - intervals):
            units = {ticker: amount / total / quotes[ticker][start] for ticker, amount in allocations.items()}
            periods.append([float(sum(units[ticker] * quotes[ticker][i] for ticker in units))
                            for i in range(start, start + intervals + 1)])
    returns = [(period[-1] - period[0]) / period[0] for period in periods]
    drawdowns = [max((peak - value) / peak for value, peak in zip(period, accumulate(period, max)))
                 for period in periods]
    metrics = {}
    for name, samples in (("terminal_return", returns), ("max_drawdown", drawdowns)):
        observed = samples[first]
        ordered = sorted(samples)
        lower = bisect_left(ordered, observed - _TIE_TOLERANCE)
        at_most = bisect_right(ordered, observed + _TIE_TOLERANCE)
        metrics[name] = {"value": observed, "percentile": (lower + at_most) / (2 * len(ordered))}
    checked = _stress_record(days, first, last, intervals, len(periods), metrics)
    _require_match(checked, claimed, path="stress_percentile")
    return checked
