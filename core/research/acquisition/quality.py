"""
====================================================

QuantEngine -- Phase 17 dataset quality audit.

Research-only, deterministic, stdlib-only. Pure
functions over normalized OHLCV row dicts
({time,open,high,low,close,volume}). No strategy
logic, no thresholds, no execution, no I/O.

Flat / zero-volume bars are COUNTED, never classified:
their provenance (quiescence vs feed artifact) is
indistinguishable from OHLCV alone, so the audit
reports PROVENANCE_UNKNOWN and removes nothing.
====================================================
"""

from __future__ import annotations

ROW_KEYS = ("close", "high", "low", "open", "time", "volume")


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def audit_quality(rows, step=60, requested=None):
    """Audit one normalized candle series.

    rows: sequence of {time,open,high,low,close,volume}.
    step: expected seconds between consecutive bars.
    requested: bars requested from the venue (None = unknown).
    """
    rows = list(rows)
    received = len(rows)
    malformed = 0
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            malformed += 1
            continue
        if sorted(row.keys()) != sorted(ROW_KEYS):
            malformed += 1
            continue
        ts = row.get("time")
        if not isinstance(ts, int) or isinstance(ts, bool):
            malformed += 1
            continue
        clean.append(row)
    stamps = sorted(r["time"] for r in clean)
    duplicates = len(stamps) - len(set(stamps))
    monotonic = all(b > a for a, b in zip(stamps, stamps[1:]))
    missing_intervals = 0
    gaps = []
    for a, b in zip(stamps, stamps[1:]):
        skipped = round((b - a) / step) - 1
        if skipped > 0:
            missing_intervals += skipped
            gaps.append({"gap_start": a, "gap_end": b,
                         "missing_bars": skipped})
    ohlc_violations = 0
    nonpositive_prices = 0
    flat_bars = 0
    zero_volume_bars = 0
    for row in clean:
        o = _as_float(row["open"])
        h = _as_float(row["high"])
        l = _as_float(row["low"])
        c = _as_float(row["close"])
        v = _as_float(row["volume"])
        if None in (o, h, l, c, v):
            malformed += 1
            continue
        if h < l or h < o or h < c or l > o or l > c:
            ohlc_violations += 1
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            nonpositive_prices += 1
        if o == h == l == c:
            flat_bars += 1
        if v == 0:
            zero_volume_bars += 1
    if stamps:
        start, end = stamps[0], stamps[-1]
        span_bars = round((end - start) / step) + 1
    else:
        start, end, span_bars = None, None, 0
    coverage_pct = (received / span_bars) if span_bars else 0.0
    return {
        "coverage": {
            "requested": requested,
            "received": received,
            "expected_intervals": span_bars,
            "actual_intervals": len(set(stamps)),
            "coverage_pct": coverage_pct,
            "start": start,
            "end": end,
            "duration_bars": span_bars,
        },
        "integrity": {
            "duplicates": duplicates,
            "missing_intervals": missing_intervals,
            "monotonic": monotonic,
            "ohlc_violations": ohlc_violations,
            "nonpositive_prices": nonpositive_prices,
            "malformed_rows": malformed,
        },
        "activity": {
            "flat_bars": flat_bars,
            "zero_volume_bars": zero_volume_bars,
            "flat_pct": (flat_bars / received) if received else 0.0,
            "zero_volume_pct": (zero_volume_bars / received)
            if received else 0.0,
            "flat_provenance": "PROVENANCE_UNKNOWN",
        },
        "continuity": {
            "gaps": gaps,
            "gap_count": len(gaps),
            "max_gap_bars": max(
                (g["missing_bars"] for g in gaps), default=0),
        },
    }
