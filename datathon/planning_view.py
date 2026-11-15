"""Render educational decision support from the planning question's stated facts."""

import streamlit as st

from .planning_risk import RISK_OPTIONS, guarantee_guidance


_GOALS = "https://www.canada.ca/en/financial-consumer-agency/services/savings-investments/savings-investment-goals.html"
_INFLATION = "https://www.bankofcanada.ca/2025/03/price-check-inflation-in-canada/"
_SPY = "https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy"
_GOLD = "https://www.ssga.com/us/en/individual/capabilities/alternatives/gold"
_ASSET_ALLOCATION = "https://www.investor.gov/introduction-investing/getting-started/asset-allocation"

_POINT_LABELS = {
    "amount": "Stated amount", "currency": "Stated currency", "cash_position": "Cash or savings",
    "spending": "Planned spending", "inflation": "Purchasing power concern", "growth": "Growth or income goal",
    "risk": "Concern about losses", "timing": "Stated timing",
    "beginner": "Investing experience", "concentration": "Concentration being considered",
    "peer_trading": "Other people's reported trades", "return_claim": "Return claim to check",
}

_OPTIONS = {
    "cash_deposits": (
        "Savings accounts and deposits",
        "For a near-term goal, check when the money can be withdrawn and whether the account pays interest. "
        "If banking in Canada, a savings account or short-term deposit with suitable access can serve as a baseline. "
        f"[FCAC savings guidance]({_GOALS})",
    ),
    "sp500": (
        "S&P 500 ETF",
        "An S&P 500 fund offers exposure across large U.S. companies while retaining stock-market risk. "
        f"The value can fall before a withdrawal is due. SPY is one example. [Fund objective and risks]({_SPY})",
    ),
    "gold": (
        "Gold",
        "Gold exposure rises or falls with its market price. A bullion trust such as GLD generates no income, "
        f"so cash for expenses would come from selling shares. [Issuer risk information]({_GOLD})",
    ),
    "bonds": (
        "Bonds and bond funds",
        "Compare when money is due and how the investment can react to a change in interest rates. "
        f"Bond funds can lose value before a withdrawal. [Asset allocation guidance]({_ASSET_ALLOCATION})",
    ),
    "equity_funds": (
        "Equity funds",
        "Check which companies and markets the fund holds. A fund can diversify across holdings while remaining exposed "
        f"to stock-market losses. [Diversification guidance]({_ASSET_ALLOCATION})",
    ),
    **RISK_OPTIONS,
}


def render_planning_answer(plan):
    """Show an answer now and return example symbols for an optional replay."""
    points, instruments = plan["points"], plan["instruments"]
    with st.container(key="assistant-options", border=True):
        st.subheader("Planning considerations")
        if stated_balance := points.get("amount"):
            st.text(f"Stated amount · {stated_balance}")
        if return_claim := points.get("return_claim"):
            st.text(f"Return claim to check · {return_claim}")
            st.warning(guarantee_guidance())
        if "spending" in points:
            st.write("Separate money you expect to spend from money you could leave invested through a downturn. "
                     "For the spending portion, the withdrawal date and accessible amount come first.")
        else:
            st.write("Start with when you need the money and what loss you could absorb at that time. "
                     "Those two facts help decide which options are worth comparing.")
        if "concentration" in points:
            st.markdown("Putting the entire balance into one asset exposes it to that asset's price swings. "
                        f"A diversified allocation spreads exposure across investments. [Diversification guidance]({_ASSET_ALLOCATION})")
        if "peer_trading" in points:
            st.write("Treat other people's profits as individual outcomes. Compare choices using their downside and "
                     "the risk to your savings over your own time horizon.")
        if "beginner" in points:
            st.write("Before comparing returns, check how each investment can make or lose money and how you would get your cash out.")
        if "risk" in points:
            st.write("Your concern about a market drop matters most if you would need to sell during it. "
                     "First identify the money that must stay accessible, then consider what loss you could tolerate on the rest.")
        if "inflation" in points:
            st.markdown("Inflation affects purchasing power. Compare the savings rate with inflation over the same period, "
                        f"and consider taxes and access terms where they apply. [Bank of Canada inflation guide]({_INFLATION})")

        options = list(instruments)
        if any(key in points for key in ("spending", "cash_position")) and "cash_deposits" not in options:
            options.insert(0, "cash_deposits")
        for instrument in options:
            if instrument in _OPTIONS and (instrument != "equity_funds" or "sp500" not in options):
                heading, details = _OPTIONS[instrument]
                st.markdown(f"**{heading}.** {details}")

        st.markdown("**The next detail to establish**")
        if "timing" in points:
            st.write("How much needs to stay available for planned expenses?")
        elif "spending" in points:
            st.write("When will you first need to withdraw money, and roughly how much will you need then?")
        else:
            st.write("How much of your savings must stay accessible for expenses or emergencies, and when might you need it?")
        if "amount" in points and "currency" not in points:
            st.caption("Confirm the currency for any calculation using the stated balance.")
        st.caption("You can add that detail to your question and interpret it again.")
        with st.expander("Details recognized from your question"):
            st.text("\n".join(f"{_POINT_LABELS[key]} · {value}" for key, value in points.items()
                              if key in _POINT_LABELS and key not in {"amount", "return_claim"}))

    if len(plan["examples"]) == 2:
        return {symbol: {symbol: 1.0} for symbol in plan["examples"]}
    return None
