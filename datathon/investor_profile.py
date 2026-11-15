"""Fictional investor context and explicit priorities for historical analysis."""

from dataclasses import dataclass

from .scope import OBJECTIVES, WITHDRAWAL_TIMES


PRIORITIES = {
    "max_drawdown": "Maximum drawdown",
    "terminal_loss": "Terminal loss",
    "terminal_return": "Terminal return",
}
RISK_TOLERANCES = ("Low", "Moderate", "High")
_GROWTH, _PRESERVATION, _WITHDRAWAL = OBJECTIVES
_NEAR_TERM, _, _LONG_TERM = WITHDRAWAL_TIMES


def _priority_suggestion(objective: str, withdrawal_time: str, risk_tolerance: str | None) -> tuple[str, str]:
    if objective not in OBJECTIVES:
        raise ValueError("Choose a fictional investment objective.")
    if withdrawal_time not in WITHDRAWAL_TIMES:
        raise ValueError("Choose the next meaningful withdrawal horizon.")
    if risk_tolerance is not None and risk_tolerance not in RISK_TOLERANCES:
        raise ValueError("Choose a stated willingness to take investment risk.")

    if withdrawal_time == _NEAR_TERM:
        return "max_drawdown", (
            "A withdrawal within one year makes losses during a replay relevant, even if the path later recovers. "
            "Maximum drawdown measures each replay's largest fall from a prior peak."
        )
    if objective == _PRESERVATION:
        return "max_drawdown", (
            "For capital preservation, maximum drawdown highlights the largest fall from a prior peak "
            "during each replay."
        )
    if objective == _GROWTH and withdrawal_time == _LONG_TERM:
        if risk_tolerance == "Low":
            return "max_drawdown", (
                "For long-horizon growth with a low stated willingness to take risk, maximum drawdown "
                "highlights how sharply each option fell during the historical replays."
            )
        return "terminal_return", (
            "For growth with no meaningful withdrawal in the next five years, terminal return compares "
            "the signed change in value from start to finish across the same historical windows."
        )
    if objective == _WITHDRAWAL:
        return "terminal_loss", (
            "For a planned withdrawal beyond one year, terminal loss highlights any shortfall from starting "
            "value at the end of each replay. Replay endpoints stand for historical comparison dates."
        )
    return "terminal_loss", (
        "A growth objective with a withdrawal in one to five years makes ending losses worth checking. "
        "Terminal loss measures each replay's shortfall from its starting value."
    )


def suggest_priority(objective: str, withdrawal_time: str, risk_tolerance: str | None = None) -> str:
    """Suggest a historical metric which the investor must confirm or change."""
    return _priority_suggestion(objective, withdrawal_time, risk_tolerance)[0]


@dataclass(frozen=True)
class InvestorProfile:
    """Store confirmed fictional context without inferring binding financial limits."""

    objective: str
    withdrawal_time: str
    priority: str
    require_esg: bool = False
    risk_tolerance: str | None = None

    def __post_init__(self):
        suggest_priority(self.objective, self.withdrawal_time, self.risk_tolerance)
        if not isinstance(self.priority, str) or self.priority not in PRIORITIES:
            raise ValueError("Confirm a supported historical comparison priority.")
        if type(self.require_esg) is not bool:
            raise ValueError("Confirm whether the comparison requires ESG evidence.")

    @property
    def explanation(self) -> str:
        suggested, reason = _priority_suggestion(self.objective, self.withdrawal_time, self.risk_tolerance)
        if suggested == self.priority:
            return reason
        return f"{reason} Your confirmed comparison priority is {PRIORITIES[self.priority].lower()}."

    @property
    def audit_focus(self) -> str | None:
        """Return a compatible loss measure when the investor enables a trade-audit cap."""
        return None if self.priority == "terminal_return" else self.priority

    def report(self) -> dict:
        return {
            "objective": self.objective,
            "withdrawal_time": self.withdrawal_time,
            "priority": self.priority,
            "require_esg": self.require_esg,
            "risk_tolerance": self.risk_tolerance,
            "explanation": self.explanation,
        }
