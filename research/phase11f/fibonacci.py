"""Phase 11F-1 causal Fibonacci features (research-only, no strategy).

Structural retracements/extensions computed ONLY from previously
CONFIRMED fractal swings. A swing extreme at bar e with confirmation
lag R is usable only at bars >= e+R; Fibonacci levels at decision
bar T therefore depend only on bars[0..T].

Pre-registered frozen ratio sets (standard structural relationships,
never optimized):

  RETRACE  = 0.382 / 0.50 / 0.618 / 0.786
  EXTENSION = 1.272 / 1.618

Anchor rule (deterministic): as of bar i, take the most recent
confirmed swing low and most recent confirmed swing high with
confirmed_index <= i. If both exist:
  - high confirmed after low confirmed  -> bullish impulse (low->high);
    retracement levels hang below the high.
  - low confirmed after high confirmed  -> bearish impulse (high->low);
    retracement levels hang above the low.
If only one side is confirmed, no levels exist at i (None/empty).

Causal timestamp of every level = max(low_confirmed, high_confirmed).
Levels are never back-dated to the formation bar.

Invalidation: a bullish-impulse retracement is invalidated once a
close prints below the impulse low; a bearish one once a close
prints above the impulse high. Invalidation is reported as a
boolean evaluated causally (close[i] vs anchors confirmed <= i).

No order-flow/footprint input. OHLC only. No strategy is defined
here — feature infrastructure only.
"""

from __future__ import annotations

from research.phase11f import features as F

FIB_RETRACE_RATIOS = (0.382, 0.5, 0.618, 0.786)
FIB_EXTENSION_RATIOS = (1.272, 1.618)


def _last_confirmed(swings, kind, upto):
    """Most recent confirmed swing of kind with confirmed_index <= upto."""
    best = None
    for idx in range(upto + 1):
        s = swings[idx]
        if s is not None and s["kind"] == kind:
            best = s
    return best


def fib_retracements(bars, left=3, right=3, ratios=FIB_RETRACE_RATIOS):
    """Per-bar Fibonacci retracement levels (causal).

    Returns a list aligned to bars; each entry is [] (no confirmed
    pair yet) or a list of level dicts with keys:
      direction, ratio, level, anchor_low, anchor_high,
      anchor_low_index, anchor_high_index,
      anchor_low_confirmed, anchor_high_confirmed,
      confirmed_index, invalidated
    """
    if tuple(ratios) != tuple(FIB_RETRACE_RATIOS):
        raise ValueError("Fibonacci ratios are frozen; no optimization")
    swings = F.swings(bars, left, right)
    closes = [float(b["close"]) for b in bars]
    n = len(bars)
    out: list = [[] for _ in range(n)]
    for i in range(n):
        lo = _last_confirmed(swings, "low", i)
        hi = _last_confirmed(swings, "high", i)
        if lo is None or hi is None:
            continue
        confirmed = max(lo["confirmed_index"], hi["confirmed_index"])
        # Both confirmations must be <= i by construction of the
        # lookup above; keep the guard explicit for auditability.
        if confirmed > i:
            continue
        low, high = float(lo["extreme"]), float(hi["extreme"])
        if high <= low:
            continue
        if hi["confirmed_index"] >= lo["confirmed_index"]:
            direction = "bullish"
            invalidated = bool(closes[i] < low)
            levels = [
                {"direction": direction, "ratio": r,
                 "level": high - r * (high - low),
                 "anchor_low": low, "anchor_high": high,
                 "anchor_low_index": lo["extreme_index"],
                 "anchor_high_index": hi["extreme_index"],
                 "anchor_low_confirmed": lo["confirmed_index"],
                 "anchor_high_confirmed": hi["confirmed_index"],
                 "confirmed_index": confirmed,
                 "invalidated": invalidated}
                for r in ratios
            ]
        else:
            direction = "bearish"
            invalidated = bool(closes[i] > high)
            levels = [
                {"direction": direction, "ratio": r,
                 "level": low + r * (high - low),
                 "anchor_low": low, "anchor_high": high,
                 "anchor_low_index": lo["extreme_index"],
                 "anchor_high_index": hi["extreme_index"],
                 "anchor_low_confirmed": lo["confirmed_index"],
                 "anchor_high_confirmed": hi["confirmed_index"],
                 "confirmed_index": confirmed,
                 "invalidated": invalidated}
                for r in ratios
            ]
        out[i] = levels
    return out


def fib_extensions(bars, left=3, right=3, ratios=FIB_EXTENSION_RATIOS):
    """Per-bar Fibonacci extension levels (causal, same anchors)."""
    if tuple(ratios) != tuple(FIB_EXTENSION_RATIOS):
        raise ValueError("Fibonacci ratios are frozen; no optimization")
    swings = F.swings(bars, left, right)
    closes = [float(b["close"]) for b in bars]
    n = len(bars)
    out: list = [[] for _ in range(n)]
    for i in range(n):
        lo = _last_confirmed(swings, "low", i)
        hi = _last_confirmed(swings, "high", i)
        if lo is None or hi is None:
            continue
        confirmed = max(lo["confirmed_index"], hi["confirmed_index"])
        if confirmed > i:
            continue
        low, high = float(lo["extreme"]), float(hi["extreme"])
        span = high - low
        if span <= 0:
            continue
        if hi["confirmed_index"] >= lo["confirmed_index"]:
            direction = "bullish"
            invalidated = bool(closes[i] < low)
            levels = [
                {"direction": direction, "ratio": r,
                 "level": high + (r - 1.0) * span,
                 "anchor_low": low, "anchor_high": high,
                 "anchor_low_index": lo["extreme_index"],
                 "anchor_high_index": hi["extreme_index"],
                 "anchor_low_confirmed": lo["confirmed_index"],
                 "anchor_high_confirmed": hi["confirmed_index"],
                 "confirmed_index": confirmed,
                 "invalidated": invalidated}
                for r in ratios
            ]
        else:
            direction = "bearish"
            invalidated = bool(closes[i] > high)
            levels = [
                {"direction": direction, "ratio": r,
                 "level": low - (r - 1.0) * span,
                 "anchor_low": low, "anchor_high": high,
                 "anchor_low_index": lo["extreme_index"],
                 "anchor_high_index": hi["extreme_index"],
                 "anchor_low_confirmed": lo["confirmed_index"],
                 "anchor_high_confirmed": hi["confirmed_index"],
                 "confirmed_index": confirmed,
                 "invalidated": invalidated}
                for r in ratios
            ]
        out[i] = levels
    return out
