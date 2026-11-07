"""
====================================================

QuantEngine

Research Lab -- entry models (Phase 9B)

Deterministic, purely causal entry-execution semantics for the
experiment lab. Given the candles AFTER the historical decision
bar (decision+1 .. end), these functions decide whether and where
an experimental entry would have filled.

NEVER leak future information: a fill at index i is decided only
from candles at or before i (the same causal ordering the real
backtester uses -- the trigger candle is observed first, the fill
happens at the NEXT bar open).

These are EXPERIMENT semantics, not production. They never touch
the production entry model.
====================================================
"""

LONG = "BULLISH"
SHORT = "BEARISH"

REASON_LIMIT_FILL = "LIMIT_FILL"
REASON_BREAKOUT_FILL = "BREAKOUT_FILL"
REASON_MARKET_FILL = "MARKET_FILL"
REASON_NO_UNIT = "NO_EXECUTABLE_BAR"


def _crossed(candle, level, direction):
    """Did `candle` close strictly beyond `level` in `direction`?"""
    if direction == LONG:
        return candle.close > level
    return candle.close < level


def _in_range(candle, lo, hi):
    return candle.low <= hi and candle.high >= lo


def _window_end(candles, start, expiry):
    if expiry is None:
        return len(candles) - 1
    return min(len(candles) - 1, start + int(expiry) - 1)


def _next_open(candles, index):
    if index >= len(candles):
        return None
    return float(candles[index].open)


def _atr_at_decision(candles, decision_bar, period=14):
    """ATR computed from bars UP TO AND INCLUDING the decision
    bar. Reuses the existing core ATR indicator; never looks past
    the decision point (no lookahead)."""
    from core.indicators.atr import ATR

    window = candles[: decision_bar + 1]
    if len(window) < 2:
        return 0.0
    atr = ATR(period=period)
    atr.calculate(window)
    return float(atr.latest() or 0.0)


class EntryModels:
    """Pure, causal experimental entry functions. Each returns
    (fill_index, fill_price, reason). fill_index/fill_price are
    None when no executable entry was found in the window."""

    @staticmethod
    def limit_retest(candles, decision_bar, config, direction,
                     entry_price, expiry=None):
        """LIMIT: fill when a bar's range trades through the limit
        level (within retest_tolerance). The fill price is the
        limit level (the resting limit)."""
        start = decision_bar + 1
        end = _window_end(candles, start, expiry)
        tolerance = config.retest_tolerance
        lo = entry_price - tolerance
        hi = entry_price + tolerance
        for i in range(start, end + 1):
            c = candles[i]
            if _in_range(c, lo, hi):
                return i, float(entry_price), REASON_LIMIT_FILL
        return None, None, REASON_NO_UNIT

    @staticmethod
    def breakout_continuation(candles, decision_bar, config, direction,
                              entry_price, expiry=None):
        """BREAKOUT: when a bar closes beyond the trigger level
        (entry + breakout_buffer), fill at the NEXT bar open."""
        trigger = entry_price
        buffer = config.breakout_buffer
        level = trigger + buffer if direction == LONG else trigger - buffer
        start = decision_bar + 1
        end = _window_end(candles, start, expiry)
        for i in range(start, end):
            c = candles[i]
            if _crossed(c, level, direction):
                nxt = i + 1
                fill = _next_open(candles, nxt)
                if fill is None:
                    return None, None, REASON_NO_UNIT
                return nxt, fill, REASON_BREAKOUT_FILL
        return None, None, REASON_NO_UNIT

    @staticmethod
    def market_confirmation(candles, decision_bar, config, direction,
                            entry_price, expiry=None):
        """MARKET_CONFIRMATION: a bar closes beyond the
        confirmation-distance level, then fill at the next open."""
        conf = config.confirmation_distance
        level = (
            entry_price + conf
            if direction == LONG
            else entry_price - conf
        )
        start = decision_bar + 1
        end = _window_end(candles, start, expiry)
        for i in range(start, end):
            c = candles[i]
            if _crossed(c, level, direction):
                nxt = i + 1
                fill = _next_open(candles, nxt)
                if fill is None:
                    return None, None, REASON_NO_UNIT
                return nxt, fill, REASON_MARKET_FILL
        return None, None, REASON_NO_UNIT
