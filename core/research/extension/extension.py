"""
====================================================
QuantEngine -- Phase 19 OOS data-extension helpers.

Research-only, deterministic, stdlib-only. Pure
functions over venue-verbatim OHLCV rows. No strategy
logic, no thresholds, no execution, no I/O, no network,
no randomness.

Extension rule: every row must satisfy
timestamp > discovery_boundary (strict). Merging never
fabricates bars, never fills gaps, never interpolates.
Zero fills stay zero: no finite bars-per-fill is ever
inferred from a zero-fill sample.
====================================================
"""

from __future__ import annotations


ROW_KEYS = ("close", "high", "low", "open", "time", "volume")


def dedupe_merge(existing_rows, incoming_rows, discovery_boundary):
    """Merge two row sets into a strictly-after-boundary series.

    Dedupes by timestamp (first occurrence wins), drops any row
    with timestamp <= boundary, malformed rows, or non-dict
    rows. Returns ascending-sorted list. Gaps are preserved
    (never filled).
    """
    boundary = int(discovery_boundary)
    seen = {}
    for source in (existing_rows, incoming_rows):
        for r in list(source):
            if not isinstance(r, dict):
                continue
            if sorted(r.keys()) != sorted(ROW_KEYS):
                continue
            ts = r.get("time")
            if not isinstance(ts, int) or isinstance(ts, bool):
                continue
            if ts <= boundary:
                continue
            if ts not in seen:
                seen[ts] = r
    return [seen[t] for t in sorted(seen)]


def extension_stats(old_rows_asc, merged_rows_asc):
    """Describe what the extension added (bars only, not trades)."""
    old_ts = set(r["time"] for r in old_rows_asc)
    merged_ts = [r["time"] for r in merged_rows_asc]
    new_ts = [t for t in merged_ts if t not in old_ts]
    return {
        "previous_bars": len(old_rows_asc),
        "merged_bars": len(merged_rows_asc),
        "added_bars": len(new_ts),
        "new_min": min(new_ts) if new_ts else None,
        "new_max": max(new_ts) if new_ts else None,
        "merged_min": min(merged_ts) if merged_ts else None,
        "merged_max": max(merged_ts) if merged_ts else None,
    }


def estimate_extension(observed_fills, merged_bars,
                       per_period_bars=25000.0, n_periods=6):
    """Feasibility estimate from a zero-or-thin fill sample.

    With 0 observed fills no finite bars-per-fill exists:
    returns bars_per_fill None + requirement UNAVAILABLE with
    an explicit lower-bound context from the Gate-A measured
    rates (caller-supplied per_period_bars). Labels are
    ESTIMATE, never EVIDENCE.
    """
    fills = int(observed_fills or 0)
    if fills <= 0:
        return {
            "bars_per_fill": None,
            "status": "ZERO OBSERVED FILLS",
            "required_bars_context": float(per_period_bars) * int(n_periods),
            "verdict": "OOS_BLOCKED",
            "note": ("ESTIMATE only: no finite requirement can be "
                     "inferred from zero fills; context lower bound "
                     "shown for scale, unbounded above"),
        }
    rate = fills / float(merged_bars) if merged_bars else 0.0
    if rate <= 0.0:
        return {
            "bars_per_fill": None,
            "status": "ZERO OBSERVED FILLS",
            "required_bars_context": float(per_period_bars) * int(n_periods),
            "verdict": "OOS_BLOCKED",
            "note": "ESTIMATE only",
        }
    need_60 = 60.0 / rate
    return {
        "bars_per_fill": 1.0 / rate,
        "status": "ESTIMATE",
        "required_bars_context": need_60,
        "verdict": "OOS_BLOCKED" if merged_bars < need_60 else "OOS_FEASIBLE",
        "note": "ESTIMATE only: point rate from thin sample",
    }
