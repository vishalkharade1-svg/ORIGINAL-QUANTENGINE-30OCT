"""11G-A volume engine (REAL volume measurement; neutral interpretation).

Total 1m volume is REAL. Everything derived from it (relative volume,
expansion, regimes) is an explicitly labeled volume aggregate — never
"institutional volume", never order flow. All rolling statistics use
trailing windows over bars[..i] only (no centering, no future).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def rolling_stats(bars, window=20):
    """Trailing mean/median volume + relative volume at each bar."""
    vols = [float(b["volume"]) for b in bars]
    out = []
    for i in range(len(bars)):
        if i + 1 < window:
            out.append(C.empty("volume_stats", i, bars, "11g.volume",
                               reason="INSUFFICIENT_HISTORY"))
            continue
        win = vols[i - window + 1:i + 1]
        mean = sum(win) / window
        med = _median(win)
        out.append(C.event(
            "volume_stats",
            {"volume": vols[i], "mean": mean, "median": med,
             "rvol_mean": (vols[i] / mean) if mean > 0 else None,
             "rvol_median": (vols[i] / med) if med > 0 else None},
            i, bars, "11g.volume", formation=i, confirmation=i,
            metadata={"window": window, "provenance": "REAL volume; derived ratios"}))
    return out


def volume_regime(bars, window=100):
    """LOW/NORMAL/HIGH from the trailing-window rank of current volume.

    rank = fraction of trailing bars (incl. current) with volume <=
    current. LOW: rank < 1/3. HIGH: rank >= 2/3. Else NORMAL.
    Thresholds are trailing-causal by construction (no fitted cutoffs).
    """
    vols = [float(b["volume"]) for b in bars]
    out = []
    for i in range(len(bars)):
        if i + 1 < window:
            out.append(C.empty("volume_regime", i, bars, "11g.volume",
                               reason="INSUFFICIENT_HISTORY"))
            continue
        win = vols[i - window + 1:i + 1]
        rank = sum(1 for v in win if v <= vols[i]) / window
        state = "LOW" if rank < 1.0 / 3.0 else ("HIGH" if rank >= 2.0 / 3.0 else "NORMAL")
        out.append(C.event("volume_regime", state, i, bars, "11g.volume",
                           formation=i, confirmation=i,
                           metadata={"window": window, "rank": rank}))
    return out


def expansion(bars, window=20, mult=2.0):
    """True when volume >= mult * trailing median (frozen mult)."""
    stats = rolling_stats(bars, window)
    out = []
    for i, s in enumerate(stats):
        if s["status"] != "OK":
            out.append(C.empty("volume_expansion", i, bars, "11g.volume",
                               reason=s["status"]))
            continue
        rvm = s["value"]["rvol_median"]
        out.append(C.event("volume_expansion", bool(rvm is not None and rvm >= mult),
                           i, bars, "11g.volume", formation=i, confirmation=i,
                           metadata={"mult": mult, "rvol_median": rvm}))
    return out
