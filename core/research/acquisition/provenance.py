"""
====================================================

QuantEngine -- Phase 17 dataset provenance manifest.

Research-only, deterministic, stdlib-only. One frozen
manifest per acquired dataset covering the mandated
provenance fields. The deterministic manifest_id covers
the CANONICAL subset only: the operational fetched_at
timestamp is recorded for operations but NEVER enters
the id or any research comparison.

Reuses the frozen 11G content_hash (sha256 over the
canonical JSON form) -- no new hashing system.
====================================================
"""

from __future__ import annotations

import dataclasses

from research.phase11g.provenance.model import content_hash

# §13 mandated provenance fields (canonical, hashed).
CANONICAL_FIELDS = (
    "venue",
    "market",
    "instrument",
    "symbol",
    "timeframe",
    "acquisition_source",
    "acquisition_method",
    "requested_start",
    "requested_end",
    "actual_start",
    "actual_end",
    "row_count",
    "schema_version",
    "normalization_version",
    "dataset_hash",
    "acquisition_status",
)

# Closed acquisition-status vocabulary (gate words only).
ACQUISITION_STATUSES = (
    "COMPLETE",
    "PARTIAL",
    "EMPTY",
    "BLOCKED",
)


@dataclasses.dataclass(frozen=True)
class ProvenanceManifest:
    """Immutable provenance record for one dataset.

    fetched_at is operational metadata (wall-clock) and is
    EXCLUDED from canonical_dict()/manifest_id().
    """

    venue: str
    market: str
    instrument: str
    symbol: str
    timeframe: str
    acquisition_source: str
    acquisition_method: str
    requested_start: int
    requested_end: int
    actual_start: int | None
    actual_end: int | None
    row_count: int
    schema_version: str
    normalization_version: str
    dataset_hash: str
    acquisition_status: str
    fetched_at: str = ""

    def __post_init__(self):
        if self.acquisition_status not in ACQUISITION_STATUSES:
            raise ValueError(
                "unknown acquisition_status: %r" % self.acquisition_status)
        if int(self.row_count) < 0:
            raise ValueError("row_count must be >= 0")

    def canonical_dict(self):
        """Hash-covered subset: no wall-clock, no operations."""
        return {k: getattr(self, k) for k in CANONICAL_FIELDS}

    def manifest_id(self):
        return manifest_id(self.canonical_dict())


def manifest_id(canonical):
    """Deterministic sha256 over the canonical mapping."""
    unknown = set(canonical) - set(CANONICAL_FIELDS)
    if unknown:
        raise ValueError("non-canonical fields: %s" % sorted(unknown))
    missing = [k for k in CANONICAL_FIELDS if k not in canonical]
    if missing:
        raise ValueError("missing canonical fields: %s" % missing)
    return content_hash(canonical)
