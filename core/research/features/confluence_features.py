"""
====================================================

QuantEngine

Feature Evidence -- confluence feature producers (Phase 9F)

Deterministic, decision-time feature producers that turn a
CausalWindow (+ the opportunity's own levels) into canonical,
human-meaningful confluence / market-structure features. They are
ALL optional and ALL data-gated: when the bounded history is too
short, or the required data stream is absent, a producer returns
UNAVAILABLE (None) rather than inventing a value.

Producers provided in this phase:
   * wyckoff_phase          simplified accumulation / markup /
                            distribution / markdown regime from price
                            structure + range contraction
   * market_structure       higher-high / lower-high / consolidation
                            context formed by the last pivots
   * atr_regime             normalised ATR vs a trailing ATR (regime)
   * bollinger_position     latest close position in its band [-1,1]
   * sma_slope              slope of the close's SMA20 over the window
   * obv_trend              OBV slope sign (UNAVAILABLE without volume)
   * liquidity_sweep        a stop-runoff sweep just before decision
   * fvg_present            fair-value-gap detection over recent bars
   * displacement_strength  strong directional momentum candle(s)
   * order_block            a recent consolidation-break base
   * fibonacci_zone         the 0.382/0.5/0.618 zone the ENTRY sits in
                            (drawn from a decision-time swing)
   * volume_profile         UNAVAILABLE unless order-flow/volume-profile
                            data is supplied (never fabricated)
   * footprint_flow         UNAVAILABLE unless order-flow data is
                            supplied (never fabricated)

Entry / stop / target use the OPPORTUNITY'S OWN decision-time levels
(from the 9A setup), never future levels.
====================================================
"""

UNAVAILABLE = None


def _pivots(window):
    """Deterministic swing high/low detection over the window's closes
    (approximate pivots; bounded, decision-time only)."""
    highs = window.highs()
    lows = window.lows()
    n = len(window.points)
    if n < 5:
        return []
    out = []
    for i in range(2, n - 2):
        if highs[i] == max(highs[i - 2:i + 3]):
            out.append(("H", i, highs[i]))
        elif lows[i] == min(lows[i - 2:i + 3]):
            out.append(("L", i, lows[i]))
    return out


def _last_swing(window):
    """(swing_pivot, price) of the most recent local extreme."""
    pivots = _pivots(window)
    if not pivots:
        return None
    return pivots[-1]


# ------------------------------------------------------------------
# Producers
# ------------------------------------------------------------------


def wyckoff_phase(window):
    """Simplified accumulation / markup / distribution / markdown
    regime from bounded price structure."""
    if not window.ensure_minimum(20):
        return UNAVAILABLE
    closes = window.closes()
    half = len(closes) // 2
    first = sum(closes[:half]) / half
    second = sum(closes[half:]) / len(closes[half:])
    lo = min(window.lows())
    hi = max(window.highs())
    rng = hi - lo
    if rng <= 0:
        return UNAVAILABLE
    spread = closes[-1] - lo
    body_range = (hi - lo) / (lo if lo != 0 else 1.0)
    if second > first and spread > 0.5 * rng:
        return "MARKUP"
    if second < first and spread < 0.5 * rng:
        return "MARKDOWN"
    if body_range < 0.05:
        # narrow-range consolidation -> accumulation or distribution
        return "ACCUMULATION" if spread >= 0.5 * rng else "DISTRIBUTION"
    return "TRANSITION"


def market_structure(window):
    """Higher-high / lower-high / consolidation context from the
    trailing pivot extremes."""
    if not window.ensure_minimum(12):
        return UNAVAILABLE
    pivots = _pivots(window)
    highs = [p[2] for p in pivots if p[0] == "H"]
    lows = [p[2] for p in pivots if p[0] == "L"]
    if len(highs) < 2 and len(lows) < 2:
        return UNAVAILABLE
    if len(highs) >= 2 and highs[-1] > highs[-2]:
        return "HIGHER_HIGH"
    if len(lows) >= 2 and lows[-1] < lows[-2]:
        return "LOWER_LOW"
    return "CONSOLIDATION"


def atr_regime(window, atr_at_decision, period=14):
    """Normalised ATR (recent volatility vs trailing) as a ratio;
    UNAVAILABLE when ATR cannot be computed."""
    if atr_at_decision is None or atr_at_decision <= 0:
        return UNAVAILABLE
    if not window.ensure_minimum(period):
        return UNAVAILABLE
    from core.research.features.indicators import atr
    recent = atr(window.highs(), window.lows(), window.closes(), period=period)
    if recent is None or recent <= 0:
        return UNAVAILABLE
    return round(atr_at_decision / recent, 4)


def bollinger_position(window, period=20):
    if not window.ensure_minimum(period + 1):
        return UNAVAILABLE
    from core.research.features.indicators import bollinger_position as bp
    return bp(window.closes(), period)


