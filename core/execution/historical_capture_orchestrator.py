"""Phase 206 bounded, read-only historical recapture orchestration.

This layer coordinates the existing Delta reconciliation read adapter and
Phase 205 CaptureSnapshot/reconciliation primitives. It never performs writes
to an exchange. Real authenticated collection is denied unless an explicit
owner authorization callback is supplied by trusted application code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid5, NAMESPACE_URL

from core.execution.cross_capture_reconciliation import (
    CaptureSnapshot,
    IncompatibleScopeError,
    canonical_json_bytes,
    compute_capture_checksum,
    reconcile_two_captures,
)


class CapturePlanError(ValueError):
    """A capture plan is invalid or exceeds configured safety bounds."""


class CaptureAuthorizationError(PermissionError):
    """A real authenticated capture lacks trusted owner authorization."""


class CapturePersistenceError(RuntimeError):
    """A capture artifact could not be persisted safely."""


@dataclass(frozen=True)
class CaptureWindow:
    start: datetime
    end: datetime

    def as_iso(self) -> tuple[str, str]:
        return (self.start.isoformat().replace("+00:00", "Z"),
                self.end.isoformat().replace("+00:00", "Z"))


@dataclass(frozen=True)
class HistoricalCapturePlan:
    venue: str
    tenant_id: str
    account_id: str
    product_id: int
    start: str
    end: str
    window_seconds: int = 3600
    overlap_seconds: int = 60
    repeat_count: int = 1
    max_windows: int = 48
    max_records_per_snapshot: int = 10000
    max_total_records: int = 100000
    max_capture_runs: int = 48
    interval_seconds: int = 0
    mode: str = "fixture"
    owner_authorized: bool = False
    plan_id: str | None = None

    def validate(self) -> tuple[datetime, datetime]:
        if self.venue.lower() != "delta":
            raise CapturePlanError("only the existing Delta reconciliation adapter is supported")
        for name, value in (("tenant_id", self.tenant_id), ("account_id", self.account_id)):
            if not isinstance(value, str) or not value.strip():
                raise CapturePlanError(f"{name} is required; unknown scope is not accepted")
        if isinstance(self.product_id, bool) or not isinstance(self.product_id, int) or self.product_id <= 0:
            raise CapturePlanError("product_id must be a positive integer")
        start, end = _utc(self.start, "start"), _utc(self.end, "end")
        if start >= end:
            raise CapturePlanError("start must precede end")
        if end - start > timedelta(days=14):
            raise CapturePlanError("historical horizon cannot exceed 14 days")
        if isinstance(self.window_seconds, bool) or not 60 <= self.window_seconds <= 86400:
            raise CapturePlanError("window_seconds must be between 60 and 86400")
        if isinstance(self.overlap_seconds, bool) or not 0 <= self.overlap_seconds <= min(3600, self.window_seconds // 2):
            raise CapturePlanError("overlap_seconds exceeds the safe window bound")
        if isinstance(self.repeat_count, bool) or not 1 <= self.repeat_count <= 10:
            raise CapturePlanError("repeat_count must be between 1 and 10")
        if isinstance(self.max_windows, bool) or not 1 <= self.max_windows <= 500:
            raise CapturePlanError("max_windows must be between 1 and 500")
        if isinstance(self.max_records_per_snapshot, bool) or not 1 <= self.max_records_per_snapshot <= 100000:
            raise CapturePlanError("max_records_per_snapshot must be between 1 and 100000")
        if isinstance(self.max_total_records, bool) or not 1 <= self.max_total_records <= 1000000:
            raise CapturePlanError("max_total_records must be between 1 and 1000000")
        if isinstance(self.max_capture_runs, bool) or not 1 <= self.max_capture_runs <= 5000:
            raise CapturePlanError("max_capture_runs must be between 1 and 5000")
        if isinstance(self.interval_seconds, bool) or not 0 <= self.interval_seconds <= 86400:
            raise CapturePlanError("interval_seconds must be between 0 and 86400")
        if self.mode not in {"fixture", "authenticated"}:
            raise CapturePlanError("mode must be fixture or authenticated")
        if self.mode == "authenticated" and self.owner_authorized is not True:
            raise CaptureAuthorizationError("authenticated capture requires trusted owner authorization")
        if self.mode == "fixture" and self.interval_seconds:
            raise CapturePlanError("fixture mode cannot schedule delayed repeated captures")
        return start, end


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CapturePlanError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise CapturePlanError(f"{label} must be valid ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapturePlanError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def generate_windows(plan: HistoricalCapturePlan) -> tuple[CaptureWindow, ...]:
    start, end = plan.validate()
    step = timedelta(seconds=plan.window_seconds - plan.overlap_seconds)
    width = timedelta(seconds=plan.window_seconds)
    windows: list[CaptureWindow] = []
    cursor = start
    while cursor < end:
        if len(windows) >= plan.max_windows:
            raise CapturePlanError("maximum window budget exceeded")
        window_end = min(cursor + width, end)
        windows.append(CaptureWindow(cursor, window_end))
        if window_end == end:
            break
        cursor += step
    return tuple(windows)


def _snapshot_records(snapshot: Any) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for name in ("open_orders", "order_history", "fills", "positions", "wallet_transactions"):
        value = getattr(snapshot, name, ())
        rows.extend(dict(row) for row in value)
    return tuple(rows)


def _snapshot_status(snapshot: Any) -> tuple[bool, Mapping[str, str]]:
    status = dict(getattr(snapshot, "endpoint_status", {}) or {})
    complete = bool(getattr(snapshot, "complete", False))
    # A snapshot is complete only when all declared endpoints are explicitly OK.
    if not status or any(value != "OK" for value in status.values()):
        complete = False
    return complete, status


def _safe_json_write(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json_bytes(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    target = path.with_suffix(path.suffix + ".json")
    # O_EXCL makes an existing evidence artifact immutable.
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() == digest:
            return digest
        raise CapturePersistenceError("capture artifact already exists with different content") from None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    return digest


class DeltaCaptureAdapter(Protocol):
    def capture(self, *, product_id: int, window_start: str, window_end: str,
                overlap_seconds: int = 60) -> Any: ...


@dataclass
class CaptureRunResult:
    plan_id: str
    status: str
    snapshots: list[CaptureSnapshot] = field(default_factory=list)
    reconciliation_reports: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requested_windows: int = 0
    completed_windows: int = 0
    total_records: int = 0


class HistoricalCaptureOrchestrator:
    """Bounded coordinator over the existing authenticated GET-only adapter."""

    def __init__(self, adapter: DeltaCaptureAdapter, storage_root: str | Path,
                 *, owner_authorizer: Callable[[HistoricalCapturePlan], bool] | None = None,
                 clock: Callable[[], datetime] | None = None,
                 sleeper: Callable[[float], None] = time.sleep):
        self._adapter = adapter
        self._root = Path(storage_root)
        self._owner_authorizer = owner_authorizer
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleeper

    def run(self, plan: HistoricalCapturePlan) -> CaptureRunResult:
        windows = generate_windows(plan)
        if plan.mode == "authenticated":
            if self._owner_authorizer is None or self._owner_authorizer(plan) is not True:
                raise CaptureAuthorizationError("trusted owner authorization callback denied capture")
            if not bool(getattr(getattr(self._adapter, "_rest", None), "authenticated", False)):
                raise CaptureAuthorizationError("authenticated Delta REST client is not available")
        plan_id = plan.plan_id or str(uuid5(NAMESPACE_URL, canonical_json_bytes({
            "venue": plan.venue, "tenant": plan.tenant_id, "account": plan.account_id,
            "product": plan.product_id, "start": plan.start, "end": plan.end,
            "window_seconds": plan.window_seconds, "overlap_seconds": plan.overlap_seconds,
        }).decode("utf-8")))
        result = CaptureRunResult(plan_id=plan_id, status="COMPLETE", requested_windows=len(windows))
        prior_by_window: dict[str, CaptureSnapshot] = {}
        run_count = 0
        for repeat in range(plan.repeat_count):
            for index, window in enumerate(windows):
                run_count += 1
                if run_count > plan.max_capture_runs:
                    result.status = "PARTIAL"
                    result.errors.append("MAX_CAPTURE_RUNS_REACHED")
                    return result
                start_iso, end_iso = window.as_iso()
                try:
                    raw = self._adapter.capture(
                        product_id=plan.product_id, window_start=start_iso,
                        window_end=end_iso, overlap_seconds=plan.overlap_seconds,
                    )
                    records = _snapshot_records(raw)
                    if len(records) > plan.max_records_per_snapshot:
                        raise CapturePlanError("MAX_RECORDS_PER_SNAPSHOT_REACHED")
                    if result.total_records + len(records) > plan.max_total_records:
                        raise CapturePlanError("MAX_TOTAL_RECORDS_REACHED")
                    complete, endpoint_status = _snapshot_status(raw)
                    captured_at = str(getattr(raw, "captured_at", self._clock().isoformat()))
                    capture_id = str(uuid5(NAMESPACE_URL, f"{plan_id}:{repeat}:{index}:{captured_at}"))
                    capture = CaptureSnapshot(
                        capture_id=capture_id, venue=plan.venue,
                        record_category="delta_reconciliation_bundle", records=records,
                        captured_at=captured_at, product_id=plan.product_id,
                        account_id=plan.account_id, window_start=start_iso, window_end=end_iso,
                        overlap_seconds=plan.overlap_seconds, complete=complete,
                        pagination_complete=complete, endpoint_status=endpoint_status,
                    )
                    payload = {
                        "schema": "quantengine.phase206.capture.v1",
                        "plan_id": plan_id, "tenant_id": plan.tenant_id,
                        "capture": capture.to_dict(),
                        "capture_status": "COMPLETE" if complete else "PARTIAL",
                        "page_provenance": "NOT_EXPOSED_BY_PHASE199_ADAPTER",
                    }
                    checksum = _safe_json_write(self._root / plan_id / capture_id, payload)
                    capture = CaptureSnapshot(
                        **{**capture.__dict__, "raw_source_checksum": capture.content_identity()}
                    )
                    result.snapshots.append(capture)
                    result.total_records += len(records)
                    result.completed_windows += 1
                    key = f"{index}"
                    previous = prior_by_window.get(key)
                    if previous is not None:
                        try:
                            report = reconcile_two_captures(previous, capture)
                            result.reconciliation_reports.append({
                                "window_index": index, "repeat": repeat,
                                "status": "RECONCILED" if complete and previous.complete else "INCONCLUSIVE",
                                "result": report.to_dict() if hasattr(report, "to_dict") else report,
                            })
                        except IncompatibleScopeError:
                            result.reconciliation_reports.append({
                                "window_index": index, "repeat": repeat, "status": "INCOMPATIBLE_SCOPE",
                            })
                    prior_by_window[key] = capture
                    if not complete:
                        result.status = "PARTIAL"
                except Exception as exc:
                    result.status = "PARTIAL"
                    result.errors.append(f"window={index};repeat={repeat};error={type(exc).__name__}")
                if plan.interval_seconds and run_count < plan.max_capture_runs:
                    self._sleep(plan.interval_seconds)
        return result


def observation_stability(snapshots: list[CaptureSnapshot]) -> dict[str, Any]:
    """Describe repeated observations without inferring deletion or retention."""
    if not snapshots:
        return {"status": "OBSERVATION_INCONCLUSIVE", "records": [],
                "disclaimer": "Measures observed API behavior, not venue completeness."}
    groups: dict[str, list[tuple[int, str]]] = {}
    for index, snap in enumerate(snapshots):
        for row in snap.records:
            from core.execution.cross_capture_reconciliation import extract_record_identity, canonical_record_hash
            identity = extract_record_identity(row, snap.record_category)
            if identity is None:
                continue
            groups.setdefault(identity, []).append((index, canonical_record_hash(row)))
    output = []
    for identity, seen in sorted(groups.items()):
        indices = [item[0] for item in seen]
        hashes = [item[1] for item in seen]
        missing = max(indices) - min(indices) + 1 - len(set(indices))
        changed = len(set(hashes)) > 1
        output.append({
            "record_identity": identity, "observed_capture_count": len(set(indices)),
            "first_observed_capture": min(indices), "last_observed_capture": max(indices),
            "unchanged_observations": max(0, len(hashes) - 1) if not changed else 0,
            "changed_observations": max(0, len(hashes) - 1) if changed else 0,
            "missing_observations": missing,
            "status": "CHANGED_BETWEEN_OBSERVATIONS" if changed else (
                "NOT_OBSERVED_IN_SOME_CAPTURES" if missing else "CONSISTENTLY_OBSERVED"
            ),
        })
    return {
        "status": "OBSERVATION_SEQUENCE_COMPLETE" if all(s.complete and s.pagination_complete for s in snapshots)
                 else "OBSERVATION_INCONCLUSIVE",
        "capture_count": len(snapshots), "records": output,
        "disclaimer": "This measures observed API behavior only; it does not establish venue history completeness, deletion, or retention policy.",
    }
