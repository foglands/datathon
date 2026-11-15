"""Expected joint price/FX sessions for the archived competition replays."""

from datetime import date, timedelta


# The reference calendar is independent of the input being audited. The dates below
# are the weekday closures in the common US/Canadian price panel for the frozen cases.
_REFERENCE_WINDOWS = {
    ("2021-12-31", "2022-12-30"): {
        "2022-01-03", "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-23",
        "2022-05-30", "2022-06-20", "2022-07-01", "2022-07-04", "2022-08-01",
        "2022-09-05", "2022-10-10", "2022-11-24", "2022-12-26", "2022-12-27",
    },
    ("2023-07-31", "2023-10-31"): {"2023-08-07", "2023-09-04", "2023-10-09"},
    ("2024-12-31", "2025-04-08"): {"2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17"},
}

# These sessions have prices for every reference asset, but no same-day CAD fixing.
_KNOWN_MISSING_FX = frozenset({"2022-09-30", "2022-11-11", "2023-10-02"})
STARTER_CALENDAR_ID = "official-starter-joint-sessions-v1"
STARTER_CALENDAR_ASSETS = frozenset({"SPY", "XIU.TO", "QQQ", "ZST.TO", "NVDA"})


def _expected_sessions(start, end, price_closures):
    first = date.fromisoformat(start)
    length = (date.fromisoformat(end) - first).days + 1
    weekdays = (first + timedelta(days=offset) for offset in range(length))
    return frozenset(day.isoformat() for day in weekdays if day.weekday() < 5) - price_closures - _KNOWN_MISSING_FX


_REPLAY_SESSIONS = {
    window: _expected_sessions(*window, closures) for window, closures in _REFERENCE_WINDOWS.items()
}


def starter_calendar_gap(start, end, aligned_dates):
    """Describe deviations from the pinned calendar for a reference window, if any."""
    expected = _REPLAY_SESSIONS.get((start, end))
    if expected is None:
        return None
    aligned = set(aligned_dates)
    differences = []
    for description, days in (("missing", expected - aligned), ("unexpected", aligned - expected)):
        if days:
            sample = ", ".join(sorted(days)[:3])
            suffix = ", …" if len(days) > 3 else ""
            differences.append(f"{len(days)} {description} ({sample}{suffix})")
    if differences:
        return (f"Starter replay calendar mismatch for {start} to {end}: "
                f"{', '.join(differences)} aligned price/FX sessions.")


def _missing_reason(day, price_dates, fixing_dates, converted_price_dates):
    missing_price = price_dates is not None and day not in price_dates
    missing_fixing = fixing_dates is not None and day not in fixing_dates
    if missing_price and missing_fixing:
        return "missing_prices_and_fx"
    if missing_price:
        return "missing_adjusted_close"
    if missing_fixing:
        return "missing_fx_fixing"
    if converted_price_dates is not None and day not in converted_price_dates:
        return "missing_converted_price"
    return "missing_aligned_observation"


def _consecutive_gaps(expected, missing):
    # Consecutive expected sessions can straddle a weekend or a known closure.
    gaps = []
    previous_index = -2
    for index, day in enumerate(sorted(expected)):
        if day not in missing:
            continue
        if previous_index == index - 1:
            gap = gaps[-1]
            gap["end"] = day
            gap["observations"] += 1
        else:
            gaps.append({"start": day, "end": day, "observations": 1})
        previous_index = index
    return gaps


def starter_calendar_coverage(start, end, aligned_dates, *, applicable=True,
                              price_dates=None, fixing_dates=None, converted_price_dates=None):
    """Describe the coverage against the independent, frozen reference sessions."""
    window = (start, end)
    expected = _REPLAY_SESSIONS.get(window) if applicable else None
    observed = set(aligned_dates)
    known_exclusions = {}
    if expected is not None:
        known_exclusions = {day: "documented_exchange_closure" for day in _REFERENCE_WINDOWS[window]}
        known_exclusions.update({day: "documented_fx_exclusion"
                                 for day in _KNOWN_MISSING_FX if start <= day <= end})

    excluded = {day: known_exclusions[day] for day in known_exclusions.keys() - observed}
    if expected is None and price_dates is not None and fixing_dates is not None:
        excluded.update({day: "observed_prices_without_fx" for day in set(price_dates).difference(fixing_dates)
                         if start <= day <= end})

    result = {
        "status": "coverage_not_verified",
        "calendar_id": None,
        "expected_observations": None,
        "excluded_dates": [{"date": day, "reason": excluded[day]} for day in sorted(excluded)],
        "missing_dates": [],
        "unexpected_dates": [],
        "consecutive_gaps": [],
    }
    if expected is None:
        result["reason"] = "reference_calendar_unavailable" if applicable else "reference_calendar_not_applicable"
        return result

    missing = expected - observed
    unexpected = observed - expected
    result.update(
        status="incomplete" if missing or unexpected else "verified",
        calendar_id=STARTER_CALENDAR_ID,
        expected_observations=len(expected),
        missing_dates=[{"date": day, "reason": _missing_reason(day, price_dates, fixing_dates,
                                                              converted_price_dates)} for day in sorted(missing)],
        unexpected_dates=[{"date": day, "reason": known_exclusions.get(day, "outside_reference_sessions")}
                          for day in sorted(unexpected)],
        consecutive_gaps=_consecutive_gaps(expected, missing),
    )
    return result
