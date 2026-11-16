"""Small, dated factual extracts from public filings and issuer disclosures."""

from decimal import Decimal


_SPY_PROSPECTUS = "https://www.sec.gov/Archives/edgar/data/884394/000119312523017928/d449477d497.htm"
_SPY_HOLDINGS = "https://www.sec.gov/Archives/edgar/data/884394/000141036826089410/NPORT_J905_66407841_0626.htm"
_ESGU_RETURNS = "https://www.sec.gov/Archives/edgar/data/1100663/000119312525327016/R300.htm"
_TSLA_PRICES = "https://www.sec.gov/Archives/edgar/data/1114446/000111444623000724/tc8172999f_1fwp.htm"

_PRODUCTS = {
    "ESGU": (
        "ESGU · Index screening policy",
        "iShares describes screens for specified involvement in controversial weapons, civilian firearms, tobacco, "
        "thermal coal and oil sands, and for severe controversies according to MSCI's methodology. "
        "Checking whether a particular company is currently held or screened out requires dated holdings and issuer-level records.",
        ("https://www.ishares.com/us/literature/product-brief/ishares-esg-aware-equity-brief.pdf",),
    ),
    "ESGV": (
        "ESGV · Index screening policy",
        "Vanguard describes screens based on specified business activities and labor, human rights, environmental and "
        "anti-corruption standards. The index methodology alone cannot verify holdings or coverage of individual controversies.",
        ("https://www.sec.gov/Archives/edgar/data/52848/000005284826000628/R292.htm",),
    ),
    "SPY": (
        "SPY · Investment objective and disclosed holdings",
        "SPY tracks the S&P 500. Its June 30, 2026 schedule of investments lists NVIDIA as a holding. "
        "The observation establishes historical overlap with a direct NVIDIA investment. Today's weight and the "
        "impact on an entire portfolio require current holdings and before/after allocation weights.",
        (_SPY_PROSPECTUS, _SPY_HOLDINGS),
    ),
    "IBIT": (
        "IBIT · Bitcoin exposure",
        "iShares discloses that the trust seeks to reflect the price of bitcoin. It gives exposure to a single "
        "cryptoasset. Its objective alone supplies no measured correlation, loss protection or portfolio impact.",
        ("https://www.ishares.com/us/literature/prospectus/p-ishares-bitcoin-trust-12-31.pdf",),
    ),
}


def disclosure_evidence(symbols):
    """Return evidence for referenced instruments, independent of price availability."""
    symbols = set(symbols)
    blocks = {}
    for symbol, (title, description, sources) in _PRODUCTS.items():
        if symbol in symbols:
            blocks[f"{symbol}.disclosure"] = {"title": title, "text": description, "sources": list(sources),
                "scope": {"level": "asset", "objects": [symbol], "method": "dated product disclosure"}}

    if {"ESGU", "SPY"} <= symbols:
        esgu_return, spy_return = Decimal("-20.22"), Decimal("-18.17")
        difference = esgu_return - spy_return
        blocks["ESGU-SPY.disclosure"] = {"title": "ESGU and SPY · Calendar 2022 fund returns",
            "text": f"The reported calendar 2022 before-tax USD fund returns were {esgu_return}% for ESGU and "
                    f"{spy_return}% for SPY. The difference (ESGU minus SPY) was {difference} percentage points. "
                    "One calendar year does not establish daily volatility, maximum drawdown or future returns.",
            "sources": [_ESGU_RETURNS, _SPY_PROSPECTUS],
            "scope": {"level": "product_comparison", "objects": ["ESGU", "SPY"], "currency": "USD",
                "start": "2021-12-31", "end": "2022-12-31", "method": "reported before-tax fund returns and Python subtraction"}}

    if "TSLA" in symbols:
        start, end = Decimal("409.97"), Decimal("109.10")
        loss = end / start - 1
        blocks["TSLA.disclosure"] = {"title": "TSLA · A disclosed peak-to-trough episode",
            "text": f"From the highest closing price in Q4 2021 (USD {start}) to the lowest closing price in Q4 2022 "
                    f"(USD {end}), TSLA fell {abs(loss):.2%}. The filing reports split-adjusted USD closes. This is "
                    "one ordered historical peak-to-trough pair. The full-history maximum and future outcomes are unknown.",
            "sources": [_TSLA_PRICES],
            "scope": {"level": "asset", "objects": ["TSLA"], "currency": "USD", "start_period": "2021-Q4",
                "end_period": "2022-Q4", "method": "filed quarterly closing-price extrema and Python end/start minus one"}}
    return blocks
