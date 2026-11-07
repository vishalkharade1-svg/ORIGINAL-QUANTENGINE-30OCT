"""11G-A market-structure adapter (REAL, OHLCV).

Thin causal layer over certified 11F primitives (swings, donchian,
range_state, ema). Adds HH/HL/LH/LL trend derivation, BOS and
CHOCH/MSS events from CONFIRMED swings only. Every event carries
formation (extreme bar) / confirmation (confirmation bar) /
availability (== confirmation, never back-dated) timestamps.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def swing_series(bars, left=3, right=3):
    """Confirmed swing at each bar: None or event (availability = confirmation)."""
    out = []
    for s in F11.swings(bars, left, right):
        if s is None:
            out.append(C.empty("swing", 0, bars, "phase11f.swings",
                               reason="NO_EVENT"))
            continue
        i = s["confirmed_index"]
        out.append(C.event("swing", {"kind": s["kind"], "extreme": s["extreme"],
                                     "extreme_index": s["extreme_index"]},
                           i, bars, "phase11f.swings",
                           formation=s["extreme_index"], confirmation=i))
    return out


def _confirmed_extremes(bars, left=3, right=3):
    seq = []
    for s in F11.swings(bars, left, right):
        if s is not None:
            seq.append(s)
    return seq


def trend_state(bars, left=3, right=3):
    """HH/HL/LH/LL regime from the last two confirmed swing pairs.

    UPTREND: last two highs rising AND last two lows rising.
    DOWNTREND: both falling. Otherwise RANGE. Single pass: only swings
    with confirmed_index <= i participate at bar i.
    """
    sw = F11.swings(bars, left, right)
    out = []
    highs, lows = [], []
    for i in range(len(bars)):
        if sw[i] is not None:
            (highs if sw[i]["kind"] == "high" else lows).append(sw[i])
        if len(highs) < 2 or len(lows) < 2:
            out.append(C.empty("trend_state", i, bars, "11g.structure",
                               reason="INSUFFICIENT_HISTORY"))
            continue
        h, l = highs[-2:], lows[-2:]
        up = h[1]["extreme"] > h[0]["extreme"] and l[1]["extreme"] > l[0]["extreme"]
        dn = h[1]["extreme"] < h[0]["extreme"] and l[1]["extreme"] < l[0]["extreme"]
        state = "UPTREND" if up else ("DOWNTREND" if dn else "RANGE")
        out.append(C.event("trend_state", state, i, bars, "11g.structure",
                           formation=i, confirmation=i,
                           metadata={"hh": h[1]["extreme"], "prev_hh": h[0]["extreme"],
                                     "hl": l[1]["extreme"], "prev_hl": l[0]["extreme"]}))
    return out


def bos_events(bars, left=3, right=3):
    """Break-of-structure: close beyond the most recently confirmed
    opposite swing extreme. Availability = break bar."""
    seq = _confirmed_extremes(bars, left, right)
    cl = C.closes(bars)
    out = [C.empty("bos", i, bars, "11g.structure", reason="NO_EVENT")
           for i in range(len(bars))]
    last_high = last_low = None
    for i in range(len(bars)):
        for s in seq:
            if s["confirmed_index"] == i:
                if s["kind"] == "high":
                    last_high = s["extreme"]
                else:
                    last_low = s["extreme"]
        if i > 0 and last_high is not None and cl[i - 1] <= last_high < cl[i]:
            out[i] = C.event("bos", {"direction": "BULLISH", "level": last_high},
                             i, bars, "11g.structure", formation=i, confirmation=i)
        elif i > 0 and last_low is not None and cl[i - 1] >= last_low > cl[i]:
            out[i] = C.event("bos", {"direction": "BEARISH", "level": last_low},
                             i, bars, "11g.structure", formation=i, confirmation=i)
    return out


def choch_events(bars, left=3, right=3):
    """Change-of-character: BOS against the prevailing swing trend."""
    trend = trend_state(bars, left, right)
    bos = bos_events(bars, left, right)
    out = []
    for i, (t, b) in enumerate(zip(trend, bos)):
        if b["status"] == "OK" and t["status"] == "OK":
            d = b["value"]["direction"]
            if (d == "BULLISH" and t["value"] == "DOWNTREND") or \
               (d == "BEARISH" and t["value"] == "UPTREND"):
                out.append(C.event("choch", b["value"], i, bars, "11g.structure",
                                   formation=i, confirmation=i,
                                   metadata={"against": t["value"]}))
                continue
        out.append(C.empty("choch", i, bars, "11g.structure", reason="NO_EVENT"))
    return out


def range_state(bars, period=50, min_hold=30):
    """Adapter over certified 11F range_state with 11G result schema."""
    out = []
    for i, r in enumerate(F11.range_state(bars, period, min_hold)):
        if r is None:
            out.append(C.empty("range_state", i, bars, "phase11f.range_state",
                               reason="NO_EVENT"))
        else:
            out.append(C.event("range_state", {"high": r["high"], "low": r["low"],
                                               "hold": r["hold"]},
                               i, bars, "phase11f.range_state",
                               formation=i, confirmation=i))
    return out
