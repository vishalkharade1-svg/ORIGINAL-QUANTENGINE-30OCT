"""
====================================================

Institutional Candle

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class Candle:

    timestamp: int

    open: float

    high: float

    low: float

    close: float

    volume: float

    # FORMING vs CLOSED provenance (Phase 6D). Backtest candles are
    # always closed (default True). Live feeds mark the still-forming
    # candle closed=False; the strategy layer only ever consumes
    # closed candles so BREAKOUT triggers stay causally aligned to
    # NEXT_BAR_OPEN.
    closed: bool = True

    # Symbol provenance (Phase 6D). Backtest candles leave this as
    # the default "" (the backtester carries symbol on the market).
    # Live subscriptions tag each candle so a multiplexed transport
    # can be sanity-scoped per worker.
    symbol: str = ""