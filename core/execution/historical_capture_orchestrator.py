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
import stat
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4, uuid5, NAMESPACE_URL

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


def _bounded_int(value: Any, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


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
    max_pages_per_endpoint: int = 100
    max_total_pages: int = 500
    request_timeout_seconds: int = 20
    retry_budget: int = 2
    max_capture_runs: int = 48
    interval_seconds: int = 0
    mode: str = "fixture"
    plan_id: str | None = None
    endpoints: tuple[str, ...] = ("open_orders", "order_history", "fills", "positions", "wallet_transactions")

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
        if not _bounded_int(self.window_seconds, 60, 86400):
            raise CapturePlanError("window_seconds must be between 60 and 86400")
        if not _bounded_int(self.overlap_seconds, 0, min(3600, self.window_seconds // 2)):
            raise CapturePlanError("overlap_seconds exceeds the safe window bound")
        if not _bounded_int(self.repeat_count, 1, 10):
            raise CapturePlanError("repeat_count must be between 1 and 10")
        if not _bounded_int(self.max_windows, 1, 500):
            raise CapturePlanError("max_windows must be between 1 and 500")
        if not _bounded_int(self.max_records_per_snapshot, 1, 100000):
            raise CapturePlanError("max_records_per_snapshot must be between 1 and 100000")
        if not _bounded_int(self.max_total_records, 1, 1000000):
            raise CapturePlanError("max_total_records must be between 1 and 1000000")
        if not _bounded_int(self.max_pages_per_endpoint, 1, 100):
            raise CapturePlanError("max_pages_per_endpoint must be between 1 and 100")
        if not _bounded_int(self.max_total_pages, 1, 2500):
            raise CapturePlanError("max_total_pages must be between 1 and 2500")
        if not _bounded_int(self.request_timeout_seconds, 1, 60):
            raise CapturePlanError("request_timeout_seconds must be between 1 and 60")
        if not _bounded_int(self.retry_budget, 0, 5):
            raise CapturePlanError("retry_budget must be between 0 and 5")
        if not _bounded_int(self.max_capture_runs, 1, 5000):
            raise CapturePlanError("max_capture_runs must be between 1 and 5000")
        if not _bounded_int(self.interval_seconds, 0, 86400):
            raise CapturePlanError("interval_seconds must be between 0 and 86400")
        supported_endpoints = {"open_orders", "order_history", "fills", "positions", "wallet_transactions"}
        if (not isinstance(self.endpoints, tuple) or not self.endpoints
                or any(not isinstance(endpoint, str) or endpoint not in supported_endpoints
                       for endpoint in self.endpoints)
                or len(set(self.endpoints)) != len(self.endpoints)):
            raise CapturePlanError("endpoints must be a non-empty tuple of unique supported endpoint names")
        if self.mode not in {"fixture", "authenticated"}:
            raise CapturePlanError("mode must be fixture or authenticated")
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


_ENDPOINT_FIELDS = {
    "open_orders": "open_orders",
    "order_history": "order_history",
    "fills": "fills",
    "positions": "positions",
    "wallet_transactions": "wallet_transactions",
}


def _snapshot_records(snapshot: Any, endpoint: str) -> tuple[dict[str, Any], ...]:
    """Return only records belonging to one endpoint/category."""
    field_name = _ENDPOINT_FIELDS[endpoint]
    return tuple(dict(row) for row in (getattr(snapshot, field_name, ()) or ()))


def _endpoint_status(snapshot: Any) -> Mapping[str, str]:
    return dict(getattr(snapshot, "endpoint_status", {}) or {})


def _open_capture_plan_directory(root: Path, plan_id: str, *, create: bool) -> int | None:
    """Open a plan directory without following a plan-directory symlink."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise CapturePersistenceError("platform lacks no-follow directory operations")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        if create:
            root.mkdir(parents=True, exist_ok=True)
        elif not root.exists():
            return None
        root_fd = os.open(str(root), flags)
    except Exception:
        raise CapturePersistenceError("capture storage root is not a safe directory") from None
    try:
        try:
            plan_fd = os.open(plan_id, flags, dir_fd=root_fd)
        except FileNotFoundError:
            if not create:
                return None
            os.mkdir(plan_id, mode=0o700, dir_fd=root_fd)
            plan_fd = os.open(plan_id, flags, dir_fd=root_fd)
        return plan_fd
    except Exception:
        raise CapturePersistenceError("capture plan directory is not a safe directory") from None
    finally:
        os.close(root_fd)


def _read_capture_artifact_at(directory_fd: int, name: str) -> Mapping[str, Any]:
    """Read one regular artifact file without following a symlink."""
    if not name.endswith(".json") or name in {".json", "..json"} or "/" in name or "\\" in name:
        raise CapturePersistenceError("persisted capture artifact filename is invalid")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CapturePersistenceError("persisted capture artifact is not a regular file")
            payload = json.loads(stream.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise CapturePersistenceError("persisted capture artifact payload is invalid")
        return payload
    except CapturePersistenceError:
        raise
    except Exception as exc:
        raise CapturePersistenceError(
            f"persisted capture could not be opened safely ({type(exc).__name__})"
        ) from None


def _safe_json_write(root: Path, plan_id: str, capture_id: str,
                     payload: Mapping[str, Any]) -> str:
    """Atomically create an immutable artifact using no-follow directory handles."""
    if not capture_id or "/" in capture_id or "\\" in capture_id:
        raise CapturePersistenceError("capture artifact identity is not a safe filename")
    encoded = canonical_json_bytes(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    target_name = f"{capture_id}.json"
    directory_fd = _open_capture_plan_directory(root, plan_id, create=True)
    temporary_name = f".{target_name}.{uuid4().hex}.tmp"
    try:
        fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(
                temporary_name, target_name,
                src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing_fd = os.open(
                target_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            with os.fdopen(existing_fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise CapturePersistenceError("existing capture artifact is not a regular file")
                existing = stream.read()
            if hashlib.sha256(existing).hexdigest() == digest:
                return digest
            raise CapturePersistenceError(
                "capture artifact already exists with different content"
            ) from None
        os.fsync(directory_fd)
        return digest
    except CapturePersistenceError:
        raise
    except Exception as exc:
        raise CapturePersistenceError(
            f"atomic capture persistence failed ({type(exc).__name__})"
        ) from None
    finally:
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        os.close(directory_fd)


def _validate_page_provenance(value: Any, plan: HistoricalCapturePlan) -> None:
    """Validate the shape and bounded sequence of persisted read-page metadata."""
    if not isinstance(value, list):
        raise CapturePersistenceError("persisted page provenance must be a list")
    if len(value) > plan.max_total_pages:
        raise CapturePersistenceError("persisted page provenance exceeds the total page budget")
    next_index: dict[str, int] = {}
    allowed_statuses = {"REQUEST_FAILED", "INVALID_RESPONSE", "SUCCESS", "RECORD_BUDGET_OVERRUN", "REPEATED_PAGE"}
    for page in value:
        if not isinstance(page, Mapping):
            raise CapturePersistenceError("persisted page provenance entry must be a mapping")
        endpoint = page.get("endpoint")
        if endpoint not in plan.endpoints:
            raise CapturePersistenceError("persisted page provenance endpoint is unsupported")
        page_index = page.get("page_index")
        expected_index = next_index.get(endpoint, 0)
        if (not _bounded_int(page_index, 0, plan.max_pages_per_endpoint - 1)
                or page_index != expected_index):
            raise CapturePersistenceError("persisted page provenance index is invalid or non-sequential")
        next_index[endpoint] = expected_index + 1
        status = page.get("response_status")
        if status not in allowed_statuses:
            raise CapturePersistenceError("persisted page provenance response status is unsupported")
        for cursor_name in ("request_cursor", "response_cursor"):
            cursor = page.get(cursor_name)
            if cursor is not None and not isinstance(cursor, str):
                raise CapturePersistenceError("persisted page provenance cursor is invalid")
        record_count = page.get("record_count")
        if not _bounded_int(record_count, 0, plan.max_records_per_snapshot):
            raise CapturePersistenceError("persisted page provenance record count is invalid")
        digest = page.get("content_sha256")
        if digest is not None and (not isinstance(digest, str) or len(digest) != 64
                                   or any(ch not in "0123456789abcdef" for ch in digest)):
            raise CapturePersistenceError("persisted page provenance content digest is invalid")
        if status in {"REQUEST_FAILED", "INVALID_RESPONSE"} and digest is not None:
            raise CapturePersistenceError("failed page provenance cannot declare a content digest")
        if status in {"SUCCESS", "RECORD_BUDGET_OVERRUN", "REPEATED_PAGE"} and digest is None:
            raise CapturePersistenceError("received page provenance is missing its content digest")
        for timestamp_name in ("request_started_at", "collected_at"):
            try:
                _utc(page.get(timestamp_name), timestamp_name)
            except CapturePlanError:
                raise CapturePersistenceError("persisted page provenance timestamp is invalid") from None
        duration = page.get("request_duration_ms")
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or not duration >= 0 or duration == float("inf")):
            raise CapturePersistenceError("persisted page provenance duration is invalid")
        retry_count = page.get("retry_count")
        if retry_count is not None and not _bounded_int(retry_count, 0, 1000):
            raise CapturePersistenceError("persisted page provenance retry count is invalid")
        http_status = page.get("http_status_code")
        if http_status is not None and not _bounded_int(http_status, 0, 999):
            raise CapturePersistenceError("persisted page provenance HTTP status is invalid")
        if not isinstance(page.get("request_policy_enforced"), bool):
            raise CapturePersistenceError("persisted page provenance policy flag is invalid")
        if "records_not_persisted" in page:
            not_persisted = page["records_not_persisted"]
            if (not _bounded_int(not_persisted, 0, plan.max_records_per_snapshot)
                    or not_persisted > record_count):
                raise CapturePersistenceError("persisted page provenance dropped-record count is invalid")
        if "record_budget_remaining" in page and not _bounded_int(
                page["record_budget_remaining"], 0, plan.max_total_records):
            raise CapturePersistenceError("persisted page provenance remaining-budget field is invalid")
        if "pagination_metadata_present" in page and not isinstance(page["pagination_metadata_present"], bool):
            raise CapturePersistenceError("persisted page provenance pagination flag is invalid")
        if "pagination_status" in page and not isinstance(page["pagination_status"], str):
            raise CapturePersistenceError("persisted page provenance pagination status is invalid")
        if "error_type" in page and (not isinstance(page["error_type"], str) or not page["error_type"]):
            raise CapturePersistenceError("persisted page provenance error type is invalid")


_CAPTURE_ARTIFACT_SCHEMA = "quantengine.phase208.capture.v1"
_CAPTURE_POLICY_VERSION = "phase208-bounded-read-capture-v1"


def _plan_fingerprint(plan: HistoricalCapturePlan, windows: tuple[CaptureWindow, ...]) -> str:
    """Fingerprint all plan inputs that can affect collection or evidence meaning."""
    start_iso, end_iso = windows[0].as_iso()[0], windows[-1].as_iso()[1]
    policy = {
        "policy_version": _CAPTURE_POLICY_VERSION,
        "venue": plan.venue.strip().lower(),
        "tenant_id": plan.tenant_id,
        "account_id": plan.account_id,
        "product_id": plan.product_id,
        "start": start_iso,
        "end": end_iso,
        "window_seconds": plan.window_seconds,
        "overlap_seconds": plan.overlap_seconds,
        "repeat_count": plan.repeat_count,
        "max_windows": plan.max_windows,
        "max_records_per_snapshot": plan.max_records_per_snapshot,
        "max_total_records": plan.max_total_records,
        "max_pages_per_endpoint": plan.max_pages_per_endpoint,
        "max_total_pages": plan.max_total_pages,
        "request_timeout_seconds": plan.request_timeout_seconds,
        "retry_budget": plan.retry_budget,
        "max_capture_runs": plan.max_capture_runs,
        "interval_seconds": plan.interval_seconds,
        "mode": plan.mode,
        "endpoints": list(plan.endpoints),
    }
    return hashlib.sha256(canonical_json_bytes(policy)).hexdigest()


def _adapter_identity_payload(adapter: Any, *, require_source_identity: bool = False) -> dict[str, Any]:
    """Return auditable, non-secret adapter/source identity metadata."""
    def class_name(value: Any) -> str | None:
        if value is None:
            return None
        cls = type(value)
        return f"{cls.__module__}.{cls.__qualname__}"

    def reject_secret_fields(value: Any) -> None:
        if isinstance(value, Mapping):
            forbidden = (
                "secret", "password", "api_key", "apikey", "credential",
                "authorization", "private_key", "access_token", "refresh_token",
                "signature",
            )
            for key, nested in value.items():
                normalized = str(key).lower().replace("-", "_")
                if any(term in normalized for term in forbidden):
                    raise CapturePlanError(
                        "adapter provenance_identity contains a credential-like field"
                    )
                reject_secret_fields(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                reject_secret_fields(nested)

    read_adapter = getattr(adapter, "_read_adapter", None)
    rest_client = getattr(adapter, "_rest", None)
    if rest_client is None and read_adapter is not None:
        rest_client = getattr(read_adapter, "_rest", None)
    identity: dict[str, Any] = {
        "adapter_class": class_name(adapter),
        "read_adapter_class": class_name(read_adapter),
        "rest_client_class": class_name(rest_client),
    }
    source_found = False
    for label, component in (
        ("adapter_source", adapter),
        ("read_adapter_source", read_adapter),
        ("rest_source", rest_client),
    ):
        if component is None:
            continue
        source_identity = getattr(component, "provenance_identity", None)
        if callable(source_identity):
            source_identity = source_identity()
        if source_identity is None:
            continue
        if not isinstance(source_identity, (str, Mapping)):
            raise CapturePlanError("adapter provenance_identity must be a string or JSON mapping")
        reject_secret_fields(source_identity)
        identity[label] = source_identity
        source_found = True
    if require_source_identity and not source_found:
        raise CapturePlanError(
            "authenticated adapter must expose a stable non-secret provenance_identity"
        )
    try:
        canonical_json_bytes(identity)
    except Exception:
        raise CapturePlanError("adapter provenance_identity must be canonical JSON data") from None
    return identity


def _adapter_fingerprint(adapter: Any, *, require_source_identity: bool = False) -> str:
    identity = _adapter_identity_payload(
        adapter, require_source_identity=require_source_identity
    )
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def _assert_adapter_fingerprint(
    adapter: Any, expected: str, *, require_source_identity: bool
) -> None:
    try:
        current = _adapter_fingerprint(
            adapter, require_source_identity=require_source_identity
        )
    except CapturePlanError:
        raise CapturePersistenceError("adapter/source identity became invalid during capture") from None
    if current != expected:
        raise CapturePersistenceError("adapter/source identity changed during capture")


class DeltaCaptureAdapter(Protocol):
    def capture(self, *, product_id: int, window_start: str, window_end: str,
                overlap_seconds: int = 60, endpoints: tuple[str, ...] | None = None,
                max_pages_per_endpoint: int = 100, max_total_pages: int = 500,
                request_timeout_seconds: int = 20, retry_budget: int = 2,
                allow_partial: bool = False) -> Any: ...


@dataclass
class CaptureRunResult:
    plan_id: str
    status: str
    snapshots: list[CaptureSnapshot] = field(default_factory=list)
    reconciliation_reports: list[dict[str, Any]] = field(default_factory=list)
    cross_window_reconciliation_reports: list[dict[str, Any]] = field(default_factory=list)
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
        self._root = Path(storage_root).resolve()
        self._owner_authorizer = owner_authorizer
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleeper

    def run(self, plan: HistoricalCapturePlan, *, resume: bool = True) -> CaptureRunResult:
        windows = generate_windows(plan)
        if plan.mode == "authenticated":
            if self._owner_authorizer is None or self._owner_authorizer(plan) is not True:
                raise CaptureAuthorizationError("trusted owner authorization callback denied capture")
            rest_client = getattr(self._adapter, "_rest", None)
            if rest_client is None:
                rest_client = getattr(getattr(self._adapter, "_read_adapter", None), "_rest", None)
            if not bool(getattr(rest_client, "authenticated", False)):
                raise CaptureAuthorizationError("authenticated Delta REST client is not available")
            if not callable(getattr(rest_client, "get_with_policy", None)):
                raise CaptureAuthorizationError("authenticated REST client lacks bounded timeout/retry policy support")
        plan_id = plan.plan_id or str(uuid5(NAMESPACE_URL, canonical_json_bytes({
            "venue": plan.venue, "tenant": plan.tenant_id, "account": plan.account_id,
            "product": plan.product_id, "start_utc": windows[0].start.isoformat(),
            "end_utc": windows[-1].end.isoformat(),
            "window_seconds": plan.window_seconds, "overlap_seconds": plan.overlap_seconds,
            "repeat_count": plan.repeat_count, "max_windows": plan.max_windows,
            "max_records_per_snapshot": plan.max_records_per_snapshot,
            "max_total_records": plan.max_total_records,
            "max_pages_per_endpoint": plan.max_pages_per_endpoint,
            "max_total_pages": plan.max_total_pages,
            "request_timeout_seconds": plan.request_timeout_seconds,
            "retry_budget": plan.retry_budget,
            "max_capture_runs": plan.max_capture_runs,
            "interval_seconds": plan.interval_seconds, "mode": plan.mode,
            "endpoints": plan.endpoints,
        }).decode("utf-8")))
        if (not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128
                or plan_id in {".", ".."} or "/" in plan_id or "\\" in plan_id
                or Path(plan_id).name != plan_id):
            raise CapturePlanError("plan_id must be a safe single path component")
        plan_fingerprint = _plan_fingerprint(plan, windows)
        adapter_identity = _adapter_identity_payload(
            self._adapter, require_source_identity=plan.mode == "authenticated"
        )
        adapter_fingerprint = hashlib.sha256(
            canonical_json_bytes(adapter_identity)
        ).hexdigest()
        result = CaptureRunResult(
            plan_id=plan_id,
            status="COMPLETE",
            requested_windows=len(windows) * plan.repeat_count,
        )
        # Phase 207: reconstruct verified Phase-207 artifacts before issuing
        # any new reads. Legacy Phase-206 v1 files lack slot coordinates and
        # are intentionally not guessed into a window/repeat position.
        slot_latest: dict[tuple[int, int, str], CaptureSnapshot] = {}
        plan_directory_fd = (
            _open_capture_plan_directory(self._root, plan_id, create=False)
            if resume else None
        )
        if plan_directory_fd is not None:
            recovered: list[tuple[int, int, str, CaptureSnapshot]] = []
            try:
                artifact_names = sorted(
                    name for name in os.listdir(plan_directory_fd) if name.endswith(".json")
                )
                for artifact_name in artifact_names:
                    try:
                        payload = _read_capture_artifact_at(plan_directory_fd, artifact_name)
                        schema = payload.get("schema")
                        if schema in {"quantengine.phase206.capture.v1", "quantengine.phase207.capture.v1"}:
                            # Older artifacts lack plan/source fingerprints; preserve
                            # them but never trust them as resumable slots.
                            continue
                        if schema != _CAPTURE_ARTIFACT_SCHEMA:
                            raise CapturePersistenceError("persisted capture schema is unsupported")
                        if payload.get("plan_id") != plan_id or payload.get("tenant_id") != plan.tenant_id:
                            raise CapturePersistenceError("persisted capture scope does not match requested plan")
                        if payload.get("plan_fingerprint") != plan_fingerprint:
                            raise CapturePersistenceError("persisted capture plan/policy fingerprint does not match")
                        if payload.get("adapter_identity") != adapter_identity:
                            raise CapturePersistenceError("persisted capture adapter/source identity does not match")
                        if payload.get("adapter_fingerprint") != adapter_fingerprint:
                            raise CapturePersistenceError("persisted capture adapter/source fingerprint does not match")
                        repeat_index = payload.get("repeat_index")
                        window_index = payload.get("window_index")
                        endpoint = payload.get("endpoint")
                        if (not _bounded_int(repeat_index, 0, plan.repeat_count - 1)
                                or not _bounded_int(window_index, 0, len(windows) - 1)
                                or endpoint not in plan.endpoints):
                            raise CapturePersistenceError("persisted capture has invalid slot coordinates")
                        capture_payload = payload.get("capture")
                        if not isinstance(capture_payload, Mapping):
                            raise CapturePersistenceError("persisted capture payload is invalid")
                        content_checksum = capture_payload.get("raw_source_checksum")
                        if (not isinstance(content_checksum, str) or len(content_checksum) != 64
                                or any(ch not in "0123456789abcdef" for ch in content_checksum)):
                            raise CapturePersistenceError(
                                "persisted capture content checksum is missing or invalid"
                            )
                        capture_records = capture_payload.get("records")
                        capture_record_count = capture_payload.get("record_count")
                        if (not isinstance(capture_records, (list, tuple))
                                or not _bounded_int(
                                    capture_record_count, 0, plan.max_records_per_snapshot
                                )
                                or capture_record_count != len(capture_records)):
                            raise CapturePersistenceError(
                                "persisted capture record count is missing or inconsistent"
                            )
                        if capture_payload.get("schema") != "quantengine.historical-capture.v1":
                            raise CapturePersistenceError("persisted capture schema is unsupported")
                        capture = CaptureSnapshot.from_dict(capture_payload)
                        if capture.record_category != endpoint:
                            raise CapturePersistenceError("persisted capture endpoint does not match its slot")
                        if artifact_name[:-5] != capture.capture_id:
                            raise CapturePersistenceError("persisted capture filename does not match capture identity")
                        expected_capture_id = str(uuid5(
                            NAMESPACE_URL,
                            f"{plan_id}:{repeat_index}:{window_index}:{endpoint}:{capture.captured_at}",
                        ))
                        if capture.capture_id != expected_capture_id:
                            raise CapturePersistenceError("persisted capture identity does not match its slot and timestamp")
                        _validate_page_provenance(payload.get("page_provenance"), plan)
                        expected_product = None if endpoint == "wallet_transactions" else plan.product_id
                        if (capture.venue.strip().lower() != plan.venue.strip().lower()
                                or capture.account_id != plan.account_id
                                or capture.product_id != expected_product):
                            raise CapturePersistenceError("persisted capture scope does not match requested plan")
                        expected_status = "COMPLETE" if capture.complete and capture.pagination_complete else "PARTIAL"
                        if payload.get("capture_status") != expected_status:
                            raise CapturePersistenceError("persisted capture status does not match its completeness flags")
                        expected_window = windows[window_index]
                        expected_start, expected_end = expected_window.as_iso()
                        if capture.window_start != expected_start or capture.window_end != expected_end:
                            raise CapturePersistenceError("persisted capture window does not match its slot")
                        if len(capture.records) > plan.max_records_per_snapshot:
                            raise CapturePersistenceError("persisted capture exceeds per-snapshot record budget")
                        recovered.append((repeat_index, window_index, endpoint, capture))
                    except CapturePersistenceError:
                        raise
                    except Exception as exc:
                        raise CapturePersistenceError(
                            f"persisted capture could not be verified ({type(exc).__name__})"
                        ) from None
            finally:
                os.close(plan_directory_fd)
            for repeat_index, window_index, endpoint, capture in sorted(
                    recovered, key=lambda item: (item[0], item[1], item[2], item[3].captured_at)):
                result.snapshots.append(capture)
                result.total_records += len(capture.records)
                if result.total_records > plan.max_total_records:
                    raise CapturePersistenceError("persisted captures exceed total record budget")
                key = (repeat_index, window_index, endpoint)
                previous = slot_latest.get(key)
                if previous is None or capture.captured_at >= previous.captured_at:
                    slot_latest[key] = capture
        run_count = 0
        for repeat in range(plan.repeat_count):
            for index, window in enumerate(windows):
                start_iso, end_iso = window.as_iso()
                missing_endpoints = tuple(
                    endpoint for endpoint in plan.endpoints
                    if (repeat, index, endpoint) not in slot_latest
                    or not slot_latest[(repeat, index, endpoint)].complete
                    or not slot_latest[(repeat, index, endpoint)].pagination_complete
                )
                if not missing_endpoints:
                    result.completed_windows += 1
                    continue
                if run_count >= plan.max_capture_runs:
                    result.status = "PARTIAL"
                    result.errors.append("MAX_CAPTURE_RUNS_REACHED")
                    return result
                run_count += 1
                try:
                    _assert_adapter_fingerprint(
                        self._adapter, adapter_fingerprint,
                        require_source_identity=plan.mode == "authenticated",
                    )
                    raw = self._adapter.capture(
                        product_id=plan.product_id, window_start=start_iso,
                        window_end=end_iso, overlap_seconds=plan.overlap_seconds,
                        endpoints=missing_endpoints,
                        max_pages_per_endpoint=plan.max_pages_per_endpoint,
                        max_total_pages=plan.max_total_pages,
                        request_timeout_seconds=plan.request_timeout_seconds,
                        retry_budget=plan.retry_budget, allow_partial=True,
                    )
                    _assert_adapter_fingerprint(
                        self._adapter, adapter_fingerprint,
                        require_source_identity=plan.mode == "authenticated",
                    )
                    endpoint_status = _endpoint_status(raw)
                    captured_at = str(getattr(raw, "captured_at", self._clock().isoformat()))
                    for endpoint in missing_endpoints:
                        records = _snapshot_records(raw, endpoint)
                        if len(records) > plan.max_records_per_snapshot:
                            raise CapturePlanError("MAX_RECORDS_PER_SNAPSHOT_REACHED")
                        if result.total_records + len(records) > plan.max_total_records:
                            raise CapturePlanError("MAX_TOTAL_RECORDS_REACHED")
                        endpoint_complete = endpoint_status.get(endpoint) == "OK"
                        capture_id = str(uuid5(
                            NAMESPACE_URL,
                            f"{plan_id}:{repeat}:{index}:{endpoint}:{captured_at}",
                        ))
                        capture = CaptureSnapshot(
                            capture_id=capture_id, venue=plan.venue,
                            record_category=endpoint, records=records,
                            captured_at=captured_at,
                            product_id=None if endpoint == "wallet_transactions" else plan.product_id,
                            account_id=plan.account_id, window_start=start_iso, window_end=end_iso,
                            overlap_seconds=plan.overlap_seconds, complete=endpoint_complete,
                            pagination_complete=endpoint_complete,
                            endpoint_status={endpoint: endpoint_status.get(endpoint, "STATUS_MISSING")},
                        )
                        page_provenance = [dict(page) for page in getattr(raw, "page_provenance", ())]
                        _validate_page_provenance(page_provenance, plan)
                        payload = {
                            "schema": _CAPTURE_ARTIFACT_SCHEMA,
                            "plan_id": plan_id, "tenant_id": plan.tenant_id,
                            "plan_fingerprint": plan_fingerprint,
                            "adapter_identity": adapter_identity,
                            "adapter_fingerprint": adapter_fingerprint,
                            "repeat_index": repeat, "window_index": index,
                            "endpoint": endpoint,
                            "capture": capture.to_dict(),
                            "capture_status": "COMPLETE" if endpoint_complete else "PARTIAL",
                            "page_provenance": page_provenance,
                        }
                        _safe_json_write(self._root, plan_id, capture_id, payload)
                        capture = CaptureSnapshot(
                            **{**capture.__dict__, "raw_source_checksum": capture.content_identity()}
                        )
                        result.snapshots.append(capture)
                        result.total_records += len(records)
                        slot_latest[(repeat, index, endpoint)] = capture
                        if not endpoint_complete:
                            result.status = "PARTIAL"
                            status_label = endpoint_status.get(endpoint, "STATUS_MISSING")
                            result.errors.append(
                                f"window={index};repeat={repeat};endpoint={endpoint};status={status_label}"
                            )
                    if all(
                        (repeat, index, endpoint) in slot_latest
                        and slot_latest[(repeat, index, endpoint)].complete
                        and slot_latest[(repeat, index, endpoint)].pagination_complete
                        for endpoint in plan.endpoints
                    ):
                        result.completed_windows += 1
                except CapturePlanError as exc:
                    result.status = "PARTIAL"
                    result.errors.append(f"window={index};repeat={repeat};error={str(exc)}")
                    # Budget exhaustion is terminal for this run. Do not keep
                    # issuing reads after a hard record/window budget is hit.
                    return result
                except CapturePersistenceError:
                    # Evidence durability/integrity failures are not adapter
                    # transients. Stop immediately; never continue collecting.
                    raise
                except Exception as exc:
                    result.status = "PARTIAL"
                    result.errors.append(f"window={index};repeat={repeat};error={type(exc).__name__}")
                if plan.interval_seconds and run_count < plan.max_capture_runs:
                    self._sleep(plan.interval_seconds)
        # Reconcile repeated observations for the same window independently
        # of execution order so reports are reconstructed after restart too.
        for repeat in range(1, plan.repeat_count):
            for index in range(len(windows)):
                for endpoint in plan.endpoints:
                    earlier = slot_latest.get((repeat - 1, index, endpoint))
                    later = slot_latest.get((repeat, index, endpoint))
                    if earlier is None or later is None:
                        continue
                    try:
                        report = reconcile_two_captures(earlier, later)
                        result.reconciliation_reports.append({
                            "window_index": index,
                            "repeat": repeat,
                            "endpoint": endpoint,
                            "status": (
                                report.status
                                if earlier.complete and earlier.pagination_complete
                                and later.complete and later.pagination_complete
                                else "INCONCLUSIVE"
                            ),
                            "result": report.to_dict() if hasattr(report, "to_dict") else report,
                        })
                    except IncompatibleScopeError:
                        result.reconciliation_reports.append({
                            "window_index": index, "repeat": repeat,
                            "endpoint": endpoint, "status": "INCOMPATIBLE_SCOPE",
                        })
        # Reconcile adjacent windows independently of repeated same-window
        # observations. This runs after the loop so it also works when every
        # slot was recovered from disk and no adapter call was necessary.
        for repeat in range(plan.repeat_count):
            for index in range(1, len(windows)):
                for endpoint in plan.endpoints:
                    earlier = slot_latest.get((repeat, index - 1, endpoint))
                    later = slot_latest.get((repeat, index, endpoint))
                    if earlier is None or later is None:
                        continue
                    try:
                        report = reconcile_two_captures(earlier, later)
                        result.cross_window_reconciliation_reports.append({
                            "repeat": repeat,
                            "earlier_window_index": index - 1,
                            "later_window_index": index,
                            "endpoint": endpoint,
                            "status": (
                                report.status
                                if earlier.complete and earlier.pagination_complete
                                and later.complete and later.pagination_complete
                                else "INCONCLUSIVE"
                            ),
                            "result": report.to_dict() if hasattr(report, "to_dict") else report,
                        })
                    except IncompatibleScopeError:
                        result.cross_window_reconciliation_reports.append({
                            "repeat": repeat,
                            "earlier_window_index": index - 1,
                            "later_window_index": index,
                            "endpoint": endpoint,
                            "status": "INCOMPATIBLE_SCOPE",
                        })
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
        missing = len(snapshots) - len(set(indices))
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
        "disclaimer": "This measures observed API behavior only; absence does not prove a record was deleted and does not establish venue history completeness or retention policy.",
    }
