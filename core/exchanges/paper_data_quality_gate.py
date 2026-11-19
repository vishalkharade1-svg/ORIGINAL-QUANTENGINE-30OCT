"""Fail-closed market-data gate for paper-strategy inputs (Phase 204).

This is a decision helper only: it does not place orders, mutate a portfolio,
or certify the authenticity of a feed. A caller must explicitly provide a
normalized quote and an evaluation clock. Missing/invalid inputs are rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.exchanges.market_data_validation import NormalizedBar, NormalizedQuote, validate_quote


@dataclass(frozen=True, slots=True)
class PaperDataGateDecision:
    accepted: bool
    reason_codes: tuple[str, ...]
    symbol: str | None = None
    source: str | None = None


def evaluate_paper_quote(
    quote: NormalizedQuote | None,
    *,
    now: datetime,
    expected_symbol: str,
    max_age_seconds: float,
    require_two_sided_quote: bool = False,
) -> PaperDataGateDecision:
    """Accept only a valid, fresh, correctly identified quote for paper use."""
    if quote is None:
        return PaperDataGateDecision(False, ("MARKET_DATA_UNAVAILABLE",))
    if not isinstance(expected_symbol, str) or not expected_symbol.strip():
        return PaperDataGateDecision(False, ("EXPECTED_SYMBOL_REQUIRED",), quote.symbol, quote.source)
    if require_two_sided_quote and (quote.bid is None or quote.ask is None):
        return PaperDataGateDecision(False, ("TWO_SIDED_QUOTE_REQUIRED",), quote.symbol, quote.source)
    report = validate_quote(
        quote,
        now=now,
        max_age_seconds=max_age_seconds,
        expected_symbol=expected_symbol,
    )
    mapping = {
        "symbol mismatch": "SYMBOL_MISMATCH",
        "stale market data": "MARKET_DATA_STALE",
        "market data timestamp is in the future": "MARKET_DATA_FUTURE_TIMESTAMP",
        "now must be timezone-aware": "EVALUATION_TIME_INVALID",
        "age tolerances must be non-negative": "AGE_TOLERANCE_INVALID",
    }
    codes = tuple(mapping.get(error, "MARKET_DATA_INVALID") for error in report.errors)
    if codes:
        return PaperDataGateDecision(False, codes, quote.symbol, quote.source)
    return PaperDataGateDecision(True, ("PAPER_DATA_ACCEPTED",), quote.symbol, quote.source)


def evaluate_paper_candle(
    candle,
    *,
    now: datetime,
    expected_symbol: str,
    max_age_seconds: float,
) -> PaperDataGateDecision:
    """Validate a closed-candle-like object before paper strategy intake.

    Candle timestamps in the existing engine are Unix seconds. This adapter
    intentionally validates only the minimum fields needed by the paper gate;
    it does not mutate the candle or call any execution API.
    """
    if candle is None:
        return PaperDataGateDecision(False, ("MARKET_DATA_UNAVAILABLE",))
    try:
        symbol = getattr(candle, "symbol", None)
        if not isinstance(symbol, str) or not symbol.strip():
            return PaperDataGateDecision(False, ("CANDLE_SYMBOL_MISSING",))
        if getattr(candle, "closed", True) is not True:
            return PaperDataGateDecision(False, ("CANDLE_NOT_CLOSED",), symbol, "paper-candle")
        timestamp = datetime.fromtimestamp(float(candle.timestamp), tz=timezone.utc)
        # Validate the full OHLCV envelope before adapting close to a quote.
        NormalizedBar(
            symbol=symbol, timestamp=timestamp, source="paper-candle",
            open=candle.open, high=candle.high, low=candle.low,
            close=candle.close, volume=getattr(candle, "volume", 0),
        )
        quote = NormalizedQuote(
            symbol=symbol, timestamp=timestamp, source="paper-candle", last=candle.close
        )
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return PaperDataGateDecision(False, ("CANDLE_NORMALIZATION_INVALID",))
    return evaluate_paper_quote(
        quote, now=now, expected_symbol=expected_symbol,
        max_age_seconds=max_age_seconds,
    )
