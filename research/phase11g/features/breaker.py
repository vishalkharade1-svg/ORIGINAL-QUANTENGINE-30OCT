"""11G-A breaker adapter (REAL, OHLCV).

Event representation (no orders): a confirmed swing extreme acts as the
level; a close crossing back through it is the failure/role-reversal
event, confirmed on the crossing bar. Zone = the flipped level;
invalidation = close back across the level against the break direction.
Production breaker semantics unchanged (adapter only, new timestamps).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def breaker_events(bars, left=3, right=3):
    sw = F11.swings(bars, left, right)
    cl = C.closes(bars)
    out = [C.empty("breaker", i, bars, "11g.breaker", reason="NO_EVENT")
           for i in range(len(bars))]
    last_high = last_low = None
    for i in range(len(bars)):
        if sw[i] is not None:
            if sw[i]["kind"] == "high":
                last_high = sw[i]["extreme"]
            else:
                last_low = sw[i]["extreme"]
        if i == 0:
            continue
        if last_low is not None and cl[i - 1] <= last_low < cl[i]:
            out[i] = C.event("breaker",
                             {"direction": "BULLISH", "level": last_low,
                              "source": "failed_support",
                              "invalidation": "close back below level"},
                             i, bars, "11g.breaker",
                             formation=i, confirmation=i)
        elif last_high is not None and cl[i - 1] >= last_high > cl[i]:
            out[i] = C.event("breaker",
                             {"direction": "BEARISH", "level": last_high,
                              "source": "failed_resistance",
                              "invalidation": "close back above level"},
                             i, bars, "11g.breaker",
                             formation=i, confirmation=i)
    return out
