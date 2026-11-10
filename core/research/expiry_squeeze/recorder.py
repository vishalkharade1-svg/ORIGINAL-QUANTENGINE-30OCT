"""Append-only, hash-chained observation journal for expiry-option research.

The recorder is provider-neutral and deliberately has no broker, exchange,
strategy, or execution imports. A provider adapter must normalize incoming
messages into the event contract below. Every observation is retained in
arrival order; exchange time and local receipt time are stored separately.

A single writer owns a session journal. On restart the complete chain is
verified before appending. Corrupt or truncated journals fail closed and are
never silently repaired or overwritten.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any, Mapping


SCHEMA = "quantengine.expiry_squeeze.event.v1"
_ALLOWED_EVENT_TYPES = frozenset({
    "SESSION_MARKER",
    "OPTION_CHAIN_SNAPSHOT",
    "OPTION_QUOTE",
    "OPTION_TRADE",
    "OPTION_BOOK",
    "OPTION_CANDLE_1M",
    "INDEX_CANDLE_1M",
    "INDEX_CANDLE_5M",
    "CANDIDATE",
    "REJECTION",
    "OUTCOME_LABEL",
})
_ALLOWED_CANDIDATE_STATES = frozenset({"OBSERVED", "ELIGIBLE", "REJECTED"})
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_ZERO_HASH = "0" * 64


class RecorderError(ValueError):
    """The event or recorder configuration violates the capture contract."""


class CaptureLimitError(RecorderError):
    """A configured event or disk budget has been reached."""


class CorruptJournalError(RecorderError):
    """A persisted journal is truncated, malformed, or hash-inconsistent."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecorderError(f"event is not strict JSON: {type(exc).__name__}") from None


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecorderError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise RecorderError(f"{field} must be valid ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecorderError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash_event(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(dict(body))).hexdigest()


def candidate_identity(session_id: str, instrument_id: str, decision_timestamp: str) -> str:
    """Stable identity for one contract at one decision timestamp."""
    if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
        raise RecorderError("session_id must be a safe single identifier")
    if not isinstance(instrument_id, str) or not instrument_id.strip():
        raise RecorderError("instrument_id is required")
    normalized_ts = _timestamp(decision_timestamp, "decision_timestamp")
    raw = _canonical_bytes([session_id, instrument_id, normalized_ts])
    return "C-" + hashlib.sha256(raw).hexdigest()[:24]


class ExpirySqueezeRecorder:
    """Durable, append-only journal for normalized market observations.

    Parameters
    ----------
    journal_path:
        One JSONL file for one capture session. Existing files are verified
        before the recorder becomes writable.
    session_id:
        Safe session identifier, e.g. SENSEX-2026-11-12.
    max_events / max_bytes:
        Hard local budgets. The recorder refuses the next append rather than
        deleting, rotating, or overwriting earlier evidence.

    This class is intentionally single-writer. A provider integration should
    serialize callbacks through one recorder instance/queue.
    """

    def __init__(self, journal_path: str | Path, session_id: str,
                 *, max_events: int = 2_000_000,
                 max_bytes: int = 2_000_000_000):
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            raise RecorderError("session_id must be a safe single identifier")
        if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= 20_000_000:
            raise RecorderError("max_events must be an integer in [1, 20000000]")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= 50_000_000_000:
            raise RecorderError("max_bytes must be an integer in [1, 50000000000]")
        self.path = Path(journal_path)
        self.session_id = session_id
        self.max_events = max_events
        self.max_bytes = max_bytes
        self._lock = RLock()
        self._closed = False
        self._sequence = 0
        self._last_hash = _ZERO_HASH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._verify_existing()

    def _verify_existing(self) -> None:
        sequence = 0
        previous_hash = _ZERO_HASH
        try:
            with self.path.open("rb") as stream:
                for line_number, raw_line in enumerate(stream, 1):
                    if not raw_line.endswith(b"\\n"):
                        raise CorruptJournalError(f"truncated journal line {line_number}")
                    try:
                        event = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise CorruptJournalError(f"invalid JSON at line {line_number}") from None
                    if not isinstance(event, dict):
                        raise CorruptJournalError(f"event at line {line_number} is not an object")
                    supplied_hash = event.pop("event_hash", None)
                    if event.get("schema") != SCHEMA:
                        raise CorruptJournalError(f"unsupported schema at line {line_number}")
                    if event.get("session_id") != self.session_id:
                        raise CorruptJournalError(f"session identity mismatch at line {line_number}")
                    if event.get("sequence") != sequence + 1:
                        raise CorruptJournalError(f"sequence discontinuity at line {line_number}")
                    if event.get("previous_event_hash") != previous_hash:
                        raise CorruptJournalError(f"hash-chain predecessor mismatch at line {line_number}")
                    actual_hash = _hash_event(event)
                    if supplied_hash != actual_hash:
                        raise CorruptJournalError(f"event checksum mismatch at line {line_number}")
                    sequence += 1
                    previous_hash = actual_hash
        except OSError as exc:
            raise CorruptJournalError(f"journal cannot be read ({type(exc).__name__})") from None
        if sequence > self.max_events:
            raise CaptureLimitError("existing journal already exceeds max_events")
        if self.path.stat().st_size > self.max_bytes:
            raise CaptureLimitError("existing journal already exceeds max_bytes")
        self._sequence = sequence
        self._last_hash = previous_hash

    @property
    def event_count(self) -> int:
        return self._sequence

    @property
    def last_event_hash(self) -> str:
        return self._last_hash

    def append(self, event_type: str, *, exchange_timestamp: str,
               instrument: Mapping[str, Any], payload: Mapping[str, Any],
               received_timestamp: str | None = None) -> dict[str, Any]:
        """Append one normalized event and fsync it before returning."""
        with self._lock:
            if self._closed:
                raise RecorderError("recorder is closed")
            if event_type not in _ALLOWED_EVENT_TYPES:
                raise RecorderError("unsupported event_type")
            if not isinstance(instrument, Mapping) or not instrument:
                raise RecorderError("instrument must be a non-empty mapping")
            if not isinstance(payload, Mapping):
                raise RecorderError("payload must be a mapping")
            if self._sequence >= self.max_events:
                raise CaptureLimitError("MAX_EVENTS_REACHED")
            exchange_ts = _timestamp(exchange_timestamp, "exchange_timestamp")
            received_ts = _timestamp(
                received_timestamp or datetime.now(timezone.utc).isoformat(),
                "received_timestamp",
            )
            body = {
                "schema": SCHEMA,
                "session_id": self.session_id,
                "sequence": self._sequence + 1,
                "event_type": event_type,
                "exchange_timestamp_utc": exchange_ts,
                "received_timestamp_utc": received_ts,
                "instrument": dict(instrument),
                "payload": dict(payload),
                "previous_event_hash": self._last_hash,
            }
            digest = _hash_event(body)
            event = {**body, "event_hash": digest}
            encoded = _canonical_bytes(event) + b"\\n"
            current_size = self.path.stat().st_size if self.path.exists() else 0
            if current_size + len(encoded) > self.max_bytes:
                raise CaptureLimitError("MAX_BYTES_REACHED")
            try:
                with self.path.open("ab") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                raise RecorderError(f"journal append failed ({type(exc).__name__})") from None
            self._sequence += 1
            self._last_hash = digest
            return event

    def record_candidate(self, *, decision_timestamp: str,
                         instrument: Mapping[str, Any], instrument_id: str,
                         state: str, premium: str | int | float,
                         reasons: tuple[str, ...] = (),
                         features: Mapping[str, Any] | None = None,
                         received_timestamp: str | None = None) -> dict[str, Any]:
        """Persist an eligible, observed, or rejected candidate without trading."""
        if state not in _ALLOWED_CANDIDATE_STATES:
            raise RecorderError("candidate state must be OBSERVED, ELIGIBLE, or REJECTED")
        if state == "REJECTED" and not reasons:
            raise RecorderError("rejected candidates require at least one reason")
        if not isinstance(reasons, tuple) or any(not isinstance(x, str) or not x.strip() for x in reasons):
            raise RecorderError("reasons must be a tuple of non-empty strings")
        if isinstance(premium, bool):
            raise RecorderError("premium must be a finite positive number")
        try:
            premium_value = float(premium)
        except (TypeError, ValueError):
            raise RecorderError("premium must be a finite positive number") from None
        if not math.isfinite(premium_value) or premium_value <= 0:
            raise RecorderError("premium must be a finite positive number")
        candidate_id = candidate_identity(self.session_id, instrument_id, decision_timestamp)
        return self.append(
            "CANDIDATE",
            exchange_timestamp=decision_timestamp,
            received_timestamp=received_timestamp,
            instrument=instrument,
            payload={
                "candidate_id": candidate_id,
                "candidate_state": state,
                "premium": str(premium),
                "rejection_reasons": list(reasons),
                "features": dict(features or {}),
                "action_authorized": False,
            },
        )

    def close(self) -> None:
        """Prevent further writes. Existing journal remains immutable."""
        with self._lock:
            self._closed = True

    @classmethod
    def verify_journal(cls, journal_path: str | Path, session_id: str) -> dict[str, Any]:
        """Verify a journal without opening it for writes."""
        recorder = cls(journal_path, session_id)
        return {
            "status": "VERIFIED",
            "session_id": session_id,
            "event_count": recorder.event_count,
            "last_event_hash": recorder.last_event_hash,
            "bytes": recorder.path.stat().st_size if recorder.path.exists() else 0,
        }
