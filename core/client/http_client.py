"""
====================================================

QuantEngine

Lightweight Desktop Control Client - HTTP client

Phase 9P-h.

A tiny standard-library HTTP client for the Control &
Monitoring API (Phase 9P-f / 9P-g). It is deliberately
generic over JSON endpoints so the desktop UI, and any
future client (mobile / web), can share one transport.

Contract (must match core/monitoring/api_server.py):

  GET  /health /universe /subscriptions /runtimes /market
       /signals /positions /orders /account /risk
       /performance /errors          -> 200 JSON

  POST /control  {"command": start|stop|restart|
                  emergency_stop}    -> 200 {"command","lifecycle_state"}

  Auth: "Authorization: Bearer <token>" on every request.
  Errors: 401 -> unauthorized / 400 -> {"error","detail"} /
          500 -> internal.

This client NEVER imports engine internals -- it speaks
HTTP only, so the only dependency direction is
CLIENT -> CONTROL API. It keeps the bearer token entirely
internal: it is never logged, shown in exception messages,
placed in URLs, or included in window titles.

Stdlib only: urllib.request, urllib.error, json, time.
====================================================
"""

import json
import time
from urllib import error as _urlerror
from urllib import parse as _urlparse
from urllib import request as _urlrequest


class ClientError(Exception):
    """Base error for the Control API HTTP client."""


class ConnectionErrorWithCause(ClientError):
    """Could not reach the server (refused / DNS / network)."""


class TimeoutErrorWithCause(ClientError):
    """The request exceeded the configured timeout."""


class AuthenticationError(ClientError):
    """The server rejected the bearer token (401)."""


class ServerError(ClientError):
    """The server returned 5xx."""


class BadResponseError(ClientError):
    """The server returned a non-2xx / non-JSON response."""


class ControlRejectedError(ClientError):
    """The server refused a control command (400 control_rejected)."""


def _classify(status, body):
    if status == 200:
        return None
    if status == 401:
        return AuthenticationError("authentication failed (check token)")
    if status == 400:
        err = (body or {}).get("error") if isinstance(body, dict) else None
        if err == "control_rejected":
            detail = (
                (body or {}).get("detail", "")
                if isinstance(body, dict)
                else ""
            )
            return ControlRejectedError(
                "control rejected: %s" % detail
            )
        return BadResponseError("bad request (HTTP %s)" % status)
    return ServerError("server error (HTTP %s)" % status)


class ApiClient:
    """Minimal JSON HTTP client for the Control API.

    All requests carry the bearer token in the Authorization
    header. Raises ApiClientError subclasses on failure; callers
    decide how to surface them.
    """

    def __init__(
        self,
        host="127.0.0.1",
        port=8787,
        token="",
        timeout=5.0,
    ):
        self.host = str(host) or "127.0.0.1"
        self.port = int(port) if port else 8787
        self.token = token or ""
        self.timeout = float(timeout) if timeout else 5.0

    def base_url(self):
        return "http://%s:%d" % (self.host, self.port)

    def _open(self, method, path, body=None):
        url = self.base_url() + path
        # B310 hardening: urlopen would honour file:// and other custom
        # schemes. This client only ever speaks to the Control API over
        # plain HTTP, so refuse anything else before opening a request.
        _scheme = _urlparse.urlparse(url).scheme
        if _scheme not in ("http", "https"):
            raise ValueError(
                "refusing non-HTTP(S) URL scheme: %r" % _scheme)

        data = None

        headers = {"Authorization": "Bearer %s" % self.token}

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = _urlrequest.Request(url, data=data, headers=headers, method=method)

        try:
            with _urlrequest.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 (scheme validated above)
                raw = resp.read()
        except _urlerror.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except _urlerror.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise TimeoutErrorWithCause(
                    "request timed out after %ss" % self.timeout
                ) from exc
            raise ConnectionErrorWithCause(
                "cannot reach Control API at %s" % url
            ) from exc
        except TimeoutError as exc:
            raise TimeoutErrorWithCause(
                "request timed out after %ss" % self.timeout
            ) from exc
        else:
            status = resp.status

        return self._decode(status, raw, path)

    def _decode(self, status, raw, path):
        if raw is None:
            raw = b""
        text = raw.decode("utf-8", errors="replace") if raw else ""

        body = None

        if text:
            try:
                body = json.loads(text)
            except ValueError:
                if status == 200:
                    raise BadResponseError(
                        "malformed JSON from %s" % path
                    )
                # non-200 + non-JSON: keep the status classification
                body = None

        exc = _classify(status, body)

        if exc is not None:
            raise exc

        return body

    # -----------------------------------------------------
    # Request verbs
    # -----------------------------------------------------

    def get(self, path):
        """GET a JSON endpoint and return its parsed body."""

        return self._open("GET", path)

    def post(self, path, payload):
        """POST a JSON payload and return the parsed body."""

        return self._open("POST", path, body=payload)


class ReconnectingClient:
    """Periodically probes connectivity so callers can track a
    DISCONNECTED / CONNECTED state without blocking.

    Exposes conn_error (last ApiClientError or None) and
    last_ok (unix timestamp of the last successful round-trip).
    """

    def __init__(self, api, interval=3.0):
        self.api = api
        self.interval = float(interval)
        self.conn_error = None
        self.last_ok = None

    def probe(self):
        """One connectivity hint: try GET /health and remember the
        result. Returns True when reachable."""

        try:
            payload = self.api.get("/health")
        except ClientError as exc:
            self.conn_error = exc
            return False
        self.conn_error = None
        self.last_ok = time.time()
        return payload is not None

    def healthy(self):
        return self.conn_error is None and self.last_ok is not None

    def describe(self):
        if self.healthy():
            return "connected"
        if self.last_ok is None:
            return "disconnected"
        return "disconnected"
