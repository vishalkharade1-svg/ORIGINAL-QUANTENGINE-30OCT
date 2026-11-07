"""Phase 11F causal research features (research-only).

Every function maps chronological bar dicts
(time/open/high/low/close/volume) to per-bar arrays where
value[i] depends ONLY on bars[0..i]. Confirmation lags are
explicit (a swing extreme at bar e confirmed at bar e+R is
visible to candidates only at index >= e+R).

Conventions:
  None   = insufficient history / no event at this bar.
  Levels are floats; directions are "long"/"short".
  PROXY_FEATURE: volume-based aggregates (no bid/ask split
    exists in the 1m schema). DATA_UNAVAILABLE: true
  footprint/delta series (orderflow_available() is False).
"""

import math


def _f(bars, key):
    return [float(b[key]) for b in bars]


def atr14(bars):
    """Wilder ATR(14); out[14] seeded from TR[1..14]."""
    highs, lows, closes = _f(bars, "high"), _f(bars, "low"), _f(bars, "close")
    n = len(bars)
    out = [None] * n
    if n < 15:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    prev = sum(trs[1:15]) / 14.0
    out[14] = prev
    for i in range(15, n):
        prev = (prev * 13.0 + trs[i]) / 14.0
        out[i] = prev
    return out


def rsi14(bars):
    """Wilder RSI(14); flat market yields 50.0 (defined convention)."""
    closes = _f(bars, "close")
    n = len(bars)
    out = [None] * n
    if n < 15:
        return out
    gains, losses = [], []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_g = sum(gains[:14]) / 14.0
    avg_l = sum(losses[:14]) / 14.0
    out[14] = 50.0 if (avg_g == 0 and avg_l == 0) else (
        100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l))
    for i in range(15, n):
        avg_g = (avg_g * 13.0 + gains[i - 1]) / 14.0
        avg_l = (avg_l * 13.0 + losses[i - 1]) / 14.0
        out[i] = 50.0 if (avg_g == 0 and avg_l == 0) else (
            100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l))
    return out


def ema(values, period):
    """Causal EMA seeded with SMA(first period). None until seeded."""
    n = len(values)
    out = [None] * n
    if n < period or period < 1:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = (values[i] - prev) * k + prev
        out[i] = prev
    return out


def sma(values, period):
    n = len(values)
    out = [None] * n
    if n < period or period < 1:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, n):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def donchian(bars, period):
    """(highest-high, lowest-low) of bars[i-period+1..i]."""
    highs, lows = _f(bars, "high"), _f(bars, "low")
    n = len(bars)
    hi, lo = [None] * n, [None] * n
    for i in range(n):
        if i + 1 >= period:
            window_h = highs[i - period + 1:i + 1]
            window_l = lows[i - period + 1:i + 1]
            hi[i] = max(window_h)
            lo[i] = min(window_l)
    return hi, lo


def swings(bars, left=3, right=3):
    """Fractal swings. Returns list aligned to bars: each entry is
    None or {"kind": "high"/"low", "extreme": float,
    "extreme_index": int, "confirmed_index": int}.
    The extreme at bar e is published at index e+right (causal)."""
    highs, lows = _f(bars, "high"), _f(bars, "low")
    n = len(bars)
    out = [None] * n
    for e in range(left, n - right):
        is_high = all(highs[e] >= highs[e - k] for k in range(1, left + 1)) and \
            all(highs[e] > highs[e + k] for k in range(1, right + 1))
        is_low = all(lows[e] <= lows[e - k] for k in range(1, left + 1)) and \
            all(lows[e] < lows[e + k] for k in range(1, right + 1))
        if is_high:
            out[e + right] = {"kind": "high", "extreme": highs[e],
                              "extreme_index": e, "confirmed_index": e + right}
        elif is_low:
            out[e + right] = {"kind": "low", "extreme": lows[e],
                              "extreme_index": e, "confirmed_index": e + right}
    return out


def equal_levels(bars, lookback=50, tolerance_atr=0.1, atr=None):
    """Equal highs/lows: >=3 swing touches within tolerance over the
    lookback. Returns per-bar list of levels active at bar i, each
    {"kind", "level", "touches", "extreme_index"}. Uses confirmed
    swings only (causal)."""
    if atr is None:
        atr = atr14(bars)
    sw = swings(bars)
    n = len(bars)
    out = [[] for _ in range(n)]
    for i in range(n):
        if atr[i] is None:
            continue
        tol = tolerance_atr * atr[i]
        recent = []
        for j in range(max(0, i - lookback), i + 1):
            if sw[j] is not None:
                recent.append(sw[j])
        groups = []
        for s in recent:
            placed = False
            for g in groups:
                if g["kind"] == s["kind"] and abs(g["level"] - s["extreme"]) <= tol:
                    g["touches"] += 1
                    g["level"] = s["extreme"]
                    g["extreme_index"] = s["extreme_index"]
                    placed = True
                    break
            if not placed:
                groups.append({"kind": s["kind"], "level": s["extreme"],
                               "touches": 1, "extreme_index": s["extreme_index"]})
        out[i] = [g for g in groups if g["touches"] >= 3]
    return out


