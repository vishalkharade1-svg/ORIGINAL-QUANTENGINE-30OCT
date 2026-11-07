"""
====================================================
QuantEngine -- Phase 18 OOS bar-period splitter.

Research-only, deterministic, stdlib-only. Splits a
chronologically-ordered bar series into N equal,
non-overlapping, chronological OOS periods with
deterministic IDs (OOS_01..OOS_N). No shuffle, no
normalization, no future leakage: period boundaries are
index boundaries into the supplied order.

Freshness is validated separately: every row must satisfy
timestamp > discovery_boundary (strict, no equality).
====================================================
"""

from __future__ import annotations


PERIOD_STATUSES = (
    "UNAVAILABLE",
    "INCONCLUSIVE",
    "REJECTED",
    "PROMISING",
    "VALIDATED",
)

FINAL_DECISIONS = (
    "OOS_BLOCKED",
    "INCONCLUSIVE",
    "REJECTED",
    "PROMISING",
    "VALIDATED_RESEARCH_ONLY",
)


def validate_freshness(rows_asc, discovery_boundary):
    """Check strict freshness + ordering + uniqueness.

    rows_asc: sequence of {time,...} in ascending order.
    Returns dict with min/max/count/ordered/unique/violations.
    """
    stamps = [r["time"] for r in rows_asc]
    ordered = all(b > a for a, b in zip(stamps, stamps[1:]))
    unique = len(set(stamps)) == len(stamps)
    below = [t for t in stamps if t <= int(discovery_boundary)]
    return {
        "count": len(stamps),
        "min": min(stamps) if stamps else None,
        "max": max(stamps) if stamps else None,
        "ordered": bool(ordered),
        "unique": bool(unique),
        "boundary": int(discovery_boundary),
        "violations": len(below),
        "strictly_after": len(below) == 0 and len(stamps) > 0,
    }


def split_bars(rows_asc, n_periods=6, prefix="OOS"):
    """Split ascending rows into N chronological bar periods.

    Returns list of dicts with period_id/start/end/row_count/
    expected/actual/completeness + row slice indices. The last
    period absorbs any remainder so no bar is dropped.
    """
    rows = list(rows_asc)
    total = len(rows)
    n = int(n_periods)
    if n <= 0:
        raise ValueError("n_periods must be positive")
    if total <= 0:
        raise ValueError("rows must be non-empty")
    base = total // n
    periods = []
    for i in range(n):
        s = i * base
        e = (i + 1) * base if i < n - 1 else total
        sl = rows[s:e]
        stamps = [r["time"] for r in sl]
        periods.append({
            "period_id": "%s_%02d" % (prefix, i + 1),
            "index": i,
            "start": min(stamps) if stamps else None,
            "end": max(stamps) if stamps else None,
            "row_count": len(sl),
            "expected_rows": base if i < n - 1 else total - base * (n - 1),
            "actual_rows": len(sl),
            "completeness": 1.0 if sl else 0.0,
            "slice": (s, e),
        })
    return periods
