"""11G-E dataset provenance model (immutable record per dataset).

Every research dataset records identity, source, time bounds, counts,
conventions, policies, hashes, transformations, classification,
contamination, phase, and restrictions. A dataset is never FRESH
because a filename says so: freshness requires an explicit
freshness_verdict field set by the governing phase.
"""

from __future__ import annotations

import hashlib
import json

PROVENANCE_FIELDS = ("dataset_id", "source", "provider", "exchange",
                     "instrument", "market_type", "symbol",
                     "timeframe", "start_timestamp", "end_timestamp",
                     "row_count", "timezone", "timestamp_convention",
                     "ordering_convention", "duplicate_policy", "gap_policy",
                     "schema_version", "retrieval_timestamp", "content_hash",
                     "raw_file_hash", "transformation_hash",
                     "transformation_description", "measurement_class",
                     "contamination_status", "intended_phase",
                     "access_restrictions", "freshness_verdict")


def build_provenance(**fields):
    missing = [k for k in PROVENANCE_FIELDS if k not in fields]
    if missing:
        raise ValueError("provenance missing fields: %s" % missing)
    if fields["freshness_verdict"] not in ("FRESH", "CONTAMINATED", "SEALED", "UNKNOWN"):
        raise ValueError("invalid freshness_verdict")
    if fields["measurement_class"] not in ("REAL", "PROXY", "UNAVAILABLE", "MIXED"):
        raise ValueError("invalid measurement_class")
    return dict(fields)


def content_hash(canonical_dicts):
    blob = json.dumps(canonical_dicts, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def transformation_hash(description, code_version):
    blob = json.dumps({"description": description, "code": code_version},
                      sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()
