"""Calculate share-purchase metrics from dated, validated market evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import re

from .live_market_data import DailyHistory, MarketQuote
from .review_snapshot import fingerprint


_SHARES = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?")
_TOLERANCE = Decimal("1e-28")


@dataclass(frozen=True)
class TrailingMetrics:
    start: date
    end: date
    observations: int
    price_return: Decimal
    max_drawdown: Decimal
    peak_date: date
    trough_date: date
    source: str
    source_url: str
    feed: str
    adjustment: str
    calendar_source_url: str
    retrieved_at: datetime
    observations_sha256: str

    def as_evidence(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "observations": self.observations,
            "price_return_fraction": str(self.price_return),
            "max_drawdown_fraction": str(self.max_drawdown),
            "peak_date": self.peak_date.isoformat(),
            "trough_date": self.trough_date.isoformat(),
            "source": self.source,
            "source_url": self.source_url,
            "feed": self.feed,
            "adjustment": self.adjustment,
            "calendar_source_url": self.calendar_source_url,
            "retrieved_at": self.retrieved_at.isoformat(),
            "observations_sha256": self.observations_sha256,
        }


@dataclass(frozen=True)
class SharePurchaseAnalysis:
    ticker: str
    shares: Decimal | None
    quote: MarketQuote
    indicative_notional: Decimal | None
    trailing: TrailingMetrics | None
    history_withheld_reason: str | None

    def as_model_evidence(self) -> dict:
        """Project verified observations and metrics into a JSON-safe model payload."""
        result = {
            "ticker": self.ticker,
            "shares": str(self.shares) if self.shares is not None else None,
            "quote": {
                "price": str(self.quote.price),
                "currency": self.quote.currency,
                "as_of": self.quote.as_of.isoformat(),
                "retrieved_at": self.quote.retrieved_at.isoformat(),
                "source": self.quote.source,
                "source_url": self.quote.source_url,
                "feed": self.quote.feed,
                "price_basis": "latest reported trade",
            },
            "indicative_notional": str(self.indicative_notional) if self.indicative_notional is not None else None,
            "trailing": self.trailing.as_evidence() if self.trailing is not None else None,
            "history_withheld_reason": self.history_withheld_reason,
            "scope": {"portfolio_impact": "unassessed", "fees_and_slippage": "excluded"},
            "formula_versions": {
                "indicative_notional": "share-count-times-trade-price-v1",
                "trailing_price_risk": "daily-close-return-and-drawdown-v1",
            },
        }
        return {**result, "evidence_sha256": fingerprint(result)}


def _positive_decimal(value) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def _valid_price(value) -> bool:
    # Keep anomalous decimal encodings from expanding into huge exact integers.
    return _positive_decimal(value) and abs(value.adjusted()) <= 16 and len(value.as_tuple().digits) <= 34


def _aware(value) -> bool:
    return isinstance(value, datetime) and value.utcoffset() is not None


def _quantity(value: str | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHARES.fullmatch(value):
        raise ValueError("Share quantity must be a positive decimal written in the request.")
    shares = Decimal(value.replace(",", ""))
    if not _positive_decimal(shares):
        raise ValueError("Share quantity must be a positive decimal written in the request.")
    return shares


def _matches_reference(value: Decimal, reference: Fraction) -> bool:
    exact = Decimal(reference.numerator) / Decimal(reference.denominator)
    return abs(value - exact) <= _TOLERANCE * max(1, abs(exact))


def _review_trailing(prices, price_return, max_drawdown, peak_index, trough_index) -> bool:
    """Check the return by chaining closes and scan drawdown from each future minimum."""
    fractions = tuple(map(Fraction, prices))
    compounded = Fraction(1)
    for previous, current in zip(fractions, fractions[1:]):
        compounded *= current / previous
    lowest_later = fractions[-1]
    largest_drop = Fraction(0)
    for price in reversed(fractions):
        lowest_later = min(lowest_later, price)
        largest_drop = max(largest_drop, 1 - lowest_later / price)
    witness = 1 - fractions[trough_index] / fractions[peak_index]
    return (_matches_reference(price_return, compounded - 1)
            and _matches_reference(max_drawdown, largest_drop)
            and _matches_reference(max_drawdown, witness))


def _trailing_metrics(history: DailyHistory | None, quote: MarketQuote) -> tuple[TrailingMetrics | None, str | None]:
    if history is None:
        return None, "Daily price history was unavailable."
    if history.symbol != quote.symbol or history.currency != quote.currency:
        return None, "Daily prices do not match the quoted ticker and currency."
    if history.adjustment != "split":
        return None, "Daily prices require a split-adjusted series."
    if history.expected_sessions is None or not history.calendar_source_url:
        return None, "The requested sessions could not be verified against an exchange calendar."
    dates = tuple(item.session for item in history.closes)
    if (len(dates) < 2 or any(type(day) is not date for day in dates)
            or any(first >= second for first, second in zip(dates, dates[1:]))
            or dates != history.expected_sessions or not history.start <= dates[0] <= dates[-1] <= history.end):
        return None, "Daily prices must include one close for every requested trading session."
    prices = tuple(item.close for item in history.closes)
    if any(not _valid_price(price) for price in prices) or not _aware(history.retrieved_at):
        return None, "The daily price series contains invalid observations or timestamps."

    with localcontext(Context(prec=34)):
        price_return = prices[-1] / prices[0] - 1
        max_drawdown = Decimal(0)
        peak_index = worst_peak = worst_trough = 0
        for index, price in enumerate(prices):
            if price > prices[peak_index]:
                peak_index = index
            drawdown = 1 - price / prices[peak_index]
            if drawdown > max_drawdown:
                max_drawdown, worst_peak, worst_trough = drawdown, peak_index, index
        if not _review_trailing(prices, price_return, max_drawdown, worst_peak, worst_trough):
            return None, "The independent historical calculation check failed."

    return TrailingMetrics(
        start=dates[0], end=dates[-1], observations=len(dates), price_return=price_return,
        max_drawdown=max_drawdown, peak_date=dates[worst_peak], trough_date=dates[worst_trough],
        source=history.source, source_url=history.source_url, feed=history.feed, adjustment=history.adjustment,
        calendar_source_url=history.calendar_source_url, retrieved_at=history.retrieved_at,
        observations_sha256=fingerprint([(day.isoformat(), str(price)) for day, price in zip(dates, prices)]),
    ), None


def analyze_share_purchase(ticker: str, shares: str | None, quote: MarketQuote,
                           history: DailyHistory | None = None) -> SharePurchaseAnalysis:
    """Verify the priced inputs and calculate cost and eligible trailing metrics."""
    if (not ticker or quote.symbol != ticker or not isinstance(quote.currency, str)
            or not re.fullmatch(r"[A-Z]{3}", quote.currency) or not _valid_price(quote.price)
            or not _aware(quote.as_of) or not _aware(quote.retrieved_at) or quote.as_of > quote.retrieved_at):
        raise ValueError("The provider quote did not verify for the requested ticker.")
    quantity = _quantity(shares)
    notional = None
    if quantity is not None:
        precision = len(quote.price.as_tuple().digits) + len(quantity.as_tuple().digits)
        with localcontext(Context(prec=precision)):
            notional = quantity * quote.price
        if Fraction(notional) / Fraction(quantity) != Fraction(quote.price):
            raise ValueError("The independent purchase-notional check failed.")
    trailing, withheld = _trailing_metrics(history, quote)
    return SharePurchaseAnalysis(ticker, quantity, quote, notional, trailing, withheld)
