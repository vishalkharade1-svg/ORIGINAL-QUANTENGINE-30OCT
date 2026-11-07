"""11G-A liquidity engine (REAL, OHLCV).

References: prior confirmed swing highs/lows, prior session high/low,
current-session running extremes, range boundaries, confirmed equal
levels. Session = UTC calendar day (documented convention). A prior
session extreme becomes available only after that session ends.
Sweep events are neutral representations (no signal, no entry).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C

SESSION = 86400


def _day(ts):
    return int(ts) // SESSION


def session_levels(bars):
    """Per-bar prior-session high/low (available after session end) and
    current-session running high/low/volume (prefix-only)."""
    hi, lo = C.highs(bars), C.lows(bars)
    out = []
    closed = {}
    run_h, run_l, run_v, run_day = None, None, None, None
    for i, b in enumerate(bars):
        day = _day(b["time"])
        if run_day is None or day != run_day:
            if run_day is not None:
                closed[run_day] = {"high": run_h, "low": run_l,
                                   "end_time": int(bars[i - 1]["time"])}
            run_day, run_h, run_l, run_v = day, hi[i], lo[i], float(b["volume"])
        else:
            run_h = max(run_h, hi[i])
            run_l = min(run_l, lo[i])
            run_v += float(b["volume"])
        prior = closed.get(day - 1)
        # NOTE: prior-session lookup uses day-1 only (consecutive-day
        # simplification, documented). Gaps leave the nearest closed
        # prior day unavailable rather than guessed.
        out.append(C.event("session_levels",
                           {"prior_high": prior["high"] if prior else None,
                            "prior_low": prior["low"] if prior else None,
                            "prior_available": prior is not None,
                            "session_high": run_h, "session_low": run_l,
                            "session_volume": run_v},
                           i, bars, "11g.liquidity",
                           formation=i, confirmation=i))
    return out


def reference_pools(bars, left=3, right=3, tolerance_atr=0.1):
    """Active liquidity references per bar: confirmed swing extremes
    (confirmed <= i), range boundaries, confirmed equal levels. Each
    reference carries its own confirmation time."""
    atr = F11.atr14(bars)
    sw = F11.swings(bars, left, right)
    hi, lo = F11.donchian(bars, 50)
    lv = F11.equal_levels(bars, 50, tolerance_atr, atr)
    out = []
    confirmed = []
    for i in range(len(bars)):
        if sw[i] is not None:
            s = sw[i]
            confirmed.append({"type": "swing_" + s["kind"], "level": s["extreme"],
                              "confirmed_time": int(bars[s["confirmed_index"]]["time"])})
        refs = list(confirmed)
        if hi[i] is not None:
            refs.append({"type": "range_high", "level": hi[i],
                         "confirmed_time": int(bars[i]["time"])})
            refs.append({"type": "range_low", "level": lo[i],
                         "confirmed_time": int(bars[i]["time"])})
        for g in lv[i]:
            refs.append({"type": "equal_" + g["kind"], "level": g["level"],
                         "touches": g["touches"],
                         "confirmed_time": int(bars[i]["time"])})
        out.append(C.event("liquidity_pool", refs, i, bars, "11g.liquidity",
                           formation=i, confirmation=i,
                           metadata={"n_refs": len(refs)}))
    return out


def sweep_events(bars, lookback=50, tolerance_atr=0.1, buffer_atr=0.25):
    """Neutral sweep representation over 11F sweep semantics.

    Records reference level/type, direction, penetration (beyond-level
    distance in ATR), sweep/reclaim/confirmation/availability times.
    No signal, no entry.
    """
    atr = F11.atr14(bars)
    sw = F11.sweeps(bars, lookback, tolerance_atr, atr)
    lv = F11.equal_levels(bars, lookback, tolerance_atr, atr)
    out = []
    for i in range(len(bars)):
        s = sw[i]
        if s is None or atr[i] is None:
            out.append(C.empty("sweep", i, bars, "phase11f.sweeps", reason="NO_EVENT"))
            continue
        pen = abs(s["extreme"] - s["level"]) / atr[i]
        out.append(C.event("sweep",
                           {"direction": s["direction"], "level": s["level"],
                            "extreme": s["extreme"],
                            "penetration_atr": pen,
                            "reference_type": "equal_level"},
                           i, bars, "phase11f.sweeps",
                           formation=i, confirmation=i,
                           metadata={"n_levels": len(lv[i])}))
    return out


def session_sweep_events(bars, buffer_atr=0.25):
    """Sweeps of the PRIOR session high/low (available sessions only):
    wick beyond + same-bar reclaim close. Timestamps on the sweep bar."""
    atr = F11.atr14(bars)
    sess = session_levels(bars)
    hi, lo, cl = C.highs(bars), C.lows(bars), C.closes(bars)
    out = []
    for i in range(len(bars)):
        ref = sess[i]["value"]
        if not ref["prior_available"] or atr[i] is None:
            out.append(C.empty("session_sweep", i, bars, "11g.liquidity",
                               reason="NO_EVENT"))
            continue
        buf = buffer_atr * atr[i]
        fired = None
        if lo[i] < ref["prior_low"] and cl[i] > ref["prior_low"]:
            fired = {"direction": "long", "level": ref["prior_low"], "extreme": lo[i]}
        elif hi[i] > ref["prior_high"] and cl[i] < ref["prior_high"]:
            fired = {"direction": "short", "level": ref["prior_high"], "extreme": hi[i]}
        if fired is None:
            out.append(C.empty("session_sweep", i, bars, "11g.liquidity",
                               reason="NO_EVENT"))
            continue
        pen = abs(fired["extreme"] - fired["level"]) / atr[i]
        out.append(C.event("session_sweep",
                           {"direction": fired["direction"], "level": fired["level"],
                            "extreme": fired["extreme"], "penetration_atr": pen,
                            "reference_type": "prior_session",
                            "buffer_atr": buf},
                           i, bars, "11g.liquidity",
                           formation=i, confirmation=i))
    return out