def sweeps(bars, lookback=50, tolerance_atr=0.1, atr=None):
    """Sweep + reclaim at bar i: wick beyond an equal level, close
    back inside. Returns None or {"direction", "level", "extreme"}.
    direction "long" = swept lows, reclaimed up."""
    if atr is None:
        atr = atr14(bars)
    highs, lows, closes = _f(bars, "high"), _f(bars, "low"), _f(bars, "close")
    levels = equal_levels(bars, lookback, tolerance_atr, atr)
    n = len(bars)
    out = [None] * n
    for i in range(n):
        if atr[i] is None:
            continue
        tol = tolerance_atr * atr[i]
        for lv in levels[i]:
            if lv["kind"] == "low" and lows[i] < lv["level"] - tol \
                    and closes[i] > lv["level"]:
                out[i] = {"direction": "long", "level": lv["level"],
                          "extreme": lows[i]}
                break
            if lv["kind"] == "high" and highs[i] > lv["level"] + tol \
                    and closes[i] < lv["level"]:
                out[i] = {"direction": "short", "level": lv["level"],
                          "extreme": highs[i]}
                break
    return out


def displacement(bars, mult=2.0, atr=None):
    """True when bar range exceeds mult * ATR14. Causal."""
    if atr is None:
        atr = atr14(bars)
    highs, lows = _f(bars, "high"), _f(bars, "low")
    return [(a is not None and (h - l) > mult * a)
            for a, h, l in zip(atr, highs, lows)]


def fvg_zones(bars):
    """Bullish/bearish fair value gaps. Entry per bar: None or
    {"direction", "top", "bottom", "origin_index"}. A gap at bar i
    uses bars[i-2..i] only. Mitigation state is tracked by the
    candidate/simulator, not here."""
    highs, lows, closes = _f(bars, "high"), _f(bars, "low"), _f(bars, "close")
    n = len(bars)
    out = [None] * n
    for i in range(2, n):
        if lows[i] > highs[i - 2] and closes[i] > closes[i - 1]:
            out[i] = {"direction": "long", "top": lows[i],
                      "bottom": highs[i - 2], "origin_index": i}
        elif highs[i] < lows[i - 2] and closes[i] < closes[i - 1]:
            out[i] = {"direction": "short", "top": lows[i - 2],
                      "bottom": highs[i], "origin_index": i}
    return out


def order_block_before(bars, index, direction):
    """Last opposite-range candle before bar `index` (exclusive),
    used as the OB reference. Returns None or
    {"extreme", "edge", "index"}. Pure past lookup."""
    opens, highs, lows, closes = (_f(bars, "open"), _f(bars, "high"),
                                  _f(bars, "low"), _f(bars, "close"))
    for j in range(index - 1, -1, -1):
        body_up = closes[j] >= opens[j]
        if direction == "long" and not body_up:
            return {"extreme": lows[j], "edge": highs[j], "index": j}
        if direction == "short" and body_up:
            return {"extreme": highs[j], "edge": lows[j], "index": j}
    return None


def range_state(bars, period=50, min_hold=30):
    """Donchian range + hold counter. Entry: None until the range
    high/low pair is unchanged for min_hold bars, else
    {"high", "low", "hold"}. Causal."""
    hi, lo = donchian(bars, period)
    n = len(bars)
    out = [None] * n
    last_change = None
    prev = (None, None)
    for i in range(n):
        if hi[i] is None:
            continue
        if prev != (hi[i], lo[i]):
            last_change = i
            prev = (hi[i], lo[i])
        hold = i - last_change
        if hold >= min_hold:
            out[i] = {"high": hi[i], "low": lo[i], "hold": hold}
    return out


def rvol_proxy(bars, period=20):
    """PROXY_FEATURE: volume / SMA(volume). No bid/ask split exists."""
    vols = _f(bars, "volume")
    base = sma(vols, period)
    return [(v / b if b else None) for v, b in zip(vols, base)]


def orderflow_available():
    """False: the 1m schema carries total volume only."""
    return False


def finite_guard(values):
    """True iff every value is a finite number."""
    return all(v is not None and math.isfinite(v) for v in values)
