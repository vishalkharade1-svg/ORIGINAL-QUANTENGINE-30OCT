"""11G-A confluence representation (descriptive state, NO scores).

Composes per-feature decision-bar states into one descriptive dict.
There are no weights, no thresholds, no buy/sell outputs — any future
scoring must itself be preregistered. A numeric 'score' key is
rejected outright (see compose()).
"""

from __future__ import annotations


CONFLUENCE_FIELDS = ("structure", "liquidity", "displacement", "fvg",
                     "order_block", "breaker", "wyckoff", "fib",
                     "volume_regime", "mtf_structure", "order_flow")


def compose(states):
    """states: {field: 11G result dict}. Returns the descriptive state.

    Unknown fields and any 'score'/'weight' keys raise ValueError.
    """
    for key in states:
        if key in ("score", "weight", "weights", "total"):
            raise ValueError("confluence forbids scores: %r" % key)
        if key not in CONFLUENCE_FIELDS:
            raise ValueError("unknown confluence field: %r" % key)
    out = {}
    for field in CONFLUENCE_FIELDS:
        res = states.get(field)
        if res is None or res.get("status") != "OK":
            out[field] = None
            continue
        out[field] = {"value": res.get("value"),
                      "availability_time": res.get("availability_time"),
                      "provenance": res.get("provenance", "REAL")}
    return out


def provenance_map(states):
    composed = compose(states)
    return {k: v.get("provenance", "REAL") for k, v in composed.items()
            if isinstance(v, dict)}
