"""Deterministic multi-symbol OOS evidence coverage audit.

Research-only. Symbol identity may be established either by an explicit row
field or by a row-level provenance record whose timestamp set exactly covers
the rows. Filename/envelope-only inference is never accepted.
"""
from __future__ import annotations

import hashlib
import json

STATUS = ("VERIFIED", "INCONCLUSIVE", "UNAVAILABLE")


def _identity(payload):
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _explicit_symbol_rows(rows):
    buckets = {}
    missing = 0
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            missing += 1
            continue
        symbol = symbol.strip()
        bucket = buckets.setdefault(symbol, {"rows": 0, "trades": 0,
                                              "timestamps": []})
        bucket["rows"] += 1
        ts = row.get("time")
        if isinstance(ts, int) and not isinstance(ts, bool):
            bucket["timestamps"].append(ts)
        trades = row.get("completed_trades")
        if isinstance(trades, int) and not isinstance(trades, bool):
            bucket["trades"] += max(0, trades)
    return buckets, missing


def _provenance_symbol_rows(rows, provenance):
    """Use row-level provenance only when it exactly covers row timestamps.

    A provenance record is admissible because it is already bound to the
    accepted dataset by the existing Phase-20 provenance identity. We require
    one-to-one timestamp coverage and reject mixed symbol/timeframe/venue
    provenance rather than guessing.
    """
    by_time = {}
    for record in provenance or ():
        if not isinstance(record, dict):
            continue
        ts = record.get("time")
        if isinstance(ts, int) and not isinstance(ts, bool):
            if ts in by_time and by_time[ts] != record:
                return None, "CONFLICTING_PROVENANCE"
            by_time[ts] = record
    buckets = {}
    missing = 0
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        ts = row.get("time")
        record = by_time.get(ts) if isinstance(ts, int) else None
        symbol = record.get("symbol") if record else None
        if not isinstance(symbol, str) or not symbol.strip():
            missing += 1
            continue
        symbol = symbol.strip()
        bucket = buckets.setdefault(symbol, {"rows": 0, "trades": 0,
                                              "timestamps": []})
        bucket["rows"] += 1
        if isinstance(ts, int) and not isinstance(ts, bool):
            bucket["timestamps"].append(ts)
        trades = row.get("completed_trades")
        if isinstance(trades, int) and not isinstance(trades, bool):
            bucket["trades"] += max(0, trades)
    row_times = {r.get("time") for r in rows or ()
                 if isinstance(r, dict) and isinstance(r.get("time"), int)
                 and not isinstance(r.get("time"), bool)}
    if set(by_time) != row_times:
        return None, "PROVENANCE_COVERAGE_MISMATCH"
    return buckets, None


def _render(buckets, *, required_bars, required_trades):
    symbols = []
    for symbol in sorted(buckets):
        item = buckets[symbol]
        timestamps = sorted(set(item["timestamps"]))
        rows_count = item["rows"]
        trade_count = item["trades"]
        if rows_count >= required_bars and trade_count >= required_trades:
            status = "VERIFIED"
        elif rows_count or trade_count:
            status = "INCONCLUSIVE"
        else:
            status = "UNAVAILABLE"
        symbols.append({
            "symbol": symbol,
            "status": status,
            "rows": rows_count,
            "trades": trade_count,
            "first_timestamp": timestamps[0] if timestamps else None,
            "last_timestamp": timestamps[-1] if timestamps else None,
        })
    return symbols


def audit(rows, *, required_bars=0, required_trades=0, provenance=None):
    """Return deterministic per-symbol coverage without filename inference."""
    explicit, explicit_missing = _explicit_symbol_rows(rows)
    source = "explicit_row_metadata"
    error = None
    if provenance is not None:
        bound, error = _provenance_symbol_rows(rows, provenance)
        if bound is not None:
            buckets = bound
            missing = 0
            source = "row_level_provenance"
        else:
            buckets = explicit
            missing = explicit_missing
            source = "explicit_row_metadata_fallback"
    else:
        buckets = explicit
        missing = explicit_missing
    symbols = _render(buckets, required_bars=required_bars,
                       required_trades=required_trades)
    if provenance is None:
        # Preserve the Phase-35 artifact schema/bytes for callers that do not
        # opt into provenance-backed attribution.
        payload = {
            "schema_version": "1",
            "required_bars": int(required_bars),
            "required_trades": int(required_trades),
            "missing_symbol_rows": missing,
            "symbols": symbols,
        }
    else:
        payload = {
            "schema_version": "2",
            "required_bars": int(required_bars),
            "required_trades": int(required_trades),
            "symbol_source": source,
            "symbol_source_error": error,
            "missing_symbol_rows": missing,
            "symbols": symbols,
        }
    return dict(payload, audit_id=_identity(payload))
