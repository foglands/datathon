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
