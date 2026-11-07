"""
====================================================

QuantEngine

Feature Evidence -- deterministic indicators (Phase 9F)

Small, deterministic, decision-time indicator helpers used ONLY
inside a CausalWindow (bounded lookback, no lookahead). They are
pure functions over bounded price/volume sequences; they never use
data at or after the decision bar, never fit models, and never
fabricate values when a series is too short or data is missing.

Implemented indicators: ATR, SMA, EMA, rolling volatility (std),
Bollinger percentile/position, and On-Balance-Volume. OBV and any
indicator that decomposes to `None`/`UNAVAILABLE` when the required
data is absent.
====================================================
"""

import math

UNAVAILABLE = None


def _clean(seq):
    return [float(x) for x in seq if x is not None]


def atr(highs, lows, closes, period=14):
    """Wilder's ATR over a bounded series. Returns UNAVAILABLE when
    fewer than `period` ranges are available (data-gated; never
    fabricates from an undersized window)."""
    h = _clean(highs)
    l = _clean(lows)
    c = _clean(closes)
    if not h or not l or not c:
        return UNAVAILABLE
    n = min(len(h), len(l), len(c))
    if n < period + 1:
        return UNAVAILABLE
    trs = []
    for i in range(1, n):
        tr = max(
            h[i] - l[i],
            abs(h[i] - c[i - 1]),
            abs(l[i] - c[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return UNAVAILABLE
    return (sum(trs[-period:]) / period)


def sma(seq, period):
    data = _clean(seq)
    if len(data) < period:
        return UNAVAILABLE
    return float(sum(data[-period:]) / period)


def ema(seq, period):
    data = _clean(seq)
    if not data or period <= 0:
        return UNAVAILABLE
    if len(data) < period:
        return UNAVAILABLE
    k = 2.0 / (period + 1.0)
    e = data[0]
    for x in data[1:]:
        e = k * x + (1 - k) * e
    return float(e)


def rolling_volatility(seq, period=14):
    """Sample standard deviation over the trailing window."""
    data = _clean(seq)
    if len(data) < period:
        return UNAVAILABLE
    window = data[-period:]
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
    return float(math.sqrt(var) if var >= 0 else 0.0)


def bollinger_position(closes, period=20, k=2.0):
    """Where the latest close sits within its Bollinger band,
    normalised to [-1, +1]; None when the window is too short."""
    data = _clean(closes)
    if len(data) < period:
        return UNAVAILABLE
    window = data[-period:]
    mean = sum(window) / len(window)
    sd = rolling_volatility(window, period)
    if sd is None or sd == 0:
        return UNAVAILABLE
    upper = mean + k * sd
    lower = mean - k * sd
    span = upper - lower
    if span == 0:
        return UNAVAILABLE
    return float((data[-1] - lower) / span * 2.0 - 1.0)


def obv(closes, volumes):
    """On-Balance-Volume over aligned close/volume series (decision
    time only). Returns UNAVAILABLE when volume data is entirely
    absent or misaligned."""
    c = _clean(closes)
    v = [float(x) for x in volumes if x is not None]
    if not c or not v or len(c) != len(v):
        return UNAVAILABLE
    total = 0.0
    for i in range(1, len(c)):
        if c[i] > c[i - 1]:
            total += v[i]
        elif c[i] < c[i - 1]:
            total -= v[i]
    return float(total)