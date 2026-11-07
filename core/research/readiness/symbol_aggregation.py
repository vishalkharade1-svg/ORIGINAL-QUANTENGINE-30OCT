"""Deterministic cross-symbol OOS evidence aggregation.

Research-only. Aggregation never converts missing evidence into rejection and
never converts one symbol's result into another symbol's result. Each symbol
remains independently visible.
"""
from __future__ import annotations

import hashlib
import json

STATUSES = ("VALIDATED", "PROMISING", "INCONCLUSIVE", "REJECTED", "UNAVAILABLE")


def _identity(payload):
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def aggregate_symbol_results(results, *, required_symbols=0):
    """Aggregate already-evaluated symbol results without hiding evidence.

    ``results`` must contain explicit symbol/status records. A missing symbol
    is represented by absence from the input and remains ``UNAVAILABLE`` when
    a required symbol universe is supplied. No status is inferred from another
    symbol. The returned summary is descriptive and does not promote OOS state.
    """
    if not isinstance(required_symbols, int) or isinstance(required_symbols, bool) or required_symbols < 0:
        raise ValueError("required_symbols must be a non-negative integer")

    rendered = {}
    for item in results or ():
        if not isinstance(item, dict):
            raise ValueError("MALFORMED_SYMBOL_RESULT")
        symbol = item.get("symbol")
        status = item.get("status")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("MISSING_SYMBOL")
        symbol = symbol.strip()
        if status not in STATUSES:
            raise ValueError("INVALID_SYMBOL_STATUS:%s" % status)
        if symbol in rendered:
            raise ValueError("DUPLICATE_SYMBOL:%s" % symbol)
        rendered[symbol] = {
            "symbol": symbol,
            "status": status,
            "rows": int(item.get("rows", 0)),
            "trades": int(item.get("trades", 0)),
        }

    symbols = [rendered[s] for s in sorted(rendered)]
    counts = {status: 0 for status in STATUSES}
    for item in symbols:
        counts[item["status"]] += 1

    payload = {
        "schema_version": "oos-symbol-aggregation-v1",
        "required_symbols": required_symbols,
        "observed_symbols": len(symbols),
        "symbol_results": symbols,
        "status_counts": counts,
        "missing_required_symbols": max(0, required_symbols - len(symbols)),
        "cross_symbol_evidence": (
            "AVAILABLE" if len(symbols) >= required_symbols and required_symbols > 0
            else "UNAVAILABLE"
        ),
    }
    return dict(payload, aggregation_id=_identity(payload))
