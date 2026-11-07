"""11G-A availability snapshot: 'what was known at T'.

Primary lookahead defense for Stage-B research: given per-bar feature
arrays, known_at() returns only entries whose availability_time <= T.
Anything dated after T is invisible by construction.
"""

from __future__ import annotations


def known_at(series, timestamp):
    """series: list of 11G result dicts. Returns [value|None] visible at T."""
    out = []
    for res in series:
        if res.get("status") == "OK" and res.get("availability_time") is not None \
                and res["availability_time"] <= timestamp:
            out.append(res["value"])
        else:
            out.append(None)
    return out


def confluence_at(states_by_field, timestamp):
    """states_by_field: {field: per-bar series}. Returns the descriptive
    confluence using only knowledge available at T (all other fields None)."""
    from research.phase11g.features import confluence as CF
    states = {}
    for field, series in states_by_field.items():
        visible = [r for r in series
                   if r.get("status") == "OK"
                   and r.get("availability_time") is not None
                   and r["availability_time"] <= timestamp]
        states[field] = visible[-1] if visible else {"status": "NO_EVENT"}
    return CF.compose(states)
