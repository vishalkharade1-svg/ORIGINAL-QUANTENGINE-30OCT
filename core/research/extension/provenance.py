"""Deterministic row-level provenance for research acquisition artifacts.

Research-only. This records the acquisition authority asserted by the
collector for each accepted row without modifying the venue-verbatim raw
candle schema. It does not independently prove venue authenticity.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = "row-provenance-v1"


def build_row_provenance(rows, *, venue, acquisition_source, acquisition_method,
                         symbol, timeframe):
    """Build deterministic provenance records for every accepted row."""
    records = []
    for row in sorted(rows, key=lambda r: r["time"]):
        records.append({
            "time": int(row["time"]),
            "venue": str(venue),
            "acquisition_source": str(acquisition_source),
            "acquisition_method": str(acquisition_method),
            "symbol": str(symbol),
            "timeframe": str(timeframe),
        })
    return records


def provenance_identity(records):
    blob = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def validate_row_provenance(rows, records, *, expected_venue, expected_source,
                            expected_method, expected_symbol, expected_timeframe):
    """Validate exact timestamp coverage and immutable acquisition metadata."""
    expected_times = [int(r["time"]) for r in sorted(rows, key=lambda r: r["time"])]
    if len(records) != len(expected_times):
        return False, "ROW_COUNT_MISMATCH"
    actual_times = [int(r["time"]) for r in records]
    if actual_times != expected_times:
        return False, "TIMESTAMP_COVERAGE_MISMATCH"
    required = {
        "venue": str(expected_venue),
        "acquisition_source": str(expected_source),
        "acquisition_method": str(expected_method),
        "symbol": str(expected_symbol),
        "timeframe": str(expected_timeframe),
    }
    for record in records:
        for key, value in required.items():
            if record.get(key) != value:
                return False, "METADATA_MISMATCH"
    return True, "VERIFIED"
