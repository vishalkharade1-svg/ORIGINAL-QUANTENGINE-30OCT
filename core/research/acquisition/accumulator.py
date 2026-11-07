"""Deterministic research-data batch accumulation.

Research-only.  Pure functions over venue-verbatim OHLCV rows and row-level
provenance.  The accumulator never fetches data, fills gaps, interpolates,
or executes trading logic.

Unlike the historical Phase-19 merge helper, this layer refuses conflicting
same-timestamp rows instead of silently choosing one.  Identical duplicates
are retained once.  Every accepted row must have matching acquisition
provenance.  Batch identities are content-derived and contain no wall-clock
state.
"""
from __future__ import annotations

import hashlib
import json

from core.research.extension.extension import ROW_KEYS


SCHEMA_VERSION = "oos-acquisition-accumulator-v1"


class AccumulationError(ValueError):
    """Raised when an acquisition batch cannot be safely accumulated."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _row_key(row):
    if not isinstance(row, dict) or sorted(row.keys()) != sorted(ROW_KEYS):
        raise AccumulationError("MALFORMED_ROW")
    ts = row.get("time")
    if not isinstance(ts, int) or isinstance(ts, bool):
        raise AccumulationError("INVALID_TIMESTAMP")
    return ts


def _index_rows(rows):
    indexed = {}
    for row in rows:
        ts = _row_key(row)
        if ts in indexed:
            if indexed[ts] != row:
                raise AccumulationError("CONFLICTING_DUPLICATE_TIMESTAMP:%d" % ts)
            continue
        indexed[ts] = dict(row)
    return indexed


def batch_identity(rows):
    """Return deterministic identity of canonical ascending rows."""
    indexed = _index_rows(rows)
    ordered = [indexed[t] for t in sorted(indexed)]
    return hashlib.sha256(_canonical(ordered)).hexdigest()


def validate_batch(rows, provenance_records, *, boundary, expected_venue,
                   expected_source, expected_method, expected_symbol,
                   expected_timeframe):
    """Validate one fetched batch before it can enter the accumulator."""
    indexed = _index_rows(rows)
    if any(ts <= int(boundary) for ts in indexed):
        raise AccumulationError("PRE_BOUNDARY_ROW")

    records = list(provenance_records or ())
    by_ts = {}
    for record in records:
        if not isinstance(record, dict):
            raise AccumulationError("MALFORMED_PROVENANCE")
        ts = record.get("time")
        if not isinstance(ts, int) or isinstance(ts, bool):
            raise AccumulationError("INVALID_PROVENANCE_TIMESTAMP")
        if ts in by_ts:
            raise AccumulationError("DUPLICATE_PROVENANCE_TIMESTAMP:%d" % ts)
        by_ts[ts] = record

    if set(by_ts) != set(indexed):
        raise AccumulationError("PROVENANCE_COVERAGE_MISMATCH")

    expected = {
        "venue": str(expected_venue),
        "acquisition_source": str(expected_source),
        "acquisition_method": str(expected_method),
        "symbol": str(expected_symbol),
        "timeframe": str(expected_timeframe),
    }
    for ts, record in by_ts.items():
        for key, value in expected.items():
            if record.get(key) != value:
                raise AccumulationError("PROVENANCE_METADATA_MISMATCH:%s:%d" %
                                        (key, ts))
    return {
        "batch_identity": batch_identity(indexed.values()),
        "row_count": len(indexed),
        "first_timestamp": min(indexed) if indexed else None,
        "last_timestamp": max(indexed) if indexed else None,
    }


def accumulate(existing_rows, incoming_rows, existing_provenance,
               incoming_provenance, *, boundary, expected_venue,
               expected_source, expected_method, expected_symbol,
               expected_timeframe):
    """Safely merge an already-accepted dataset with one new batch.

    Existing and incoming rows are both validated.  Same-timestamp rows are
    accepted only when their complete canonical OHLCV payloads are identical.
    Conflicting observations fail closed.  No gap is filled and no ordering
    is inferred beyond timestamp sorting.
    """
    validate_batch(existing_rows, existing_provenance, boundary=boundary,
                   expected_venue=expected_venue,
                   expected_source=expected_source,
                   expected_method=expected_method,
                   expected_symbol=expected_symbol,
                   expected_timeframe=expected_timeframe)
    incoming_meta = validate_batch(
        incoming_rows, incoming_provenance, boundary=boundary,
        expected_venue=expected_venue, expected_source=expected_source,
        expected_method=expected_method, expected_symbol=expected_symbol,
        expected_timeframe=expected_timeframe)

    old = _index_rows(existing_rows)
    new = _index_rows(incoming_rows)
    added = []
    duplicate = []
    for ts in sorted(new):
        if ts in old:
            if old[ts] != new[ts]:
                raise AccumulationError("CONFLICTING_DUPLICATE_TIMESTAMP:%d" % ts)
            duplicate.append(ts)
        else:
            old[ts] = new[ts]
            added.append(ts)

    merged = [old[t] for t in sorted(old)]
    prov_by_ts = {int(r["time"]): dict(r) for r in existing_provenance}
    for record in incoming_provenance:
        ts = int(record["time"])
        if ts not in prov_by_ts:
            prov_by_ts[ts] = dict(record)
        elif prov_by_ts[ts] != record:
            raise AccumulationError("CONFLICTING_PROVENANCE_TIMESTAMP:%d" % ts)
    merged_provenance = [prov_by_ts[t] for t in sorted(prov_by_ts)]

    return {
        "rows": merged,
        "provenance": merged_provenance,
        "batch_identity": incoming_meta["batch_identity"],
        "added_rows": len(added),
        "identical_duplicates": len(duplicate),
        "total_rows": len(merged),
        "dataset_identity": batch_identity(merged),
    }
