"""Sourced explanations of risks mentioned in investment planning questions."""


_CONCENTRATION = "https://www.investor.gov/introduction-investing"
_CRYPTO = "https://www.ciro.ca/office-investor/understanding-risk/learn-about-risk-crypto-assets"
_OPTIONS = (
    "https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/"
    "investor-bulletins/leveraged-investing-strategies-know-risks-using-these-advanced-investment-tools"
)
_HIGH_RETURN_CLAIMS = "https://competition-bureau.canada.ca/en/fraud-and-scams/tips-and-advice/investment-scams"


RISK_OPTIONS = {
    "individual_stock": (
        "Individual company stocks",
        "Putting all investable savings into one stock ties that money to a single company's share price. "
        f"Diversification can reduce exposure to a decline in any one company. [Investor.gov diversification guide]({_CONCENTRATION})",
    ),
    "crypto": (
        "Cryptoassets such as Bitcoin",
        "Cryptoasset prices can move sharply over a short period. A large position exposes more of your savings "
        f"to that volatility and the possibility of substantial losses. [CIRO cryptoasset risk guide]({_CRYPTO})",
    ),
    "options": (
        "Options and leverage",
        "Options can use leverage to magnify gains and losses. A buyer can lose the full premium, and some "
        f"option-selling strategies can produce losses beyond the initial investment. [Investor.gov leverage bulletin]({_OPTIONS})",
    ),
}


def guarantee_guidance() -> str:
    """Explain the risk in treating a high annual return as guaranteed."""
    return (
        "Stocks, cryptoassets, and options can lose value. A promise of high guaranteed returns, especially "
        "with little or no risk, is a fraud warning sign. Verify the written terms and check the provider's "
        f"registration independently before sending money. [Competition Bureau investment fraud guide]({_HIGH_RETURN_CLAIMS})"
    )