def sma_slope(window, period=20):
    """Slope of SMA(period) over the window (percent per bar); None
    when too few bars."""
    if not window.ensure_minimum(period + 1):
        return UNAVAILABLE
    from core.research.features.indicators import sma
    closes = window.closes()
    # decision-time: last full SMA vs the one `period` bars earlier
    recent = sma(closes, period)
    if recent is None:
        return UNAVAILABLE
    earlier = sma(closes[:-period], period) if len(closes) >= 2 * period else \
        sma(closes, period)
    if earlier is None or earlier == 0:
        return UNAVAILABLE
    return round((recent - earlier) / abs(earlier), 6)


def obv_trend(window):
    """Slope sign of OBV (+1 / -1 / 0); UNAVAILABLE without volume."""
    if not window.has_volume() or len(window.volumes()) < 8:
        return UNAVAILABLE
    from core.research.features.indicators import obv
    closes = window.closes()
    vols = window.volumes()
    current = obv(closes, vols)
    if len(closes) < 8:
        return UNAVAILABLE
    past = obv(closes[:-4], vols[:-4]) if len(closes) >= 4 else current
    if past is None or current is None:
        return UNAVAILABLE
    return 1 if current > past else (-1 if current < past else 0)


def liquidity_sweep(window, stop_level, direction, lookback=6):
    """True when the stop side was swept (price spiked through the
    liquidity level and returned) shortly before the decision.
    Stop-side depends on direction (BULLISH: below stop)."""
    if not window.ensure_minimum(lookback):
        return UNAVAILABLE
    lows = window.lows()[-lookback:]
    highs = window.highs()[-lookback:]
    closes = window.closes()[-lookback:]
    if direction == "BULLISH":
        swept = any(low < stop_level for low in lows)
        closed_above = closes[-1] > stop_level
    elif direction == "BEARISH":
        swept = any(high > stop_level for high in highs)
        closed_above = closes[-1] < stop_level
    else:
        return UNAVAILABLE
    return bool(swept and closed_above)


def fvg_present(window, direction):
    """Fair-value gap: a gap between adjacent candle shadows formed in
    the last few bars (measured at decision time)."""
    if not window.ensure_minimum(2):
        return UNAVAILABLE
    pts = window.points
    direction = (direction or "").upper()
    # search adjacent candle pairs, most recent first
    for j in range(len(pts) - 2, 0, -1):
        pregap = pts[j]
        post = pts[j + 1]
        if direction == "BULLISH" and post.low > pregap.high:
            return True
        if direction == "BEARISH" and post.high < pregap.low:
            return True
    return False


def displacement_strength(window, direction):
    """A strong directional momentum candle (large real body relative
    to its range) in the decision-time window."""
    if not window.ensure_minimum(6):
        return UNAVAILABLE
    pts = window.points
    direction = (direction or "").upper()
    for p in reversed(pts[-6:]):
        rng = p.high - p.low
        if rng <= 0:
            continue
        body = (p.close - p.open) if direction == "BULLISH" else (p.open - p.close)
        if body > 0.5 * rng:
            return True
    return False


def order_block(window):
    """A consolidation-break base: a candle whose close breaks the
    range defined by the prior candles. Decision-time only."""
    if not window.ensure_minimum(6):
        return UNAVAILABLE
    pts = window.points
    for i in range(len(pts) - 2, 3, -1):
        base = pts[i - 3:i - 1]
        hi = max(p.high for p in base)
        lo = min(p.low for p in base)
        if pts[i].close > hi or pts[i].close < lo:
            return True
    return False


def fibonacci_zone(window, entry, direction):
    """The 0.382/0.5/0.618 retracement zone (between the two legs of a
    recent swing) containing `entry`; returns the band label, or
    UNAVAILABLE when no swing can be drawn."""
    swing = _last_swing(window)
    if swing is None:
        return UNAVAILABLE
    pivots = _pivots(window)
    if len(pivots) < 2:
        return UNAVAILABLE
    # take the last completed swing leg (prior pivot -> last pivot)
    a = pivots[-2]
    b = pivots[-1]
    x = a[2]
    y = b[2]
    rng = abs(y - x)
    if rng <= 0:
        return UNAVAILABLE
    lo = min(x, y)
    hi = max(x, y)
    z383 = lo + 0.382 * rng
    z618 = lo + 0.618 * rng
    if z383 <= entry <= z618:
        return "FIB_0.382_0.618"
    if z383 <= entry <= lo + 0.5 * rng:
        return "FIB_0.382_0.50"
    return "OUTSIDE"


def volume_profile(window):
    """Volume-profile evidence is only meaningful with an order-flow /
    volume-profile data stream. This producer returns UNAVAILABLE if
    none is provided (it NEVER synthesises a volume profile)."""
    return UNAVAILABLE


def footprint_flow(window):
    """Footprint / order-flow evidence is only meaningful with an
    order-flow data stream. This producer returns UNAVAILABLE if none
    is provided (it NEVER synthesises footprint data)."""
    return UNAVAILABLE


# ------------------------------------------------------------------
# Registry (deterministic order; each is data-gated and optional)
# ------------------------------------------------------------------

ALL_PRODUCERS = (
    wyckoff_phase,
    market_structure,
    atr_regime,
    bollinger_position,
    sma_slope,
    obv_trend,
    liquidity_sweep,
    fvg_present,
    displacement_strength,
    order_block,
    fibonacci_zone,
    volume_profile,
    footprint_flow,
)
