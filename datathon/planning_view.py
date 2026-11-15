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
    "risk": "Concern about losses", "risk_preference": "Stated risk preference", "timing": "Stated timing",
    "beginner": "Investing experience", "concentration": "Concentration being considered",
    "peer_trading": "Other people's reported trades", "return_claim": "Return claim to check",
}

_OPTIONS = {
    "cash_deposits": (
        "Savings accounts and deposits",
        "Check access and interest for near-term spending. If you bank in Canada, a savings account or "
        "short-term deposit with suitable withdrawal terms can serve as a baseline. "
        f"[FCAC savings guidance]({_GOALS})",
    ),
    "sp500": (
        "S&P 500 ETF",
        "An S&P 500 fund spreads exposure across large U.S. companies and can fall before you need to withdraw. "
        f"SPY is one example. [Fund objective and risks]({_SPY})",
    ),
    "gold": (
        "Gold",
        "Gold prices can rise or fall. A bullion trust such as GLD generates no income, so you would sell "
        f"shares to cover expenses. [Issuer risk information]({_GOLD})",
    ),
    "bonds": (
        "Bonds and bond funds",
        "Check when you need the money and how rate changes affect the investment. Bond funds can lose value "
        f"before you withdraw. [Asset allocation guidance]({_ASSET_ALLOCATION})",
    ),
    "equity_funds": (
        "Equity funds",
        "Check which companies and markets the fund holds. A fund can spread exposure across holdings and "
        f"still lose value when the market falls. [Diversification guidance]({_ASSET_ALLOCATION})",
    ),
    "stocks": (
        "Stocks",
        "Stocks can lose value. Owning shares of one company adds exposure to that company's performance. "
        f"A diversified equity fund spreads that exposure across holdings. [Diversification guidance]({_ASSET_ALLOCATION})",
    ),
    **RISK_OPTIONS,
}

_CONSIDERATIONS = {
    "concentration": "Putting the entire balance in one asset ties it to that asset's price. "
                     f"Diversification spreads exposure. [Diversification guidance]({_ASSET_ALLOCATION})",
    "peer_trading": "Treat other people's profits as individual outcomes. Compare downside over your own time horizon.",
    "beginner": "Check how each option can make or lose money and how you would withdraw.",
    "risk": "A market drop matters most if you would need to sell during it.",
    "growth": "Weigh potential growth against how much the investment could fall before you need it.",
    "inflation": "Inflation changes purchasing power. Compare savings rates and inflation over the same period, "
                 f"including taxes and access terms where applicable. [Bank of Canada inflation guide]({_INFLATION})",
}


# The official bundle supports these illustrative exposures. Each remains a
# standalone market series rather than a proxy assigned to the user's holdings.
_CATEGORY_EXAMPLES = {"equity_funds": "SPY", "sp500": "SPY", "bonds": "AGG", "gold": "GLD"}


def render_balance_context(plan):
    """Display a stated balance separately from any market percentage replay."""
    points = plan["points"]
    issue = plan.get("balance_issue")
    amount = points.get("amount")
    if not amount and issue != "conflicting_amounts":
        return
    with st.container(key="planning-balance"):
        if issue == "conflicting_amounts":
            st.warning("The request gives different cash balances. Confirm which amount applies.")
        else:
            st.text(f"Stated amount · {amount}")
            if issue == "conflicting_currencies":
                st.warning("The request gives different currencies for the balance. Confirm its currency.")
            elif currency := points.get("currency"):
                st.text(f"Stated currency · {currency}")


def render_planning_answer(plan, *, allow_example=True):
    """Show an answer now and return example symbols for an optional replay."""
    points, instruments = plan["points"], plan["instruments"]
    with st.container(key="assistant-options", border=True):
        st.subheader("Planning considerations")
        if return_claim := points.get("return_claim"):
            st.text(f"Return claim to check · {return_claim}")
            st.warning(guarantee_guidance())
            if set(points) == {"return_claim"} and not instruments:
                return None
        low_risk = "risk_preference" in points
        if low_risk:
            st.write("Your stated priority is limiting losses.")
        elif "spending" in points:
            st.write("List your planned withdrawals and when they are due. Compare investments for the money "
                     "you could leave invested through a downturn.")
        else:
            st.write("Start with when you need the money and how much loss you could absorb by then.")
        render_balance_context(plan)
        if considerations := [note for field, note in _CONSIDERATIONS.items() if field in points]:
            st.markdown("\n".join(f"- {note}" for note in considerations))

        options = list(instruments)
        if (not options or any(key in points for key in ("spending", "cash_position"))) and "cash_deposits" not in options:
            options.insert(0, "cash_deposits")
        option_details = [_OPTIONS[instrument] for instrument in options
                          if instrument in _OPTIONS and (instrument != "equity_funds" or "sp500" not in options)]
        if option_details:
            st.markdown("**Risks to compare**" if low_risk else "**What to compare**")
            for heading, details in option_details:
                st.markdown(f"**{heading}.** {details}")

        with st.container(key="planning-next-step"):
            st.markdown("**What to add to your question**")
            if low_risk:
                st.write("What loss could you tolerate before your first withdrawal?" if "timing" in points
                         else "When do you expect to need this money?")
            elif "timing" in points:
                st.write("How much needs to stay available for planned expenses?")
            elif "spending" in points:
                st.write("When will you first need to withdraw money, and roughly how much will you need then?")
            else:
                st.write("How much of your savings must stay accessible for expenses or emergencies, and when might you need it?")
        stated_details = [f"{_POINT_LABELS[key]} · {value}" for key, value in points.items()
                          if key in _POINT_LABELS and key not in {"amount", "currency", "return_claim"}]
        if stated_details:
            with st.expander("Details from your question"):
                st.text("\n".join(stated_details))

    if not allow_example:
        return None
    symbols = plan["examples"]
    if len(symbols) < 2 and all(category in _CATEGORY_EXAMPLES for category in instruments):
        symbols = tuple(dict.fromkeys((*symbols, *(_CATEGORY_EXAMPLES[category] for category in instruments))))
    if len(symbols) == 2:
        return {symbol: {symbol: 1.0} for symbol in symbols}
    if "stocks" in instruments and "crypto" in instruments and symbols:
        st.caption("For a historical comparison, add the specific stock or fund you want to compare with the cryptoasset you named.")
    else:
        st.caption("For a historical data comparison, ask about two supported ticker symbols or give two complete allocations.")
    return None
