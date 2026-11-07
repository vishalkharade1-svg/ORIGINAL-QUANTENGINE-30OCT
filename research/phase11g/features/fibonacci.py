"""11G-A Fibonacci adapter (REAL, OHLCV; confluence only).

Thin 11G wrapper over the certified 11F implementation (frozen ratios:
0.382/0.50/0.618/0.786 retracement, 1.272/1.618 extension; confirmed
anchors only; level timestamp = max anchor confirmation). Exposes
retracements, extensions, anchor/confirmation/availability timestamps,
and a confluence flag (close within 0.1 ATR of a level — frozen).
Fibonacci is a CONFLUENCE FEATURE, never a directional oracle.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11f import fibonacci as F11FIB
from research.phase11g.features import common as C


def retracements(bars, left=3, right=3):
    base = F11FIB.fib_retracements(bars, left, right)
    out = []
    for i, levels in enumerate(base):
        if not levels:
            out.append(C.empty("fib_retracement", i, bars, "phase11f.fibonacci",
                               reason="NO_EVENT"))
            continue
        out.append(C.event(
            "fib_retracement", levels, i, bars, "phase11f.fibonacci",
            formation=min(min(l["anchor_low_index"], l["anchor_high_index"])
                          for l in levels),
            confirmation=max(l["confirmed_index"] for l in levels),
            metadata={"n_levels": len(levels),
                      "ratios": list(F11FIB.FIB_RETRACE_RATIOS)}))
    return out


def extensions(bars, left=3, right=3):
    base = F11FIB.fib_extensions(bars, left, right)
    out = []
    for i, levels in enumerate(base):
        if not levels:
            out.append(C.empty("fib_extension", i, bars, "phase11f.fibonacci",
                               reason="NO_EVENT"))
            continue
        out.append(C.event(
            "fib_extension", levels, i, bars, "phase11f.fibonacci",
            formation=min(min(l["anchor_low_index"], l["anchor_high_index"])
                          for l in levels),
            confirmation=max(l["confirmed_index"] for l in levels),
            metadata={"n_levels": len(levels),
                      "ratios": list(F11FIB.FIB_EXTENSION_RATIOS)}))
    return out


def confluence(bars, left=3, right=3, tolerance_atr=0.1):
    """True when bar i's close sits within tolerance of any confirmed
    retracement level (frozen 0.1 ATR). Descriptive flag only."""
    atr = F11.atr14(bars)
    base = F11FIB.fib_retracements(bars, left, right)
    cl = C.closes(bars)
    out = []
    for i in range(len(bars)):
        if not base[i] or atr[i] is None:
            out.append(C.empty("fib_confluence", i, bars, "11g.fibonacci",
                               reason="NO_EVENT"))
            continue
        tol = tolerance_atr * atr[i]
        hit = [l for l in base[i] if abs(cl[i] - l["level"]) <= tol]
        if hit:
            out.append(C.event(
                "fib_confluence",
                {"ratios": [l["ratio"] for l in hit],
                 "direction": hit[0]["direction"]},
                i, bars, "11g.fibonacci", formation=i, confirmation=i,
                metadata={"tolerance_atr": tolerance_atr}))
        else:
            out.append(C.empty("fib_confluence", i, bars, "11g.fibonacci",
                               reason="NO_EVENT"))
    return out
