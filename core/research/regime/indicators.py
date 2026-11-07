"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- regime indicators

Pure, deterministic, decision-time regime indicators computed over a
bounded window of candles ENDING AT the opportunity's decision bar
(inclusive) -- never over data at or after the trade's evaluation
horizon (no lookahead).

Every indicator is data-gated: when the window is too short, or the
required data stream is absent, it returns UNAVAILABLE (None) rather
than inventing a label. Thresholds are explicit and fixed so results
are byte-repeatable.

Indicators provided:
   trend_vs_range         TREND / RANGE from slope + span vs ATR
   direction_structure    BULLISH / BEARISH / NEUTRAL from swing
                          high/low progress (HH+HL vs LH+LL)
   volatility_regime      HIGH / NORMAL / LOW from volatility ratio
   atr_regime             EXPANSION / NEUTRAL / CONTRACTION
   displacement_strength  STRONG / NORMAL / ABSENT (real bodies)
   liquidity              SWEEPED / NORMAL (stop-side sweep)
   fvg                    PRESENT / ABSENT (shadow gap)
   order_block            PRESENT / ABSENT (consolidation break)
   wyckoff_phase          ACCUMULATION / MARKUP / DISTRIBUTION /
                          MARKDOWN / TRANSITION (simplified)

A candle is any attribute object exposing .open/.high/.low/.close.
Pure meaning: no production imports, no randomness, no mutation.
====================================================
"""

from core.research.features.indicators import (
    UNAVAILABLE,
    atr as _atr,
    sma as _sma,
    rolling_volatility as _volatility,
)

BULLISH = "BULLISH"
BEARISH = "BEARISH"

TREND = "TREND"
RANGE = "RANGE"

NEUTRAL = "NEUTRAL"
HIGH = "HIGH"
NORMAL = "NORMAL"
LOW = "LOW"
EXPANSION = "EXPANSION"
CONTRACTION = "CONTRACTION"
STRONG = "STRONG"
ABSENT = "ABSENT"
SWEEPED = "SWEEPED"
PRESENT = "PRESENT"
ACCUMULATION = "ACCUMULATION"
MARKUP = "MARKUP"
DISTRIBUTION = "DISTRIBUTION"
MARKDOWN = "MARKDOWN"
TRANSITION = "TRANSITION"


def _window(candles, end_index, lookback):
    candles = list(candles)
    if not candles:
        return ()
    end = int(end_index) if end_index is not None else len(candles) - 1
    end = max(0, min(end, len(candles) - 1))
    start = max(0, end - lookback + 1)
    return tuple(candles[start:end + 1])


def _closes(points):
    return [float(p.close) for p in points]


def _highs(points):
    return [float(p.high) for p in points]


def _lows(points):
    return [float(p.low) for p in points]


def _pivots(points):
    """Deterministic swing high/low detection (bounded, decision-time)."""
    n = len(points)
    if n < 5:
        return []
    highs = _highs(points)
    lows = _lows(points)
    out = []
    for i in range(2, n - 2):
        if highs[i] == max(highs[i - 2:i + 3]):
            out.append(("H", i, highs[i]))
        elif lows[i] == min(lows[i - 2:i + 3]):
            out.append(("L", i, lows[i]))
    return out


# ------------------------------------------------------------------
# Regime indicators
# ------------------------------------------------------------------

def trend_vs_range(points, atr_period=14, trend_period=20):
    """TREND/RANGE from normalised SMA slope + range/ATR span."""
    if len(points) < trend_period + 1:
        return UNAVAILABLE
    highs = _highs(points)
    lows = _lows(points)
    closes = _closes(points)
    atr_v = _atr(highs, lows, closes, atr_period)
    if atr_v is UNAVAILABLE or atr_v <= 0:
        return UNAVAILABLE
    sma_now = _sma(closes, trend_period)
    if len(closes) >= 2 * trend_period:
        sma_then = _sma(closes[:-trend_period], trend_period)
    else:
        sma_then = _sma(closes, trend_period)
    if sma_now is UNAVAILABLE or sma_then is UNAVAILABLE:
        return UNAVAILABLE
    slope_units = (sma_now - sma_then) / atr_v
    span_ratio = (max(highs) - min(lows)) / atr_v
    if abs(slope_units) >= 0.5 or span_ratio >= 8.0:
        return TREND
    return RANGE


def direction_structure(points, pivot_pattern=3):
    """BULLISH (higher-highs + higher-lows) / BEARISH (lower-highs +
    lower-lows) / NEUTRAL from the trailing pivot extremes."""
    if len(points) < 12:
        return UNAVAILABLE
    pivots = _pivots(points)
    highs = [p[2] for p in pivots if p[0] == "H"]
    lows = [p[2] for p in pivots if p[0] == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return UNAVAILABLE
    hh = highs[-1] > highs[-2]
    hl = lows[-1] >= lows[-2]
    lh = highs[-1] <= highs[-2]
    ll = lows[-1] < lows[-2]
    if hh and hl:
        return BULLISH
    if lh and ll:
        return BEARISH
    return NEUTRAL


def volatility_regime(points, period=14):
    """HIGH/NORMAL/LOW from the recent-vs-older volatility ratio."""
    if len(points) < 2 * period + 4:
        return UNAVAILABLE
    closes = _closes(points)
    recent = _volatility(closes[-period:], period)
    older = _volatility(closes[-2 * period:-period], period)
    if recent is UNAVAILABLE or older is UNAVAILABLE or older <= 0:
        return UNAVAILABLE
    ratio = recent / older
    if ratio >= 1.3:
        return HIGH
    if ratio <= 0.7:
        return LOW
    return NORMAL


def atr_regime(points, atr_period=14):
    """EXPANSION / NEUTRAL / CONTRACTION from recent vs older ATR."""
    need = 2 * atr_period + 2
    if len(points) < need:
        return UNAVAILABLE
    highs = _highs(points)
    lows = _lows(points)
    closes = _closes(points)
    recent = _atr(highs[-(atr_period + 1):], lows[-(atr_period + 1):],
                  closes[-(atr_period + 1):], atr_period)
    older = _atr(highs[-(2 * atr_period + 2):-(atr_period + 1)],
                 lows[-(2 * atr_period + 2):-(atr_period + 1)],
                 closes[-(2 * atr_period + 2):-(atr_period + 1)],
                 atr_period)
    if recent is UNAVAILABLE or older is UNAVAILABLE or older <= 0:
        return UNAVAILABLE
    ratio = recent / older
    if ratio >= 1.2:
        return EXPANSION
    if ratio <= 0.8:
        return CONTRACTION
    return NEUTRAL


def displacement_strength(points, direction, window=6):
    """STRONG when a real-body impulse candle sits in the window;
    ABSENT otherwise; UNAVAILABLE without a valid direction."""
    if len(points) < 2:
        return UNAVAILABLE
    direction = (direction or "").upper()
    if direction not in (BULLISH, BEARISH):
        return UNAVAILABLE
    for p in reversed(points[-window:]):
        rng = p.high - p.low
        if rng <= 0:
            continue
        body = (p.close - p.open) if direction == BULLISH else (p.open - p.close)
        if body > 0.5 * rng:
            return STRONG
    return ABSENT


def liquidity(points, direction, stop_level, lookback=6):
    """SWEEPED when the stop side got swept and price reclaimed it;
    NORMAL otherwise; UNAVAILABLE without a stop level."""
    direction = (direction or "").upper()
    if stop_level is None or direction not in (BULLISH, BEARISH):
        return UNAVAILABLE
    if len(points) < lookback:
        return UNAVAILABLE
    lows = [float(p.low) for p in points[-lookback:]]
    highs = [float(p.high) for p in points[-lookback:]]
    closes = [float(p.close) for p in points[-lookback:]]
    if direction == BULLISH:
        swept = any(low < float(stop_level) for low in lows)
        reclaimed = closes[-1] > float(stop_level)
    else:
        swept = any(high > float(stop_level) for high in highs)
        reclaimed = closes[-1] < float(stop_level)
    if swept and reclaimed:
        return SWEEPED
    return NORMAL


def fvg(points, direction):
    """PRESENT when a fair-value gap (shadow gap) formed recently;
    ABSENT when the window has none; UNAVAILABLE when too short."""
    if len(points) < 3:
        return UNAVAILABLE
    direction = (direction or "").upper()
    if direction not in (BULLISH, BEARISH):
        return UNAVAILABLE
    for j in range(len(points) - 2, 0, -1):
        pre = points[j]
        post = points[j + 1]
        if direction == BULLISH and post.low > pre.high:
            return PRESENT
        if direction == BEARISH and post.high < pre.low:
            return PRESENT
    return ABSENT


def order_block(points):
    """PRESENT when a candle broke out of a recent consolidation base."""
    if len(points) < 6:
        return UNAVAILABLE
    for i in range(len(points) - 2, 3, -1):
        base = points[i - 3:i - 1]
        hi = max(p.high for p in base)
        lo = min(p.low for p in base)
        if points[i].close > hi or points[i].close < lo:
            return PRESENT
    return ABSENT


def wyckoff_phase(points, period=20):
    """Simplified accumulation / markup / distribution / markdown /
    transition from bounded price structure."""
    if len(points) < 2 * period:
        return UNAVAILABLE
    closes = _closes(points)
    half = len(closes) // 2
    first = sum(closes[:half]) / half
    second = sum(closes[half:]) / len(closes[half:])
    lo = min(_lows(points))
    hi = max(_highs(points))
    rng = hi - lo
    if rng <= 0:
        return UNAVAILABLE
    spread = closes[-1] - lo
    body_range = (hi - lo) / (lo if lo != 0 else 1.0)
    if second > first and spread > 0.5 * rng:
        return MARKUP
    if second < first and spread < 0.5 * rng:
        return MARKDOWN
    if body_range < 0.05:
        return ACCUMULATION if spread >= 0.5 * rng else DISTRIBUTION
    return TRANSITION