"""11G-A Wyckoff event engine (REAL, OHLCV; deterministic subset).

Machine-testable events ONLY: SPRING, UPTHRUST, SECONDARY_TEST,
SIGN_OF_STRENGTH. Each event carries context/trigger/confirmation/
availability/invalidation — availability is the confirmation bar,
never the formation bar (no retrospective recognition). These are
EVENTS, not trades. Definitions frozen here; no performance tuning.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def prior_range_state(bars, period=50, min_hold=30):
    """Range boundaries over STRICTLY PRIOR bars (exclusive of bar i).

    Rationale: a Donchian window including bar i can never be swept by
    bar i (its own extreme defines the boundary). Trading ranges are
    therefore evaluated on bars[..i-1]; the spring/upthrust bar is
    tested against the confirmed prior range. Each entry is None or
    {"high","low","hold"} knowable at bar i.
    """
    hi, lo = F11.donchian(bars, period)
    n = len(bars)
    out = [None] * n
    last_change = None
    prev = (None, None)
    # ref[i] = Donchian pair as of bar i-1 (None for i == 0).
    ref = [(None, None)] + [(hi[i - 1], lo[i - 1]) for i in range(1, n)]
    for i in range(n):
        pair = ref[i]
        if pair[0] is None:
            continue
        if prev != pair:
            last_change = i
            prev = pair
        hold = i - last_change
        if hold >= min_hold:
            out[i] = {"high": pair[0], "low": pair[1], "hold": hold}
    return out


def springs(bars, range_lookback=50, min_hold=30):
    """Range spring: wick below the CONFIRMED PRIOR range low + reclaim
    close back inside the range."""
    rng = prior_range_state(bars, range_lookback, min_hold)
    lo, cl = C.lows(bars), C.closes(bars)
    out = []
    for i in range(len(bars)):
        r = rng[i]
        if r is None:
            out.append(C.empty("wyckoff_spring", i, bars, "11g.wyckoff",
                               reason="NO_EVENT"))
            continue
        if lo[i] < r["low"] and cl[i] > r["low"] and r["high"] > cl[i]:
            out.append(C.event(
                "wyckoff_spring",
                {"range_high": r["high"], "range_low": r["low"],
                 "spring_low": lo[i],
                 "invalidation": "close back below range low"},
                i, bars, "11g.wyckoff", formation=i, confirmation=i,
                metadata={"event": "SPRING"}))
        else:
            out.append(C.empty("wyckoff_spring", i, bars, "11g.wyckoff",
                               reason="NO_EVENT"))
    return out


def upthrusts(bars, range_lookback=50, min_hold=30):
    """Mirror of springs above the CONFIRMED PRIOR range high."""
    rng = prior_range_state(bars, range_lookback, min_hold)
    hi, cl = C.highs(bars), C.closes(bars)
    out = []
    for i in range(len(bars)):
        r = rng[i]
        if r is None:
            out.append(C.empty("wyckoff_upthrust", i, bars, "11g.wyckoff",
                               reason="NO_EVENT"))
            continue
        if hi[i] > r["high"] and cl[i] < r["high"] and r["low"] < cl[i]:
            out.append(C.event(
                "wyckoff_upthrust",
                {"range_high": r["high"], "range_low": r["low"],
                 "upthrust_high": hi[i],
                 "invalidation": "close back above range high"},
                i, bars, "11g.wyckoff", formation=i, confirmation=i,
                metadata={"event": "UPTHRUST"}))
        else:
            out.append(C.empty("wyckoff_upthrust", i, bars, "11g.wyckoff",
                               reason="NO_EVENT"))
    return out


def secondary_tests(bars, range_lookback=50, min_hold=30, max_wait=30,
                    tolerance_atr=0.5):
    """SECONDARY_TEST: after a spring at bar s (low L), a later bar
    within max_wait dips to [L, L+tol*ATR] and closes back above L
    (demand holds). Availability = test bar. Past-only scan."""
    spr = springs(bars, range_lookback, min_hold)
    atr = F11.atr14(bars)
    lo, cl = C.lows(bars), C.closes(bars)
    out = [C.empty("wyckoff_secondary_test", i, bars, "11g.wyckoff",
                   reason="NO_EVENT") for i in range(len(bars))]
    sprung = []  # (spring_index, spring_low)
    for i in range(len(bars)):
        if spr[i]["status"] == "OK":
            sprung.append((i, spr[i]["value"]["spring_low"]))
        if atr[i] is None:
            continue
        tol = tolerance_atr * atr[i]
        for (s, low) in sprung:
            if i <= s or i - s > max_wait:
                continue
            if low <= lo[i] <= low + tol and cl[i] > low:
                out[i] = C.event(
                    "wyckoff_secondary_test",
                    {"spring_index": s, "spring_low": low,
                     "test_low": lo[i],
                     "invalidation": "close below spring low"},
                    i, bars, "11g.wyckoff", formation=s, confirmation=i,
                    metadata={"event": "SECONDARY_TEST"})
                break
    return out


def signs_of_strength(bars, range_lookback=50, min_hold=30,
                      displacement_mult=2.0):
    """SIGN_OF_STRENGTH: prior-range-high break with displacement close
    above the range high. Availability = displacement bar."""
    rng = prior_range_state(bars, range_lookback, min_hold)
    atr = F11.atr14(bars)
    disp = F11.displacement(bars, displacement_mult, atr)
    cl = C.closes(bars)
    out = []
    for i in range(len(bars)):
        r = rng[i]
        if r is None or atr[i] is None or not disp[i]:
            out.append(C.empty("wyckoff_sos", i, bars, "11g.wyckoff",
                               reason="NO_EVENT"))
            continue
        if cl[i] > r["high"]:
            out.append(C.event(
                "wyckoff_sos",
                {"range_high": r["high"], "range_low": r["low"],
                 "invalidation": "close back inside range"},
                i, bars, "11g.wyckoff", formation=i, confirmation=i,
                metadata={"event": "SIGN_OF_STRENGTH"}))
        else:
            out.append(C.empty("wyckoff_sos", i, bars, "11g.wyckoff",
                               reason="NO_EVENT"))
    return out
