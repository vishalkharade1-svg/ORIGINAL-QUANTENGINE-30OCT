"""11G-A FVG adapter (REAL, OHLCV).

Exposes certified 11F FVG zones through the 11G result contract with
formation (three-bar pattern) / confirmation (third bar) /
availability timestamps, ATR-normalized size, boundaries, and age.
Mitigation state itself is tracked by the mitigation engine.
Thresholds frozen (11F definitions, unoptimized).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def fvg_zones(bars):
    atr = F11.atr14(bars)
    base = F11.fvg_zones(bars)
    out = []
    for i in range(len(bars)):
        z = base[i]
        if z is None:
            out.append(C.empty("fvg", i, bars, "phase11f.fvg_zones",
                               reason="NO_EVENT"))
            continue
        size = abs(z["top"] - z["bottom"])
        out.append(C.event(
            "fvg", {"direction": z["direction"], "top": z["top"],
                    "bottom": z["bottom"], "origin_index": z["origin_index"]},
            i, bars, "phase11f.fvg_zones",
            formation=i - 2, confirmation=i,
            metadata={"size": size,
                      "size_atr": (size / atr[i]) if atr[i] else None,
                      "age_bars": 0}))
    return out


def fvg_age(open_zones, i):
    """Age in bars of already-formed zones at bar i (past-only count)."""
    return [i - z["origin_index"] for z in open_zones]
