"""Issuer-documented benchmark objectives for the supported fund analyses."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import fsum


@dataclass(frozen=True)
class FundBenchmark:
    name: str
    source: str


# Reviewed plain, unleveraged US-listed index ETFs. An identical benchmark
# supports illustrating an exposure with a covered representative series.
# It does not establish identical holdings, costs, or market returns.
_FUND_BENCHMARKS = {
    "VOO": FundBenchmark("S&P 500 Index", "https://workplace.vanguard.com/assets/corp/fund_communications/pdf_publish/us-products/fact-sheet/F0968.pdf"),
    "SPY": FundBenchmark("S&P 500 Index", "https://www.ssga.com/us/en/institutional/etfs/state-street-spdr-sp-500-etf-trust-spy"),
    "IVV": FundBenchmark("S&P 500 Index", "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf"),
    "QQQ": FundBenchmark("Nasdaq-100 Index", "https://www.invesco.com/us/en/financial-products/etfs/invesco-qqq-trust-series-1.html"),
}


def benchmark_allocations(weights: Mapping[str, float]) -> list[dict]:
    """Group stated starting weights by the documented investment objective."""
    grouped = defaultdict(dict)
    for ticker, weight in weights.items():
        evidence = _FUND_BENCHMARKS.get(ticker)
        grouped[evidence.name if evidence else None][ticker] = weight
    return [
        {
            "benchmark": name,
            "weight": fsum(funds.values()),
            "tickers": list(funds),
            "sources": {ticker: _FUND_BENCHMARKS[ticker].source for ticker in funds} if name else {},
        }
        for name, funds in grouped.items()
    ]


def benchmark_proxies(weights: Mapping[str, float], available_assets: Iterable[str]) -> dict[str, str]:
    """Propose covered, same-benchmark stand-ins only for documented funds."""
    available = set(available_assets)
    choices = sorted(available & _FUND_BENCHMARKS.keys(), key=lambda ticker: (ticker not in weights, ticker))
    substitutes = {}
    for ticker in weights.keys() - available:
        documented = _FUND_BENCHMARKS.get(ticker)
        if documented and (proxy := next((choice for choice in choices if _FUND_BENCHMARKS[choice].name == documented.name), None)):
            substitutes[ticker] = proxy
    return dict(sorted(substitutes.items()))


def apply_proxies(weights: Mapping[str, float], substitutes: Mapping[str, str]) -> dict[str, float]:
    """Keep every stated starting weight when combining equivalent replay series."""
    grouped = defaultdict(list)
    for ticker, weight in weights.items():
        grouped[substitutes.get(ticker, ticker)].append(weight)
    return {ticker: fsum(parts) for ticker, parts in grouped.items()}
