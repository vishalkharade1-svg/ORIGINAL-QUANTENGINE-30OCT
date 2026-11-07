"""
====================================================

QuantEngine - Secure Remote / Mobile Control Foundation

audit.py -- thread-safe remote-control audit log (Phase 9P-k).

An append-only, JSON-lines audit trail of remote gateway events,
written to an operator-configured file. Every control action and
every significant authentication/authorization decision is
recorded with a timestamp, principal/device, correlation ID,
result, and (for control) the previous and resulting lifecycle
state and any failure reason.

HARD RULE: NO secrets are ever written. Tokens (per-role or the
local CONTROL_API_TOKEN) are NEVER logged, included in a failure
reason, placed in a correlation ID, or added to telemetry. A
request is audited by its correlation ID and role label, never by
its bearer secret.

Thread-safety: a single re-entrant lock serializes all writes so
the bearer token is hidden and partial lines are impossible.
Logging failures are swallowed (audit must never wedge a control
request), but the caller can check the last write error for
surface visibility.

Stdlib only: os, json, threading, time.
====================================================
"""

import json
import os
import threading
import time

_FALSE = frozenset({"", "0", "false", "no", "off"})


def _env_bool(name, default=False):
    val = os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val not in _FALSE


def _redact(value):
    """Best-effort scrub of obvious secret-shaped substrings. Used to
    defend against accidental leakage in a failure reason; never
    trusted on its own -- callers must not pass secrets in at all."""
    if not isinstance(value, str):
        return value
    low = value.lower()
    for marker in ("token=", "authorization", "bearer "):
        idx = low.find(marker)
        if idx >= 0:
            return "<redacted>"
    return value


class Mutation:
    """Immutable record of one auditable event."""

    __slots__ = (
        "ts", "correlation_id", "role", "device", "remote",
        "kind", "method", "path", "command", "prev_state",
        "result_state", "result", "failure",
    )

    def __init__(
        self,
        *,
        ts=None,
        correlation_id="",
        role="",
        device="",
        remote="",
        kind="event",
        method="",
        path="",
        command=None,
        prev_state=None,
        result_state=None,
        result="ok",
        failure="",
    ):
        self.ts = ts if ts is not None else time.time()
        self.correlation_id = correlation_id
        self.role = role
        self.device = device
        self.remote = remote
        self.kind = kind
        self.method = method
        self.path = path
        self.command = command
        self.prev_state = prev_state
        self.result_state = result_state
        self.result = result
        self.failure = _redact(failure)

    def as_dict(self):
        d = {
            "ts": round(self.ts, 3),
            "correlation_id": self.correlation_id,
            "role": self.role,
            "device": self.device,
            "remote": self.remote,
            "kind": self.kind,
            "method": self.method,
            "path": self.path,
            "result": self.result,
        }
        if self.command is not None:
            d["command"] = self.command
        if self.prev_state is not None:
            d["prev_state"] = self.prev_state
        if self.result_state is not None:
            d["result_state"] = self.result_state
        if self.failure:
            d["failure"] = self.failure
        return d


class AuditLog:
    """Append-only JSON-lines audit log. Safe to share across the
    gateway's handler threads; never raises on write failure."""

    def __init__(self, path=None):
        self._path = path
        self._lock = threading.RLock()
        self._fh = None
        self._last_error = None

        if path:
            self._open()

    def _open(self):
        try:
            directory = os.path.dirname(self._path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._fh = open(
                self._path, "a", encoding="utf-8", buffering=1
            )
        except OSError as exc:
            self._fh = None
            self._last_error = str(exc)

    @property
    def last_error(self):
        with self._lock:
            return self._last_error

    def enabled(self):
        return self._path is not None and self._fh is not None

    def write(self, event):
        if not isinstance(event, Mutation):
            return
        if self._path is None or self._fh is None:
            return
        with self._lock:
            try:
                self._fh.write(json.dumps(event.as_dict()) + "\n")
                self._fh.flush()
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)

    def close(self):
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None


def audit_from_settings():
    """Build an AuditLog from config.env. AUDIT_ENABLED gates it;
    AUDIT_PATH gives the file (default: logs/remote_audit.jsonl
    under the repo). Missing/empty path disables (no secret risk)."""
    if not _env_bool("AUDIT_ENABLED"):
        return AuditLog()
    path = os.getenv("AUDIT_PATH", "").strip()
    if not path:
        return AuditLog()
    return AuditLog(path)
