"""Deterministic multi-symbol OOS acquisition manifest.

Research-only. Combines already-validated symbol batches without merging
symbol namespaces. Each symbol retains its own rows, provenance identity and
batch identity. No filename inference, gap filling, or synthetic rows.
"""
from __future__ import annotations

import hashlib
import json

from core.research.acquisition.accumulator import AccumulationError, validate_batch

SCHEMA_VERSION = "oos-multi-symbol-manifest-v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _identity(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_manifest(batches, *, boundary, expected_venue, expected_source,
                    expected_method, expected_timeframe):
    """Validate independent symbol batches and return deterministic manifest.

    ``batches`` is an iterable of mappings with ``symbol``, ``rows`` and
    ``provenance``. Symbols must be unique; cross-symbol timestamp overlap is
    allowed because timestamps are not a global identity across instruments.
    """
    rendered = []
    seen = set()
    for batch in batches or ():
        if not isinstance(batch, dict):
            raise AccumulationError("MALFORMED_SYMBOL_BATCH")
        symbol = batch.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise AccumulationError("MISSING_SYMBOL")
        symbol = symbol.strip()
        if symbol in seen:
            raise AccumulationError("DUPLICATE_SYMBOL:%s" % symbol)
        seen.add(symbol)
        rows = list(batch.get("rows") or ())
        provenance = list(batch.get("provenance") or ())
        meta = validate_batch(
            rows, provenance, boundary=boundary,
            expected_venue=expected_venue, expected_source=expected_source,
            expected_method=expected_method, expected_symbol=symbol,
            expected_timeframe=expected_timeframe)
        rendered.append({
            "symbol": symbol,
            "timeframe": str(expected_timeframe),
            "row_count": meta["row_count"],
            "first_timestamp": meta["first_timestamp"],
            "last_timestamp": meta["last_timestamp"],
            "batch_identity": meta["batch_identity"],
            "provenance_identity": _identity(sorted(provenance,
                                                     key=lambda r: r["time"])),
        })
    rendered.sort(key=lambda item: item["symbol"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "boundary": int(boundary),
        "venue": str(expected_venue),
        "acquisition_source": str(expected_source),
        "acquisition_method": str(expected_method),
        "timeframe": str(expected_timeframe),
        "symbol_count": len(rendered),
        "symbols": rendered,
    }
    return dict(payload, manifest_id=_identity(payload))
