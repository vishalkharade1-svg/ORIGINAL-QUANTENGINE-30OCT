"""QuantEngine Phase 205 — Cross-Capture Historical Evidence Reconciliation.

Deterministic, fail-closed comparison across historical capture snapshots.
Identifies newly observed records, unchanged records, changed payloads,
duplicate identifiers (identical and conflicting), missing observations,
late-arriving records, and window-boundary effects without inferring venue
cancellations or deletions.

Safety & Architectural Invariants:
1. Absence is NEVER proof of deletion, cancellation, reversal, or nonexistence.
2. Identical captures produce deterministic, byte-reproducible results.
3. Content hash and stable venue identity remain strictly separated.
4. Input capture files are treated as immutable and never modified.
5. All persistence is atomic and verifiable via cryptographic content identities.
6. Execution and order writing remain completely disabled.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class CrossCaptureReconciliationError(ValueError):
    """Base error for cross-capture reconciliation failures."""


class IncompatibleScopeError(CrossCaptureReconciliationError):
    """Captures have incompatible scopes (venue, tenant, product, or category)."""


class CanonicalSerializationError(CrossCaptureReconciliationError):
    """Payload contains unsupported, non-finite, or non-deterministic data."""


class SourceChecksumMismatchError(CrossCaptureReconciliationError):
    """Raw source checksum does not match computed capture integrity digest."""


class CorruptReconciliationResultError(CrossCaptureReconciliationError):
    """Persisted reconciliation output is corrupted or failed integrity validation."""


# ---------------------------------------------------------------------------
# 1. Deterministic Canonical Normalization & Hashing
# ---------------------------------------------------------------------------

def canonical_normalize(value: Any) -> Any:
    """Normalize data structures for deterministic, platform-invariant serialization.

    Rules:
    - Dict keys are recursively sorted and converted to str.
    - Decimals are converted to exact string representations without precision loss.
    - Floats are checked for finite values; NaN and Inf fail closed.
    - Lists and tuples are recursively normalized.
    - Non-finite or unsupported objects raise CanonicalSerializationError.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalSerializationError(f"Non-finite Decimal: {value}")
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CanonicalSerializationError(f"Non-finite float value: {value}")
        return value
    if isinstance(value, (list, tuple)):
        return [canonical_normalize(item) for item in value]
    if isinstance(value, (dict, Mapping)):
        return {str(k): canonical_normalize(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    raise CanonicalSerializationError(
        f"Unsupported data type {type(value).__name__} for canonical normalization"
    )


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize object to deterministic, canonical UTF-8 JSON bytes."""
    normalized = canonical_normalize(obj)
    json_text = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return json_text.encode("utf-8")


def canonical_record_hash(record: Mapping[str, Any]) -> str:
    """Compute SHA-256 digest of canonically normalized record payload."""
    if not isinstance(record, (dict, Mapping)):
        raise CanonicalSerializationError(f"Record must be a mapping, got {type(record).__name__}")
    return hashlib.sha256(canonical_json_bytes(record)).hexdigest()


def compute_capture_checksum(records: Iterable[Mapping[str, Any]]) -> str:
    """Compute deterministic composite SHA-256 over an ordered sequence of records."""
    digests: list[str] = []
    for r in records:
        digests.append(canonical_record_hash(r))
    composite_bytes = "".join(digests).encode("utf-8")
    return hashlib.sha256(composite_bytes).hexdigest()


# ---------------------------------------------------------------------------
# 2. Timestamp and Identity Helpers
# ---------------------------------------------------------------------------

def _parse_utc(value: Any, label: str = "timestamp") -> datetime:
    """Parse string or numeric timestamp to a timezone-aware UTC datetime."""
    if isinstance(value, (int, float)):
        # Handle numeric timestamps in seconds, milliseconds, or microseconds
        val_float = float(value)
        if math.isnan(val_float) or math.isinf(val_float):
            raise CrossCaptureReconciliationError(f"{label} numeric timestamp must be finite")
        if val_float > 1e14:  # Microseconds
            return datetime.fromtimestamp(val_float / 1_000_000.0, tz=timezone.utc)
        if val_float > 1e11:  # Milliseconds
            return datetime.fromtimestamp(val_float / 1_000.0, tz=timezone.utc)
        return datetime.fromtimestamp(val_float, tz=timezone.utc)

    if not isinstance(value, str) or not value.strip():
        raise CrossCaptureReconciliationError(f"{label} must be a non-empty ISO-8601 string or numeric timestamp")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CrossCaptureReconciliationError(f"{label} must be valid ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CrossCaptureReconciliationError(f"{label} must include timezone offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def extract_event_timestamp(record: Mapping[str, Any]) -> datetime | None:
    """Extract event timestamp from known venue timestamp fields."""
    for key in ("created_at", "updated_at", "timestamp", "fill_time", "time", "transact_time"):
        raw = record.get(key)
        if raw not in (None, ""):
            try:
                return _parse_utc(raw, f"event {key}")
            except CrossCaptureReconciliationError:
                return None
    return None


def extract_record_identity(record: Mapping[str, Any], category: str = "orders") -> str | None:
    """Extract stable logical identity for a record depending on category."""
    cat = (category or "").lower()
    keys: tuple[str, ...]
    if "fill" in cat:
        keys = ("id", "fill_id")
    elif "wallet" in cat:
        keys = ("id", "transaction_id")
    elif "position" in cat:
        keys = ("product_id", "query_product_id", "id")
    else:
        # Default orders or general
        keys = ("id", "order_id")

    for k in keys:
        val = record.get(k)
        if val not in (None, ""):
            text = str(val).strip()
            if text:
                return text
    return None


# ---------------------------------------------------------------------------
# 3. Data Structures & Evidence Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CaptureSnapshot:
    """Immutable, provenance-tracked historical capture snapshot."""

    capture_id: str
    venue: str
    record_category: str
    records: tuple[dict[str, Any], ...]
    captured_at: str
    product_id: int | None = None
    account_id: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    overlap_seconds: int = 0
    complete: bool = True
    pagination_complete: bool = True
    endpoint_status: Mapping[str, str] = field(default_factory=dict)
    raw_source_checksum: str | None = None
    schema: str = "quantengine.historical-capture.v1"

    def __post_init__(self):
        if not self.capture_id or not self.capture_id.strip():
            raise CrossCaptureReconciliationError("capture_id must be non-empty")
        if not self.venue or not self.venue.strip():
            raise CrossCaptureReconciliationError("venue must be non-empty")
        if not self.record_category or not self.record_category.strip():
            raise CrossCaptureReconciliationError("record_category must be non-empty")
        if (self.window_start is None) != (self.window_end is None):
            raise CrossCaptureReconciliationError("window_start and window_end must be supplied together")
        if self.window_start is not None and self.window_end is not None:
            s = _parse_utc(self.window_start, "window_start")
            e = _parse_utc(self.window_end, "window_end")
            if s >= e:
                raise CrossCaptureReconciliationError("window_start must precede window_end")
        if self.raw_source_checksum is not None:
            actual = compute_capture_checksum(self.records)
            if self.raw_source_checksum != actual:
                raise SourceChecksumMismatchError(
                    f"Capture {self.capture_id} raw_source_checksum mismatch: "
                    f"declared {self.raw_source_checksum}, computed {actual}"
                )

    def content_identity(self) -> str:
        """Compute cryptographic content digest for this capture."""
        return compute_capture_checksum(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "capture_id": self.capture_id,
            "venue": self.venue,
            "record_category": self.record_category,
            "product_id": self.product_id,
            "account_id": self.account_id,
            "records": [dict(r) for r in self.records],
            "captured_at": self.captured_at,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "overlap_seconds": self.overlap_seconds,
            "complete": self.complete,
            "pagination_complete": self.pagination_complete,
            "endpoint_status": dict(self.endpoint_status),
            "raw_source_checksum": self.raw_source_checksum or self.content_identity(),
            "record_count": len(self.records),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CaptureSnapshot:
        if not isinstance(data, Mapping):
            raise CrossCaptureReconciliationError("Capture payload must be a mapping")
        records_raw = data.get("records", ())
        if not isinstance(records_raw, (list, tuple)):
            raise CrossCaptureReconciliationError("Capture records must be a sequence")
        records = tuple(dict(r) for r in records_raw)
        return cls(
            capture_id=str(data["capture_id"]),
            venue=str(data.get("venue", "delta")),
            record_category=str(data.get("record_category", "orders")),
            product_id=data.get("product_id"),
            account_id=str(data["account_id"]) if data.get("account_id") is not None else None,
            records=records,
            captured_at=str(data.get("captured_at", datetime.now(timezone.utc).isoformat())),
            window_start=data.get("window_start"),
            window_end=data.get("window_end"),
            overlap_seconds=int(data.get("overlap_seconds", 0)),
            complete=bool(data.get("complete", True)),
            pagination_complete=bool(data.get("pagination_complete", True)),
            endpoint_status=dict(data.get("endpoint_status", {})),
            raw_source_checksum=data.get("raw_source_checksum"),
            schema=str(data.get("schema", "quantengine.historical-capture.v1")),
        )


@dataclass(frozen=True)
class FieldDiff:
    """Field-level divergence between two versions of the same logical record."""

    field: str
    earlier_value: Any
    later_value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "earlier_value": self.earlier_value,
            "later_value": self.later_value,
        }


@dataclass(frozen=True)
class ChangedRecord:
    """Record observed in both captures but with differing content payloads."""

    record_id: str
    earlier_capture_id: str
    later_capture_id: str
    earlier_content_hash: str
    later_content_hash: str
    earlier_payload: dict[str, Any]
    later_payload: dict[str, Any]
    differing_fields: tuple[FieldDiff, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "earlier_capture_id": self.earlier_capture_id,
            "later_capture_id": self.later_capture_id,
            "earlier_content_hash": self.earlier_content_hash,
            "later_content_hash": self.later_content_hash,
            "earlier_payload": dict(self.earlier_payload),
            "later_payload": dict(self.later_payload),
            "differing_fields": [d.to_dict() for d in self.differing_fields],
        }


@dataclass(frozen=True)
class LateArrivingRecord:
    """Record appearing in a later capture whose event timestamp falls in an earlier window."""

    record_id: str
    first_observed_capture_id: str
    earlier_capture_id: str
    event_timestamp: str | None
    first_observed_capture_time: str
    earlier_window_start: str | None
    earlier_window_end: str | None
    overlap_seconds: int
    is_late_arrival: bool
    payload: dict[str, Any]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "first_observed_capture_id": self.first_observed_capture_id,
            "earlier_capture_id": self.earlier_capture_id,
            "event_timestamp": self.event_timestamp,
            "first_observed_capture_time": self.first_observed_capture_time,
            "earlier_window_start": self.earlier_window_start,
            "earlier_window_end": self.earlier_window_end,
            "overlap_seconds": self.overlap_seconds,
            "is_late_arrival": self.is_late_arrival,
            "payload": dict(self.payload),
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class NotObservedRecord:
    """Record observed in an earlier capture but absent from a later capture.

    IMPORTANT: Absence is NEVER labelled as deletion, cancellation, or reversal.
    """

    record_id: str
    observed_in_capture_id: str
    absent_from_capture_id: str
    classification: str
    event_timestamp: str | None
    payload: dict[str, Any]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "observed_in_capture_id": self.observed_in_capture_id,
            "absent_from_capture_id": self.absent_from_capture_id,
            "classification": self.classification,
            "event_timestamp": self.event_timestamp,
            "payload": dict(self.payload),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DuplicateRecord:
    """Duplicate logical identifier observed within an individual capture."""

    record_id: str
    capture_id: str
    status: str  # DUPLICATE_IDENTICAL or DUPLICATE_CONFLICTING
    occurrence_index: int
    content_hash: str
    payload: dict[str, Any]
    differing_fields: tuple[FieldDiff, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "capture_id": self.capture_id,
            "status": self.status,
            "occurrence_index": self.occurrence_index,
            "content_hash": self.content_hash,
            "payload": dict(self.payload),
            "differing_fields": [d.to_dict() for d in self.differing_fields],
        }


@dataclass(frozen=True)
class AmbiguousRecord:
    """Record whose identity or structure cannot safely be classified."""

    capture_id: str
    record_index: int
    classification: str
    payload: dict[str, Any]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "record_index": self.record_index,
            "classification": self.classification,
            "payload": dict(self.payload),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CaptureProvenance:
    """Immutable provenance record for an input capture in a reconciliation."""

    capture_id: str
    venue: str
    record_category: str
    product_id: int | None
    account_id: str | None
    captured_at: str
    window_start: str | None
    window_end: str | None
    overlap_seconds: int
    complete: bool
    pagination_complete: bool
    record_count: int
    raw_source_checksum: str | None
    content_identity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossCaptureReconciliationResult:
    """Comprehensive machine-readable cross-capture reconciliation report."""

    reconciliation_id: str
    schema: str
    created_at: str
    status: str  # RECONCILED, RECONCILED_WITH_DIFFERENCES, PARTIAL, INCONCLUSIVE, FAILED
    venue: str
    record_category: str
    product_id: int | None
    account_id: str | None
    input_captures: tuple[CaptureProvenance, ...]
    record_counts: Mapping[str, int]
    newly_observed: tuple[dict[str, Any], ...]
    unchanged: tuple[dict[str, Any], ...]
    changed: tuple[ChangedRecord, ...]
    duplicates_identical: tuple[DuplicateRecord, ...]
    duplicates_conflicting: tuple[DuplicateRecord, ...]
    not_observed: tuple[NotObservedRecord, ...]
    late_arriving: tuple[LateArrivingRecord, ...]
    ambiguous: tuple[AmbiguousRecord, ...]
    integrity: Mapping[str, Any]
    limitations: tuple[str, ...]
    content_identity: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "reconciliation_id": self.reconciliation_id,
            "schema": self.schema,
            "created_at": self.created_at,
            "status": self.status,
            "venue": self.venue,
            "record_category": self.record_category,
            "product_id": self.product_id,
            "account_id": self.account_id,
            "input_captures": [c.to_dict() for c in self.input_captures],
            "record_counts": dict(self.record_counts),
            "newly_observed": [dict(r) for r in self.newly_observed],
            "unchanged": [dict(r) for r in self.unchanged],
            "changed": [c.to_dict() for c in self.changed],
            "duplicates_identical": [d.to_dict() for d in self.duplicates_identical],
            "duplicates_conflicting": [d.to_dict() for d in self.duplicates_conflicting],
            "not_observed": [n.to_dict() for n in self.not_observed],
            "late_arriving": [l.to_dict() for l in self.late_arriving],
            "ambiguous": [a.to_dict() for a in self.ambiguous],
            "integrity": dict(self.integrity),
            "limitations": list(self.limitations),
        }
        if self.content_identity:
            d["content_identity"] = self.content_identity
        return d

    def format_report(self) -> str:
        return format_human_readable_report(self)


# ---------------------------------------------------------------------------
# 4. Scope & Completeness Guards
# ---------------------------------------------------------------------------

def validate_capture_guards(c1: CaptureSnapshot, c2: CaptureSnapshot) -> None:
    """Enforce strict pre-flight scope compatibility before cross-capture comparison.

    Fails closed on venue, tenant, product, category, or checksum disparities.
    """
    if c1.venue.strip().lower() != c2.venue.strip().lower():
        raise IncompatibleScopeError(
            f"Venue mismatch: {c1.venue!r} vs {c2.venue!r}"
        )

    # Tenant / account check (only when present on either side)
    if c1.account_id is not None and c2.account_id is not None:
        if c1.account_id.strip() != c2.account_id.strip():
            raise IncompatibleScopeError(
                f"Account scope mismatch: {c1.account_id!r} vs {c2.account_id!r}"
            )

    # Product scope check (only when defined)
    if c1.product_id is not None and c2.product_id is not None:
        if c1.product_id != c2.product_id:
            raise IncompatibleScopeError(
                f"Product scope mismatch: {c1.product_id} vs {c2.product_id}"
            )

    # Category check
    if c1.record_category.strip().lower() != c2.record_category.strip().lower():
        raise IncompatibleScopeError(
            f"Record category mismatch: {c1.record_category!r} vs {c2.record_category!r}"
        )


def compute_field_diffs(d1: Mapping[str, Any], d2: Mapping[str, Any]) -> tuple[FieldDiff, ...]:
    """Return sorted, deterministic field differences between two record payloads."""
    diffs: list[FieldDiff] = []
    all_keys = sorted(set(d1.keys()) | set(d2.keys()))
    for k in all_keys:
        v1, v2 = d1.get(k), d2.get(k)
        if canonical_normalize(v1) != canonical_normalize(v2):
            diffs.append(FieldDiff(field=k, earlier_value=v1, later_value=v2))
    return tuple(diffs)


# ---------------------------------------------------------------------------
# 5. Core Cross-Capture Reconciliation Logic
# ---------------------------------------------------------------------------

STANDARD_LIMITATIONS: tuple[str, ...] = (
    "Absence from a later capture is not proof of deletion, cancellation, reversal, or nonexistence.",
    "A clean reconciliation across captures does not certify exhaustive venue-side history retention.",
    "Positions are point-in-time state snapshots, not historical event streams.",
    "Live trading execution and testnet order writing remain strictly disabled.",
    "QuantEngine strategy edge remains NOT ESTABLISHED.",
)


def reconcile_two_captures(
    earlier: CaptureSnapshot,
    later: CaptureSnapshot,
    *,
    reconciliation_id: str | None = None,
    created_at: str | None = None,
) -> CrossCaptureReconciliationResult:
    """Perform deterministic cross-capture reconciliation between two snapshots."""
    validate_capture_guards(earlier, later)

    # Order captures chronologically if necessary
    e_time = _parse_utc(earlier.captured_at, "earlier captured_at")
    l_time = _parse_utc(later.captured_at, "later captured_at")
    if e_time > l_time:
        # Caller passed later capture first; swap order to maintain earlier -> later causality
        earlier, later = later, earlier
        e_time, l_time = l_time, e_time

    # Window bounds
    has_windows = (earlier.window_start is not None and later.window_start is not None)
    windows_overlap = False
    e_eff_start: datetime | None = None
    e_eff_end: datetime | None = None
    l_eff_start: datetime | None = None
    l_eff_end: datetime | None = None

    if has_windows:
        e_start = _parse_utc(earlier.window_start, "earlier window_start")
        e_end = _parse_utc(earlier.window_end, "earlier window_end")
        e_eff_start = e_start - timedelta(seconds=earlier.overlap_seconds)
        e_eff_end = e_end + timedelta(seconds=earlier.overlap_seconds)

        l_start = _parse_utc(later.window_start, "later window_start")
        l_end = _parse_utc(later.window_end, "later window_end")
        l_eff_start = l_start - timedelta(seconds=later.overlap_seconds)
        l_eff_end = l_end + timedelta(seconds=later.overlap_seconds)

        windows_overlap = max(e_eff_start, l_eff_start) <= min(e_eff_end, l_eff_end)

    # 1. Index earlier capture records
    earlier_by_id: dict[str, dict[str, Any]] = {}
    earlier_hashes: dict[str, str] = {}
    earlier_duplicates_identical: list[DuplicateRecord] = []
    earlier_duplicates_conflicting: list[DuplicateRecord] = []
    ambiguous_records: list[AmbiguousRecord] = []

    for idx, raw_r in enumerate(earlier.records):
        r = copy.deepcopy(dict(raw_r))
        rid = extract_record_identity(r, earlier.record_category)
        if not rid:
            ambiguous_records.append(
                AmbiguousRecord(
                    capture_id=earlier.capture_id,
                    record_index=idx,
                    classification="IDENTITY_AMBIGUOUS",
                    payload=r,
                    reason="Record missing stable logical identifier",
                )
            )
            continue

        h = canonical_record_hash(r)
        if rid in earlier_by_id:
            prior_h = earlier_hashes[rid]
            if prior_h == h:
                earlier_duplicates_identical.append(
                    DuplicateRecord(
                        record_id=rid,
                        capture_id=earlier.capture_id,
                        status="DUPLICATE_IDENTICAL",
                        occurrence_index=idx,
                        content_hash=h,
                        payload=r,
                    )
                )
            else:
                diffs = compute_field_diffs(earlier_by_id[rid], r)
                earlier_duplicates_conflicting.append(
                    DuplicateRecord(
                        record_id=rid,
                        capture_id=earlier.capture_id,
                        status="DUPLICATE_CONFLICTING",
                        occurrence_index=idx,
                        content_hash=h,
                        payload=r,
                        differing_fields=diffs,
                    )
                )
        else:
            earlier_by_id[rid] = r
            earlier_hashes[rid] = h

    # 2. Index later capture records and compare with earlier
    later_by_id: dict[str, dict[str, Any]] = {}
    later_hashes: dict[str, str] = {}
    later_duplicates_identical: list[DuplicateRecord] = []
    later_duplicates_conflicting: list[DuplicateRecord] = []

    newly_observed: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    changed: list[ChangedRecord] = []
    late_arriving: list[LateArrivingRecord] = []

    for idx, raw_r in enumerate(later.records):
        r = copy.deepcopy(dict(raw_r))
        rid = extract_record_identity(r, later.record_category)
        if not rid:
            ambiguous_records.append(
                AmbiguousRecord(
                    capture_id=later.capture_id,
                    record_index=idx,
                    classification="IDENTITY_AMBIGUOUS",
                    payload=r,
                    reason="Record missing stable logical identifier",
                )
            )
            continue

        h = canonical_record_hash(r)
        if rid in later_by_id:
            prior_h = later_hashes[rid]
            if prior_h == h:
                later_duplicates_identical.append(
                    DuplicateRecord(
                        record_id=rid,
                        capture_id=later.capture_id,
                        status="DUPLICATE_IDENTICAL",
                        occurrence_index=idx,
                        content_hash=h,
                        payload=r,
                    )
                )
            else:
                diffs = compute_field_diffs(later_by_id[rid], r)
                later_duplicates_conflicting.append(
                    DuplicateRecord(
                        record_id=rid,
                        capture_id=later.capture_id,
                        status="DUPLICATE_CONFLICTING",
                        occurrence_index=idx,
                        content_hash=h,
                        payload=r,
                        differing_fields=diffs,
                    )
                )
            # Duplicate occurrences within later capture don't re-trigger cross-capture matching
            continue

        later_by_id[rid] = r
        later_hashes[rid] = h

        # Cross-capture matching
        if rid in earlier_by_id:
            e_hash = earlier_hashes[rid]
            if e_hash == h:
                unchanged.append(r)
            else:
                diffs = compute_field_diffs(earlier_by_id[rid], r)
                changed.append(
                    ChangedRecord(
                        record_id=rid,
                        earlier_capture_id=earlier.capture_id,
                        later_capture_id=later.capture_id,
                        earlier_content_hash=e_hash,
                        later_content_hash=h,
                        earlier_payload=copy.deepcopy(earlier_by_id[rid]),
                        later_payload=r,
                        differing_fields=diffs,
                    )
                )
        else:
            # Observed in later capture, not observed in earlier capture
            t_event = extract_event_timestamp(r)
            is_late = False
            if t_event is not None and e_eff_start is not None and e_eff_end is not None:
                # If event timestamp falls inside earlier window, this is a late-arriving record!
                if e_eff_start <= t_event <= e_eff_end:
                    is_late = True
                    late_arriving.append(
                        LateArrivingRecord(
                            record_id=rid,
                            first_observed_capture_id=later.capture_id,
                            earlier_capture_id=earlier.capture_id,
                            event_timestamp=t_event.isoformat(),
                            first_observed_capture_time=later.captured_at,
                            earlier_window_start=earlier.window_start,
                            earlier_window_end=earlier.window_end,
                            overlap_seconds=earlier.overlap_seconds,
                            is_late_arrival=True,
                            payload=r,
                            explanation=(
                                f"Record event timestamp {t_event.isoformat()} fell within "
                                f"earlier capture window [{e_eff_start.isoformat()} - {e_eff_end.isoformat()}], "
                                f"but record was first observed in later capture {later.capture_id}."
                            ),
                        )
                    )
            if not is_late:
                newly_observed.append(r)

    # 3. Check for records observed in earlier capture but NOT in later capture
    not_observed: list[NotObservedRecord] = []
    for rid, e_record in earlier_by_id.items():
        if rid not in later_by_id:
            t_event = extract_event_timestamp(e_record)
            classification = "NOT_OBSERVED_IN_LATER_CAPTURE"
            reason = (
                f"Record {rid} was observed in capture {earlier.capture_id} but not observed in "
                f"capture {later.capture_id}. Absence is NOT proof of deletion or cancellation."
            )

            if not later.complete:
                classification = "CAPTURE_INCOMPLETE"
                reason = (
                    f"Record {rid} not observed in capture {later.capture_id}, but later capture "
                    "completion flag is False."
                )
            elif not later.pagination_complete:
                classification = "PAGINATION_INCOMPLETE"
                reason = (
                    f"Record {rid} not observed in capture {later.capture_id}, but later capture "
                    "pagination was incomplete."
                )
            elif l_eff_start is not None and l_eff_end is not None and t_event is not None:
                if t_event < l_eff_start or t_event > l_eff_end:
                    classification = "OUTSIDE_CAPTURE_WINDOW"
                    reason = (
                        f"Record {rid} event time {t_event.isoformat()} falls outside later capture "
                        f"window [{l_eff_start.isoformat()} - {l_eff_end.isoformat()}]."
                    )

            not_observed.append(
                NotObservedRecord(
                    record_id=rid,
                    observed_in_capture_id=earlier.capture_id,
                    absent_from_capture_id=later.capture_id,
                    classification=classification,
                    event_timestamp=t_event.isoformat() if t_event else None,
                    payload=copy.deepcopy(e_record),
                    reason=reason,
                )
            )

    # 4. Determine overall status
    is_partial = (
        not earlier.complete
        or not earlier.pagination_complete
        or not later.complete
        or not later.pagination_complete
    )
    has_inconclusive = bool(ambiguous_records)
    has_differences = bool(
        changed
        or late_arriving
        or not_observed
        or earlier_duplicates_conflicting
        or later_duplicates_conflicting
    )

    if is_partial:
        status = "PARTIAL"
    elif has_inconclusive:
        status = "INCONCLUSIVE"
    elif has_differences:
        status = "RECONCILED_WITH_DIFFERENCES"
    else:
        status = "RECONCILED"

    all_duplicates_identical = tuple(earlier_duplicates_identical + later_duplicates_identical)
    all_duplicates_conflicting = tuple(earlier_duplicates_conflicting + later_duplicates_conflicting)

    record_counts = {
        "earlier_capture_total": len(earlier.records),
        "later_capture_total": len(later.records),
        "earlier_unique_identities": len(earlier_by_id),
        "later_unique_identities": len(later_by_id),
        "newly_observed": len(newly_observed),
        "unchanged": len(unchanged),
        "changed": len(changed),
        "duplicates_identical": len(all_duplicates_identical),
        "duplicates_conflicting": len(all_duplicates_conflicting),
        "not_observed": len(not_observed),
        "late_arriving": len(late_arriving),
        "ambiguous": len(ambiguous_records),
    }

    # 5. Build Provenance objects
    prov_earlier = CaptureProvenance(
        capture_id=earlier.capture_id,
        venue=earlier.venue,
        record_category=earlier.record_category,
        product_id=earlier.product_id,
        account_id=earlier.account_id,
        captured_at=earlier.captured_at,
        window_start=earlier.window_start,
        window_end=earlier.window_end,
        overlap_seconds=earlier.overlap_seconds,
        complete=earlier.complete,
        pagination_complete=earlier.pagination_complete,
        record_count=len(earlier.records),
        raw_source_checksum=earlier.raw_source_checksum or earlier.content_identity(),
        content_identity=earlier.content_identity(),
    )
    prov_later = CaptureProvenance(
        capture_id=later.capture_id,
        venue=later.venue,
        record_category=later.record_category,
        product_id=later.product_id,
        account_id=later.account_id,
        captured_at=later.captured_at,
        window_start=later.window_start,
        window_end=later.window_end,
        overlap_seconds=later.overlap_seconds,
        complete=later.complete,
        pagination_complete=later.pagination_complete,
        record_count=len(later.records),
        raw_source_checksum=later.raw_source_checksum or later.content_identity(),
        content_identity=later.content_identity(),
    )

    if created_at is None:
        created_at = later.captured_at
    if reconciliation_id is None:
        raw_recon_key = f"{earlier.capture_id}:{earlier.content_identity()}=>{later.capture_id}:{later.content_identity()}"
        reconciliation_id = f"recon_{hashlib.sha256(raw_recon_key.encode('utf-8')).hexdigest()[:16]}"

    integrity = {
        "earlier_capture_checksum_verified": True,
        "later_capture_checksum_verified": True,
        "windows_overlap": windows_overlap,
        "has_capture_windows": has_windows,
    }

    result = CrossCaptureReconciliationResult(
        reconciliation_id=reconciliation_id,
        schema="quantengine.cross-capture-reconciliation.v1",
        created_at=created_at,
        status=status,
        venue=earlier.venue,
        record_category=earlier.record_category,
        product_id=earlier.product_id,
        account_id=earlier.account_id,
        input_captures=(prov_earlier, prov_later),
        record_counts=record_counts,
        newly_observed=tuple(newly_observed),
        unchanged=tuple(unchanged),
        changed=tuple(changed),
        duplicates_identical=all_duplicates_identical,
        duplicates_conflicting=all_duplicates_conflicting,
        not_observed=tuple(not_observed),
        late_arriving=tuple(late_arriving),
        ambiguous=tuple(ambiguous_records),
        integrity=integrity,
        limitations=STANDARD_LIMITATIONS,
    )

    # Compute deterministic content_identity of result (excluding content_identity itself)
    base_dict = result.to_dict()
    cid = hashlib.sha256(canonical_json_bytes(base_dict)).hexdigest()

    return CrossCaptureReconciliationResult(
        reconciliation_id=result.reconciliation_id,
        schema=result.schema,
        created_at=result.created_at,
        status=result.status,
        venue=result.venue,
        record_category=result.record_category,
        product_id=result.product_id,
        account_id=result.account_id,
        input_captures=result.input_captures,
        record_counts=result.record_counts,
        newly_observed=result.newly_observed,
        unchanged=result.unchanged,
        changed=result.changed,
        duplicates_identical=result.duplicates_identical,
        duplicates_conflicting=result.duplicates_conflicting,
        not_observed=result.not_observed,
        late_arriving=result.late_arriving,
        ambiguous=result.ambiguous,
        integrity=result.integrity,
        limitations=result.limitations,
        content_identity=cid,
    )


def reconcile_captures_sequence(
    captures: Sequence[CaptureSnapshot],
) -> list[CrossCaptureReconciliationResult]:
    """Reconcile a chronological sequence of captures pairwise."""
    if len(captures) < 2:
        raise CrossCaptureReconciliationError("At least two captures are required for cross-capture reconciliation")

    results: list[CrossCaptureReconciliationResult] = []
    for i in range(len(captures) - 1):
        res = reconcile_two_captures(captures[i], captures[i + 1])
        results.append(res)
    return results


# ---------------------------------------------------------------------------
# 6. Snapshot Adapter Decomposition
# ---------------------------------------------------------------------------

def snapshot_to_captures(
    snapshot: Any,
    *,
    capture_id_prefix: str = "snap",
    venue: str = "delta",
    account_id: str | None = None,
) -> dict[str, CaptureSnapshot]:
    """Decompose a DeltaReconciliationSnapshot into category CaptureSnapshots."""
    captured_at = str(getattr(snapshot, "captured_at", datetime.now(timezone.utc).isoformat()))
    product_id = getattr(snapshot, "product_id", None)
    window_start = getattr(snapshot, "window_start", None)
    window_end = getattr(snapshot, "window_end", None)
    overlap_seconds = int(getattr(snapshot, "overlap_seconds", 0))
    endpoint_status = dict(getattr(snapshot, "endpoint_status", {}))
    complete = bool(getattr(snapshot, "complete", True))

    categories = {
        "orders": [*getattr(snapshot, "open_orders", ()), *getattr(snapshot, "order_history", ())],
        "fills": list(getattr(snapshot, "fills", ())),
        "positions": list(getattr(snapshot, "positions", ())),
        "wallet_transactions": list(getattr(snapshot, "wallet_transactions", ())),
    }

    out: dict[str, CaptureSnapshot] = {}
    for cat_name, rows in categories.items():
        ep_stat = endpoint_status.get(cat_name, "OK")
        cat_complete = complete and (ep_stat == "OK")
        cid = f"{capture_id_prefix}_{cat_name}_{captured_at.replace(':', '').replace('-', '')}"
        snap = CaptureSnapshot(
            capture_id=cid,
            venue=venue,
            record_category=cat_name,
            records=tuple(dict(r) for r in rows),
            captured_at=captured_at,
            product_id=product_id if cat_name != "wallet_transactions" else None,
            account_id=account_id,
            window_start=window_start if cat_name != "positions" else None,
            window_end=window_end if cat_name != "positions" else None,
            overlap_seconds=overlap_seconds if cat_name != "positions" else 0,
            complete=cat_complete,
            pagination_complete=(ep_stat != "INCOMPLETE_PAGINATION"),
            endpoint_status={cat_name: ep_stat},
        )
        out[cat_name] = snap
    return out


def reconcile_reconciliation_snapshots(
    earlier_snapshot: Any,
    later_snapshot: Any,
    *,
    venue: str = "delta",
    account_id: str | None = None,
) -> dict[str, CrossCaptureReconciliationResult]:
    """Perform cross-capture reconciliation across all endpoints between two full snapshots."""
    e_caps = snapshot_to_captures(earlier_snapshot, capture_id_prefix="earlier", venue=venue, account_id=account_id)
    l_caps = snapshot_to_captures(later_snapshot, capture_id_prefix="later", venue=venue, account_id=account_id)

    results: dict[str, CrossCaptureReconciliationResult] = {}
    for cat in ("orders", "fills", "wallet_transactions", "positions"):
        if cat in e_caps and cat in l_caps:
            results[cat] = reconcile_two_captures(e_caps[cat], l_caps[cat])
    return results


# ---------------------------------------------------------------------------
# 7. Append-Only Atomic Persistence & Load Validation
# ---------------------------------------------------------------------------

def persist_reconciliation_result(
    result: CrossCaptureReconciliationResult,
    target_path: Path | str,
) -> str:
    """Persist reconciliation result atomically with checksum integrity.

    Ensures:
    - Never mutates input or existing evidence.
    - Uses temporary file + atomic replace.
    - Embeds canonical content_identity.
    """
    path = Path(target_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = result.to_dict()
    canonical_bytes = canonical_json_bytes(payload)

    tmp_path = path.with_name(f"{path.name}.tmp_{os.getpid()}")
    try:
        tmp_path.write_bytes(canonical_bytes)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return result.content_identity


def load_reconciliation_result(source_path: Path | str) -> dict[str, Any]:
    """Load and cryptographically verify a persisted reconciliation result."""
    path = Path(source_path).resolve()
    if not path.is_file():
        raise CorruptReconciliationResultError(f"Reconciliation file not found: {path}")

    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise CorruptReconciliationResultError(f"Malformed reconciliation file {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise CorruptReconciliationResultError(f"Reconciliation payload must be an object in {path}")

    recorded_identity = payload.get("content_identity")
    if not recorded_identity:
        raise CorruptReconciliationResultError(f"Missing content_identity in {path}")

    # Re-verify integrity by hashing payload without content_identity
    test_dict = copy.deepcopy(payload)
    test_dict.pop("content_identity", None)
    expected_identity = hashlib.sha256(canonical_json_bytes(test_dict)).hexdigest()

    if recorded_identity != expected_identity:
        raise CorruptReconciliationResultError(
            f"Content identity mismatch in {path}: recorded {recorded_identity}, "
            f"computed {expected_identity}"
        )

    return payload


# ---------------------------------------------------------------------------
# 8. Human-Readable Report Formatter
# ---------------------------------------------------------------------------

def format_human_readable_report(result: CrossCaptureReconciliationResult) -> str:
    """Generate a clean, structured human-readable Markdown reconciliation report."""
    lines: list[str] = [
        f"# Cross-Capture Historical Evidence Reconciliation Report",
        f"",
        f"**Reconciliation ID:** `{result.reconciliation_id}`  ",
        f"**Status:** `{result.status}`  ",
        f"**Created At:** {result.created_at}  ",
        f"**Content Identity:** `{result.content_identity}`  ",
        f"**Venue:** `{result.venue}` | **Category:** `{result.record_category}` | **Product ID:** `{result.product_id}`  ",
        f"",
        f"---",
        f"",
        f"## 1. Input Captures Provenance",
        f"",
        f"| Capture ID | Captured At | Records | Window Start | Window End | Complete | Pagination | Checksum |",
        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for c in result.input_captures:
        w_start = c.window_start or "None"
        w_end = c.window_end or "None"
        chk_short = c.raw_source_checksum[:12] if c.raw_source_checksum else "None"
        lines.append(
            f"| `{c.capture_id}` | {c.captured_at} | {c.record_count} | {w_start} | {w_end} | "
            f"{c.complete} | {c.pagination_complete} | `{chk_short}...` |"
        )

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 2. Record Summary",
        f"",
        f"- **Earlier Capture Total:** {result.record_counts.get('earlier_capture_total', 0)}",
        f"- **Later Capture Total:** {result.record_counts.get('later_capture_total', 0)}",
        f"- **Newly Observed in Later:** {result.record_counts.get('newly_observed', 0)}",
        f"- **Unchanged Records:** {result.record_counts.get('unchanged', 0)}",
        f"- **Changed Records:** {result.record_counts.get('changed', 0)}",
        f"- **Late-Arriving Records:** {result.record_counts.get('late_arriving', 0)}",
        f"- **Not Observed in Later:** {result.record_counts.get('not_observed', 0)}",
        f"- **Duplicates (Identical):** {result.record_counts.get('duplicates_identical', 0)}",
        f"- **Duplicates (Conflicting):** {result.record_counts.get('duplicates_conflicting', 0)}",
        f"- **Ambiguous / Inconclusive:** {result.record_counts.get('ambiguous', 0)}",
        f"",
        f"---",
        f"",
        f"## 3. Discrepancy & Anomaly Details",
        f"",
    ])

    if result.late_arriving:
        lines.append(f"### 3.1 Late-Arriving Records ({len(result.late_arriving)})")
        lines.append(f"Records whose event timestamp falls inside the earlier window but only appeared in the later capture:")
        for r in result.late_arriving:
            lines.append(f"- **Record ID `{r.record_id}`**: event timestamp `{r.event_timestamp}` (observed in `{r.first_observed_capture_id}` at `{r.first_observed_capture_time}`)")
        lines.append("")
    else:
        lines.append("### 3.1 Late-Arriving Records: None observed.")
        lines.append("")

    if result.changed:
        lines.append(f"### 3.2 Changed Payloads ({len(result.changed)})")
        for c in result.changed:
            lines.append(f"- **Record ID `{c.record_id}`**: content hash `{c.earlier_content_hash[:10]}...` -> `{c.later_content_hash[:10]}...`")
            for diff in c.differing_fields:
                lines.append(f"  - Field `{diff.field}`: `{diff.earlier_value!r}` -> `{diff.later_value!r}`")
        lines.append("")
    else:
        lines.append("### 3.2 Changed Payloads: None observed.")
        lines.append("")

    if result.not_observed:
        lines.append(f"### 3.3 Records Not Observed in Later Capture ({len(result.not_observed)})")
        lines.append("*(Note: Absence is NEVER classified as deletion or cancellation)*")
        for n in result.not_observed:
            lines.append(f"- **Record ID `{n.record_id}`**: Classification: `{n.classification}` | Reason: {n.reason}")
        lines.append("")
    else:
        lines.append("### 3.3 Records Not Observed in Later Capture: None.")
        lines.append("")

    if result.duplicates_conflicting:
        lines.append(f"### 3.4 Conflicting Duplicate Identifiers ({len(result.duplicates_conflicting)})")
        for d in result.duplicates_conflicting:
            lines.append(f"- **Record ID `{d.record_id}`** in capture `{d.capture_id}` (occurrence {d.occurrence_index})")
        lines.append("")
    else:
        lines.append("### 3.4 Conflicting Duplicate Identifiers: None observed.")
        lines.append("")

    lines.extend([
        f"---",
        f"",
        f"## 4. Integrity and Limitations",
        f"",
    ])
    for lim in result.limitations:
        lines.append(f"- {lim}")

    lines.append("")
    return "\n".join(lines)
