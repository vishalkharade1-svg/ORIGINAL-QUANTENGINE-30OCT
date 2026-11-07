"""Mobile push and telemetry broadcast gateway (Phase 163).

Provides real-time, non-blocking telemetry event broadcasting to connected mobile
and remote control clients. Enforces token authentication, secret redaction,
provenance labeling, and strict backpressure isolation.

Key Architectural Guarantees:
1. Zero Engine Impact:
   - Client subscriptions use bounded, non-blocking FIFO queues.
   - A lagging or disconnected client NEVER delays, blocks, or raises into
     the trading engine's execution loop.
2. Secret Redaction & Sanitization:
   - Any message payload is inspected; fields matching credential or secret
     patterns are automatically redacted before transmission.
3. Provenance & Integrity Labeling:
   - Every outbound frame carries explicit provenance tags ('source': 'OBSERVED'
     or 'PAPER_MODELLED') preventing simulated test data from being mistaken
     for venue truth.
4. Bearer Authentication:
   - Client handshakes require constant-time token comparison.
"""

from __future__ import annotations

import hmac
import json
import logging
import queue
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)

_REDACTED_KEYS = frozenset({
    "api_key", "secret", "api_secret", "credential", "password",
    "token", "private_key", "bearer", "authorization"
})


def sanitize_telemetry_payload(data: Any) -> Any:
    """Recursively redact sensitive keys from telemetry payloads."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(target in k.lower() for target in _REDACTED_KEYS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_telemetry_payload(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_telemetry_payload(item) for item in data]
    return data


@dataclass(frozen=True, slots=True)
class TelemetryFrame:
    event_type: str
    payload: dict[str, Any]
    source: str = "PAPER_MODELLED"  # OBSERVED or PAPER_MODELLED
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def serialize(self) -> str:
        clean_payload = sanitize_telemetry_payload(self.payload)
        frame = {
            "event": self.event_type,
            "source": self.source,
            "timestamp_ms": self.timestamp_ms,
            "data": clean_payload,
        }
        return json.dumps(frame, sort_keys=True)


class MobileClientSubscriber:
    """Represents one active client subscription with a bounded buffer."""

    def __init__(self, client_id: str, max_queue_size: int = 100):
        self.client_id = client_id
        self.queue: queue.Queue[str] = queue.Queue(maxsize=max_queue_size)
        self.dropped_frames_count = 0
        self.is_active = True

    def push(self, frame_json: str) -> bool:
        """Push a frame to the client buffer. Drops frame if queue is full."""
        if not self.is_active:
            return False
        try:
            self.queue.put_nowait(frame_json)
            return True
        except queue.Full:
            self.dropped_frames_count += 1
            return False

    def poll(self, timeout: float = 0.1) -> str | None:
        """Poll the next frame from the client queue."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None


class MobilePushGateway:
    """Thread-safe telemetry broadcaster serving mobile and web clients."""

    def __init__(self, expected_token: str, *, max_client_queue_size: int = 100):
        if not expected_token:
            raise ValueError("Expected token must be non-empty")
        self._expected_token = expected_token
        self._max_queue_size = max_client_queue_size
        self._lock = RLock()
        self._subscribers: dict[str, MobileClientSubscriber] = {}
        self._total_broadcast_frames = 0

    def authenticate_handshake(self, token_candidate: str | None) -> bool:
        """Constant-time token validation."""
        if not token_candidate:
            return False
        return hmac.compare_digest(
            token_candidate.encode("utf-8"),
            self._expected_token.encode("utf-8")
        )

    def register_client(self, client_id: str, auth_token: str) -> MobileClientSubscriber:
        """Register a new client subscriber after verifying token."""
        if not self.authenticate_handshake(auth_token):
            raise PermissionError("Unauthorized: invalid bearer token")

        with self._lock:
            sub = MobileClientSubscriber(client_id, max_queue_size=self._max_queue_size)
            self._subscribers[client_id] = sub
            logger.info("Registered mobile client subscriber: %s", client_id)
            return sub

    def unregister_client(self, client_id: str) -> None:
        """Safely remove a client subscriber."""
        with self._lock:
            if client_id in self._subscribers:
                sub = self._subscribers.pop(client_id)
                sub.is_active = False
                logger.info("Unregistered mobile client subscriber: %s", client_id)

    @property
    def active_subscribers_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @property
    def total_broadcast_frames(self) -> int:
        with self._lock:
            return self._total_broadcast_frames

    def broadcast(self, event_type: str, payload: dict[str, Any], *, source: str = "PAPER_MODELLED") -> int:
        """Broadcast a telemetry frame to all active clients.

        Returns the number of subscribers that successfully enqueued the frame.
        """
        frame = TelemetryFrame(event_type=event_type, payload=payload, source=source)
        serialized = frame.serialize()

        delivered_count = 0
        with self._lock:
            self._total_broadcast_frames += 1
            dead_clients = []
            for client_id, sub in self._subscribers.items():
                if not sub.is_active:
                    dead_clients.append(client_id)
                    continue
                if sub.push(serialized):
                    delivered_count += 1

            for cid in dead_clients:
                self._subscribers.pop(cid, None)

        return delivered_count
