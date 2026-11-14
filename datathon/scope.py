"""Explicit scope for a structured fictional portfolio audit."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .finance import BASE_WEIGHTS, STRESS_WINDOWS, StressWindow


EXTRA_WINDOW = StressWindow("2023", "2023 late-summer and fall replay", "2023-07-31", "2023-10-31")
OBJECTIVES = ("Growth", "Capital preservation", "Fund a planned withdrawal")
WITHDRAWAL_TIMES = ("Within 1 year", "1 to 5 years", "More than 5 years")


@dataclass(frozen=True)
class ReplayScope:
    starting_weights_bps: Mapping[str, int] | None = None
    include_2023: bool = False
    objective: str | None = None
    withdrawal_time: str | None = None

    def __post_init__(self):
        supplied = self.starting_weights_bps
        if supplied is not None:
            supplied = dict(supplied)
            if (set(supplied) != set(BASE_WEIGHTS)
                    or any(type(value) is not int or not 0 <= value <= 10000 for value in supplied.values())
                    or sum(supplied.values()) != 10000):
                raise ValueError("Enter all five supported weights. Each must be between 0 and 100%, totaling exactly 100%.")
            object.__setattr__(self, "starting_weights_bps", MappingProxyType(supplied))
        if type(self.include_2023) is not bool:
            raise ValueError("Select whether to include the fixed 2023 replay.")
        if self.objective is not None and self.objective not in OBJECTIVES:
            raise ValueError("Choose a supported fictional objective.")
        if self.withdrawal_time is not None and self.withdrawal_time not in WITHDRAWAL_TIMES:
            raise ValueError("Choose a supported fictional withdrawal horizon.")

    @property
    def baseline(self):
        if self.starting_weights_bps is None:
            return dict(BASE_WEIGHTS)
        return {ticker: self.starting_weights_bps[ticker] / 10000 for ticker in BASE_WEIGHTS}

    @property
    def windows(self):
        if self.include_2023:
            return tuple(sorted((*STRESS_WINDOWS, EXTRA_WINDOW), key=lambda window: window.start))
        return STRESS_WINDOWS

    def report(self):
        return {
            "starting_weights": self.baseline,
            "replay_windows": [{"id": w.id, "start": w.start, "end": w.end} for w in self.windows],
            "planning_context": {"objective": self.objective, "withdrawal_time": self.withdrawal_time},
        }
