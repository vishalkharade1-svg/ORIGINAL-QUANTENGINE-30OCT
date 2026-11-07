"""11G-A displacement adapter (REAL, OHLCV).

Exposes certified 11F displacement (range > mult*ATR14) through the 11G
result contract plus causal body/range/close-location/consecutive-bar
descriptors. Threshold frozen at construction (default 2.0); no tuning.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def displacement(bars, mult=2.0):
    atr = F11.atr14(bars)
    base = F11.displacement(bars, mult, atr)
    op, hi, lo, cl = ([float(b[k]) for b in bars]
                      for k in ("open", "high", "low", "close"))
    out = []
    for i in range(len(bars)):
        if atr[i] is None:
            out.append(C.empty("displacement", i, bars, "phase11f.displacement",
                               reason="INSUFFICIENT_HISTORY"))
            continue
        rng = hi[i] - lo[i]
        body = abs(cl[i] - op[i])
        mid = (hi[i] + lo[i]) / 2.0
        out.append(C.event(
            "displacement", bool(base[i]), i, bars, "phase11f.displacement",
            formation=i, confirmation=i,
            metadata={"mult": mult, "range_atr": rng / atr[i] if atr[i] else None,
                      "body_ratio": (body / rng) if rng > 0 else 0.0,
                      "close_location": ((cl[i] - lo[i]) / rng) if rng > 0 else 0.5}))
    return out


def consecutive_bars(bars, n=3):
    """True when the last n closes (incl. bar i) share one direction."""
    cl = C.closes(bars)
    out = []
    for i in range(len(bars)):
        if i + 1 < n:
            out.append(C.empty("consecutive", i, bars, "11g.displacement",
                               reason="INSUFFICIENT_HISTORY"))
            continue
        window = [cl[j] - cl[j - 1] for j in range(i - n + 2, i + 1)]
        up = all(d > 0 for d in window)
        dn = all(d < 0 for d in window)
        if up or dn:
            out.append(C.event("consecutive", "UP" if up else "DOWN",
                               i, bars, "11g.displacement",
                               formation=i, confirmation=i, metadata={"n": n}))
        else:
            out.append(C.empty("consecutive", i, bars, "11g.displacement",
                               reason="NO_EVENT"))
    return out
