"""11G-A mitigation state machine (REAL, OHLCV; deterministic).

Zones are described once (top/bottom/direction/origin/confirmation);
`track()` advances each zone bar-by-bar using only information
available at that bar. States:

  UNTOUCHED -> TOUCHED (wick enters zone)
  TOUCHED -> PARTIALLY_MITIGATED (penetration >= 50% of zone depth)
  -> MITIGATED (penetration >= 100%: full traverse past far edge)
  any open state -> INVALIDATED (close beyond far edge + buffer)

Tracks first_touch / touch_count / penetration / last_touch.
A future touch can never alter an earlier state (proven by test:
states are a pure left fold over bars[0..i]).
"""

from __future__ import annotations

UNTOUCHED, TOUCHED, PARTIALLY_MITIGATED, MITIGATED, INVALIDATED = (
    "UNTOUCHED", "TOUCHED", "PARTIALLY_MITIGATED", "MITIGATED", "INVALIDATED")


def new_zone(top, bottom, direction, origin_index, confirmed_index,
             buffer=0.0):
    return {"top": float(top), "bottom": float(bottom),
            "direction": direction, "origin_index": origin_index,
            "confirmed_index": confirmed_index, "buffer": float(buffer),
            "state": UNTOUCHED, "first_touch": None, "touch_count": 0,
            "penetration": 0.0, "last_touch": None}


def update(zone, bar, index):
    """Advance one zone by one bar (past-only). Mutates a copy."""
    z = dict(zone)
    if z["state"] in (MITIGATED, INVALIDATED):
        return z
    hi, lo, cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
    top, bot = z["top"], z["bottom"]
    depth = top - bot
    if depth <= 0:
        return z
    touched = (lo <= top and hi >= bot)
    overlap = min(hi, top) - max(lo, bot)
    through = (lo <= bot and hi >= top)
    pen = 1.0 if through else max(0.0, overlap / depth)
    if touched:
        z["touch_count"] += 1
        z["last_touch"] = index
        if z["first_touch"] is None:
            z["first_touch"] = index
    z["penetration"] = max(z["penetration"], pen)
    # Invalidation: close through the far edge plus buffer.
    if z["direction"] == "long" and cl < bot - z["buffer"]:
        z["state"] = INVALIDATED
    elif z["direction"] == "short" and cl > top + z["buffer"]:
        z["state"] = INVALIDATED
    elif z["penetration"] >= 1.0:
        z["state"] = MITIGATED
    elif z["penetration"] >= 0.5:
        z["state"] = PARTIALLY_MITIGATED
    elif touched:
        z["state"] = TOUCHED
    return z


def track(bars, zones, buffer_atr=0.0, atr=None):
    """Per-bar zone states. zones: list of new_zone() dicts with
    confirmed_index set. A zone contributes states only at bars
    >= its confirmation bar (never before). Pure left fold:
    state[i] depends only on bars[0..i]."""
    live = [dict(z) for z in zones]
    states = []
    for i in range(len(bars)):
        row = []
        for z in live:
            if i < z["confirmed_index"]:
                row.append({"state": UNTOUCHED, "pending": True,
                            "confirmed_index": z["confirmed_index"]})
                continue
            buf = buffer_atr * (atr[i] if atr and atr[i] else 0.0)
            z["buffer"] = buf
            updated = update(z, bars[i], i)
            z.update(updated)
            row.append(dict(z))
        states.append(row)
    return states
