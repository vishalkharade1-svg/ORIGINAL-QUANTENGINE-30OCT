"""11G-A shared result constructor (no strategy, no economics).

Every 11G feature returns per-bar dicts with formation / confirmation /
availability timestamps. Computation at decision bar i may only use
bars[0..i]; results are aligned so out[i] is knowable at bar i.
"""

from __future__ import annotations


def _t(bars, j):
    if 0 <= j < len(bars):
        return int(bars[j]["time"])
    return None


def event(name, value, i, bars, source, formation=None, confirmation=None,
          metadata=None, provenance="REAL"):
    """A computed event/value knowable at bar i."""
    return {
        "feature_name": name,
        "value": value,
        "status": "OK",
        "formation_time": _t(bars, formation if formation is not None else i),
        "confirmation_time": _t(bars, confirmation if confirmation is not None else i),
        "availability_time": _t(bars, i),
        "source": source,
        "causal": True,
        "provenance": provenance,
        "metadata": dict(metadata or {}),
    }


def empty(name, i, bars, source, reason="INSUFFICIENT_HISTORY", provenance="REAL"):
    return {
        "feature_name": name,
        "value": None,
        "status": reason,
        "formation_time": None,
        "confirmation_time": None,
        "availability_time": None,
        "source": source,
        "causal": True,
        "provenance": provenance,
        "metadata": {},
    }


def closes(bars):
    return [float(b["close"]) for b in bars]


def highs(bars):
    return [float(b["high"]) for b in bars]


def lows(bars):
    return [float(b["low"]) for b in bars]
