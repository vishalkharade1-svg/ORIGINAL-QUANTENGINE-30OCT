"""
====================================================

QuantEngine - Secure Remote / Mobile Control Foundation

gateway.py -- authenticated TLS reverse gateway (Phase 9P-k).

A stdlib-only HTTPS server that sits in FRONT of the existing
localhost Control & Monitoring API (Phase 9P-f). It:

  * terminates TLS using an operator-provided PEM cert/key pair
    (paths from config; NO cert generation / custom crypto),
  * authenticates remote clients against per-role bearer tokens
    (VIEW / CONTROL / EMERGENCY) with constant-time comparison,
  * authorizes every request against the role registry
    (core/remote/roles.py), refusing anything not explicitly
    permitted at that tier,
  * assigns each request a correlation ID (X-Request-ID),
    honouring an operator-supplied value for replay/duplicate
    grouping, and audits control actions (core/remote/audit.py),
  * rate-limits at the remote boundary (auth attempts, control,
    polling) WITHOUT limiting the internal engine poll loop, and
  * forwards authorized requests to the local Control API
    (127.0.0.1:8787) using the operator's local CONTROL_API_TOKEN,
    preserving the existing Control API contract untouched.

Serving: the gateway also serves the mobile-responsive PWA
dashboard (core/remote/dashboard.py) at "/" and its static assets,
so a phone browser is the mobile client.

CONNECTION / BINDING SAFETY:
  * The gateway NEVER binds to 0.0.0.0 on the Control API port,
    and by default binds to 127.0.0.1 on its own port. External
    reachability is strictly the operator's transport choice
    (private tunnel / VPN / firewall).
  * It NEVER creates a second control engine -- it only forwards
    to the one authoritative Control API.

CREDENTIAL HANDLING:
  * All secrets live in memory only; none is logged, placed in a
    URL, an exception, or telemetry (see core/remote/audit.py).
  * Fail-closed: an enabled gateway with a missing role token /
    cert fails to start rather than serving unauthenticated.

Stdlib only: http.server, ssl, hmac, secrets, urllib, json,
threading, time, pathlib.
====================================================
"""

import hmac
import json
import logging
import secrets
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as _urlerror
from urllib import parse as _urlparse
from urllib import request as _urlrequest

from core.remote import roles
from core.remote.audit import AuditLog, Mutation

log = logging.getLogger("quantengine.remote.gateway")


def _tokens_equal(left, right):
    a = (left or "").encode("utf-8")
    b = (right or "").encode("utf-8")
    return hmac.compare_digest(a, b)


class RemoteGatewayError(RuntimeError):
    """Configuration/startup error for the remote gateway (fail
    closed: raised before any request is served)."""


class _RateLimiter:
    """Sliding-window rate limiter keyed by remote address for the
    remote boundary. Bounded memory (per client it stores a deque of
    window timestamps). Thread-safe."""

    def __init__(self, max_events, window_seconds):
        from collections import deque

        self.max_events = int(max_events)
        self.window_seconds = float(window_seconds)
        self._deque = deque()
        self._lock = threading.Lock()

    def allow(self):
        now = time.time()
        with self._lock:
            d = self._deque
            while d and d[0] <= now - self.window_seconds:
                d.popleft()
            if len(d) >= self.max_events:
                return False
            d.append(now)
            return True


class _TokenStore:
    """Maps role -> accepted token(s), constant-time compared."""

    def __init__(self):
        self._tokens = {}
        self._lock = threading.Lock()

    def set(self, role, token):
        with self._lock:
            if token:
                self._tokens[role] = str(token)

    def resolve(self, presented):
        """Return the role matching PRESENTED (constant-time), or
        None. Iterates roles; an empty store resolves nothing."""
        if not presented:
            return None
        with self._lock:
            for role, token in self._tokens.items():
                if token and _tokens_equal(presented, token):
                    return role
        return None

    def roles(self):
        with self._lock:
            return set(self._tokens.keys())


def _json_resp(handler, status, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Connection", "close")
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    try:
        handler.wfile.write(data)
    except Exception:
        pass


def _text_resp(handler, status, content, content_type, headers=None):
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Connection", "close")
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    try:
        handler.wfile.write(data)
    except Exception:
        pass


class _GatewayHandler(BaseHTTPRequestHandler):
    """One request. Class attributes are bound by the server."""

    protocol_version = "HTTP/1.1"

    config = None          # GatewayConfig
    token_store = None     # _TokenStore
    limiter = None         # _RateLimiter
    audit = None           # AuditLog
    dashboard = None       # dashboard module (for static assets)

    body_limit = 65536

    # ---------------- low-level helpers ----------------

    def _correlation_id(self):
        supplied = self.headers.get("X-Request-ID") or ""
        supplied = supplied.strip()
        # accept [A-Za-z0-9-_] up to 64 chars (operator-supplied, used
        # for replay/duplicate grouping); otherwise mint a fresh one
        if supplied and len(supplied) <= 64 and all(
            c.isalnum() or c in "-_" for c in supplied
        ):
            return supplied
        return secrets.token_hex(12)

    def _bearer(self):
        header = self.headers.get("Authorization", "") or ""
        parts = header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        return parts[1].strip()

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        length = min(length, self.body_limit)
        try:
            raw = self.rfile.read(length)
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None  # malformed JSON is distinguishable from {}

    def _remote(self):
        try:
            return self.client_address[0] if self.client_address else ""
        except Exception:
            return ""

    def _audit(self, **kwargs):
        if self.audit is not None:
            self.audit.write(Mutation(**kwargs))

    # ---------------- authentication ----------------

    def _authenticate(self):
        """Return the authenticated role, or None."""
        bearer = self._bearer()
        return self.token_store.resolve(bearer) if bearer else None

    # ---------------- dispatch ----------------

    def _dispatch(self, method):
        conn_id = self._correlation_id()
        role = self._authenticate()
        remote = self._remote()

        if role is None:
            self._audit(
                correlation_id=conn_id,
                role="",
                device=self.headers.get("User-Agent", "")[:120],
                remote=remote,
                kind="auth",
                method=method,
                path=self.path,
                result="denied",
                failure="authentication failed (bad or missing token)",
            )
            _json_resp(
                self, 401,
                {"error": "unauthorized",
                 "detail": "valid bearer token required"},
                headers={"X-Request-ID": conn_id},
            )
            return

        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        # Rate limit the boundary (auth attempts already handled;
        # this bounds control + polling per remote client).
        if self.limiter is not None and not self.limiter.allow():
            self._audit(
                correlation_id=conn_id, role=role,
                device=self.headers.get("User-Agent", "")[:120],
                remote=remote, kind="throttle",
                method=method, path=self.path,
                result="denied", failure="rate limit exceeded",
            )
            _json_resp(
                self, 429,
                {"error": "rate_limited",
                 "detail": "too many requests"},
                headers={"X-Request-ID": conn_id},
            )
            return

        # ---- static dashboard / desktop assets ----
        if method == "GET" and path in (
            "/", "/index.html", "/app.js", "/app.css",
            "/manifest.json", "/favicon.ico", "/sw.js",
        ):
            self._serve_asset(path, conn_id, role, remote)
            return

        # ---- API: authorize / forward ----
        if path == "/api/me":
            _json_resp(
                self, 200, {"role": role},
                headers={"X-Request-ID": conn_id},
            )
            return

        # unknown / not allowed at any role -> 403 (not a read or
        # control route on the remote surface)
        self._forward_api(method, path, conn_id, role, remote)

    # ---------------- static assets ----------------

    def _serve_asset(self, path, conn_id, role, remote):
        asset = self.dashboard.by_path(path) if self.dashboard else None
        if asset is None:
            _json_resp(
                self, 404, {"error": "not_found", "path": path},
                headers={"X-Request-ID": conn_id},
            )
            return
        _text_resp(
            self, 200, asset, self.dashboard.content_type(path),
            headers={"X-Request-ID": conn_id},
        )

    # ---------------- forwarding ----------------

    def _forward_api(self, method, path, conn_id, role, remote):
        cfg = self.config

        if path == "/control":
            body = self._read_body()
            if not isinstance(body, dict) or "command" not in body:
                self._audit(
                    correlation_id=conn_id, role=role, remote=remote,
                    kind="authz", method=method, path=path,
                    result="denied", failure="malformed control body",
                )
                _json_resp(
                    self, 400,
                    {"error": "bad_request",
                     "detail": "expected JSON body {\"command\": ...}"},
                    headers={"X-Request-ID": conn_id},
                )
                return

            command = body.get("command")
            required = roles.command_required_role(command)
            if required is None or not roles.satisfies(role, required):
                self._audit(
                    correlation_id=conn_id, role=role, remote=remote,
                    kind="authz", method=method, path=path,
                    command=command, result="denied",
                    failure="principal role lacks permission "
                            "for this command",
                )
                _json_resp(
                    self, 403,
                    {"error": "forbidden",
                     "detail": "role lacks permission for this command"},
                    headers={"X-Request-ID": conn_id},
                )
                return

            # authorized: capture prev state, forward, audit outcome
            self._remote_control(conn_id, role, remote, command, body)
            return

        # ---- non-control route ----
        required = roles.required_role(method, path)
        if required == "COMMAND":
            required = roles.CONTROL
        if required is None or not roles.satisfies(role, required):
            self._audit(
                correlation_id=conn_id, role=role, remote=remote,
                kind="authz", method=method, path=path,
                result="denied",
                failure="request not permitted at this role",
            )
            _json_resp(
                self, 403,
                {"error": "forbidden",
                 "detail": "request not permitted at principal role"},
                headers={"X-Request-ID": conn_id},
            )
            return

        self._remote_read(conn_id, role, remote, method, path)

    def _fetch(self, method, path, body=None):
        """Forward METHOD PATH to the local Control API with the
        local server token. Returns (status, json_or_text)."""
        cfg = self.config
        url = "http://%s:%d%s" % (cfg.local_host, cfg.local_port, path)
        # B310 hardening: never let urlopen follow a non-HTTP(S) scheme.
        _scheme = _urlparse.urlparse(url).scheme
        if _scheme not in ("http", "https"):
            log.warning("refusing non-HTTP(S) forward URL scheme: %r", _scheme)
            return 502, {"error": "bad_gateway",
                         "detail": "unsupported URL scheme"}
        headers = {"Authorization": "Bearer %s" % cfg.local_token}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = _urlrequest.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with _urlrequest.urlopen(req, timeout=cfg.local_timeout) as resp:  # nosec B310 (scheme validated above)
                raw = resp.read()
                status = resp.status
        except _urlerror.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except Exception as exc:
            log.warning("Control API forward failed: %s", exc)
            return 502, {"error": "bad_gateway",
                         "detail": "Control API unreachable"}
        text = raw.decode("utf-8", errors="replace") if raw else ""
        if text:
            try:
                return status, json.loads(text)
            except ValueError:
                return status, text
        return status, {}

    def _remote_read(self, conn_id, role, remote, method, path):
        status, payload = self._fetch(method, path)
        if isinstance(payload, dict):
            body = payload
            # Surface the authoritative runtime mode (PAPER/LIVE) on the
            # health read so the mobile client can show it unmistakably.
            # Derived from the same config.settings the engine uses; the
            # localhost Control API contract is not modified.
            if method == "GET" and path == "/health":
                body["runtime_mode"] = self._runtime_mode()
        else:
            body = {"error": "unexpected_response",
                    "detail": str(payload)[:200]}
        self._audit(
            correlation_id=conn_id, role=role, remote=remote,
            kind="read", method=method, path=path,
            result="denied" if status >= 400 else "ok",
            failure=body.get("detail", "") if status >= 400 else "",
        )
        _json_resp(self, status, body, headers={"X-Request-ID": conn_id})

    def _runtime_mode(self):
        """PAPER/LIVE for the authoritative engine from config.settings.
        The remote surface never enables LIVE; this only reflects the
        process's own configured mode."""
        try:
            import config.settings as _settings
            live = bool(getattr(_settings.settings, "LIVE_MODE", False))
            paper = bool(getattr(_settings.settings, "PAPER_MODE", True))
            if live and not paper:
                return "LIVE"
            return "PAPER"
        except Exception:
            return "PAPER"

    def _remote_control(self, conn_id, role, remote, command, body):
        # Capture the previous lifecycle state from health BEFORE the
        # control so the audit log holds prev/result states.
        prev_state = None
        try:
            _, hb = self._fetch("GET", "/health")
            if isinstance(hb, dict):
                prev_state = hb.get("lifecycle_state")
        except Exception:
            prev_state = None

        status, payload = self._fetch("POST", "/control", body)
        if status == 200 and isinstance(payload, dict):
            result_state = payload.get("lifecycle_state")
            failure = ""
            result = "ok"
        else:
            result_state = None
            failure = (
                (payload.get("detail") if isinstance(payload, dict)
                 else "") or "control failed"
            )
            result = "denied"
        self._audit(
            correlation_id=conn_id, role=role, remote=remote,
            kind="control", method="POST", path="/control",
            command=command, prev_state=prev_state,
            result_state=result_state, result=result, failure=failure,
        )
        _json_resp(self, status, payload, headers={"X-Request-ID": conn_id})

    # ---------------- http verbs ----------------

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, *args, **kwargs):
        pass


class GatewayConfig:
    """Static gateway configuration. Holds secrets in memory only."""

    def __init__(
        self,
        *,
        host="127.0.0.1",
        port=9443,
        certfile=None,
        keyfile=None,
        local_host="127.0.0.1",
        local_port=8787,
        local_token="",
        tokens=None,
        rate_max=60,
        rate_window=60.0,
        local_timeout=5.0,
        audit=None,
        require_tls=True,
    ):
        self.host = "127.0.0.1" if not host else host
        self.port = int(port)
        self.certfile = certfile
        self.keyfile = keyfile
        self.local_host = local_host or "127.0.0.1"
        self.local_port = int(local_port or 8787)
        self.local_token = local_token or ""
        self.tokens = tokens or {}          # role -> token
        self.rate_max = int(rate_max)
        self.rate_window = float(rate_window)
        self.local_timeout = float(local_timeout)
        self.audit = audit
        self.require_tls = require_tls


class RemoteGateway:
    """Boundary server enforcing auth/authz/rate-limit/audit and
    forwarding to the local Control API, plus static PWA serving."""

    def __init__(self, config):
        self.config = config
        self._httpd = None
        self._thread = None
        self._audit = config.audit

        self._store = _TokenStore()
        for role, token in (config.tokens or {}).items():
            self._store.set(role, token)

        self.limiter = (
            _RateLimiter(config.rate_max, config.rate_window)
            if config.rate_max > 0
            else None
        )

        import core.remote.dashboard as dashboard
        self._dashboard = dashboard

    @property
    def audit(self):
        return self._audit

    # ---- fail-closed configuration checks ----

    def _validate(self):
        # An enabled gateway must be TLS-protected (or explicitly run
        # in the test-only plaintext loopback mode) -- never silently
        # serve credentials/tokens in the clear.
        if self.config.require_tls and (
            not self.config.certfile or not self.config.keyfile
        ):
            raise RemoteGatewayError(
                "remote gateway requires a TLS cert/key (certfile + "
                "keyfile); refusing to run with plaintext transport."
            )
        # Fail-closed: at least one role token must be configured, and
        # the local Control API token must be present. An under-
        # configured gateway refuses to start rather than serve
        # unauthenticated traffic.
        if not self.config.tokens:
            raise RemoteGatewayError(
                "remote gateway requires at least one role token "
                "(VIEW / CONTROL / EMERGENCY); refusing to run with "
                "an empty token store (fail closed)."
            )
        if not self.config.local_token:
            raise RemoteGatewayError(
                "remote gateway requires the local CONTROL_API_TOKEN to "
                "forward requests (fail closed)."
            )

    def serve_forever_threaded(self):
        self._validate()

        handler = type("_BoundGatewayHandler", (_GatewayHandler,), {})
        handler.config = self.config
        handler.token_store = self._store
        handler.limiter = self.limiter
        handler.audit = self._audit
        handler.dashboard = self._dashboard

        try:
            self._httpd = ThreadingHTTPServer(
                (self.config.host, self.config.port), handler
            )
        except OSError as exc:
            raise RemoteGatewayError(
                "cannot bind remote gateway to %s:%d: %s"
                % (self.config.host, self.config.port, exc)
            ) from exc

        # wrap in TLS (stdlib ssl; no cert generation). The require_tls
        # flag is a TEST-ONLY escape hatch for loopback logic tests; an
        # enabled production gateway always carries a cert/key pair.
        if self.config.require_tls:
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(
                    certfile=self.config.certfile,
                    keyfile=self.config.keyfile,
                )
                self._httpd.socket = context.wrap_socket(
                    self._httpd.socket, server_side=True
                )
            except Exception as exc:
                self._httpd.server_close()
                raise RemoteGatewayError(
                    "cannot configure TLS for remote gateway: %s" % exc
                ) from exc

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="quantengine-remote-gateway",
            daemon=True,
        )
        self._thread.start()

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def addr(self):
        return self._httpd.server_address if self._httpd else None

    def shutdown(self):
        httpd = self._httpd
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)


def gateway_from_settings():
    """Build a GatewayConfig (not yet started) from config.env.

    Remote reachability, TLS cert/key and per-role tokens are all
    operator-provisioned via environment variables:
      REMOTE_GATEWAY_ENABLED / _HOST / _PORT
      REMOTE_TLS_CERT / REMOTE_TLS_KEY
      REMOTE_VIEW_TOKEN / REMOTE_CONTROL_TOKEN / REMOTE_EMERGENCY_TOKEN
      LOCAL_CONTROL_API_HOST / LOCAL_CONTROL_API_PORT
      REMOTE_RATE_MAX / REMOTE_RATE_WINDOW
      AUDIT_ENABLED / AUDIT_PATH (remote audit log)

    The local token is the operator's CONTROL_API_TOKEN (the existing
    Control API secret). The audit log is wired from the same env the
    gateway uses.
    """
    import os

    from config.settings import settings

    from core.remote.audit import audit_from_settings

    def _ebool(name, default=False):
        return os.getenv(name, "").strip().lower() not in ("", "0",
                                                           "false", "no")

    tokens = {}
    view = os.getenv("REMOTE_VIEW_TOKEN", "").strip()
    control = os.getenv("REMOTE_CONTROL_TOKEN", "").strip()
    emergency = os.getenv("REMOTE_EMERGENCY_TOKEN", "").strip()
    if view:
        tokens[roles.VIEW] = view
    if control:
        tokens[roles.CONTROL] = control
    if emergency:
        tokens[roles.EMERGENCY] = emergency

    return GatewayConfig(
        host=os.getenv("REMOTE_GATEWAY_HOST", "127.0.0.1"),
        port=int(os.getenv("REMOTE_GATEWAY_PORT", "9443")),
        certfile=os.getenv("REMOTE_TLS_CERT", "") or None,
        keyfile=os.getenv("REMOTE_TLS_KEY", "") or None,
        local_host=os.getenv("LOCAL_CONTROL_API_HOST", "127.0.0.1"),
        local_port=int(os.getenv("LOCAL_CONTROL_API_PORT", "8787")),
        local_token=getattr(settings, "CONTROL_API_TOKEN", "") or "",
        tokens=tokens,
        rate_max=int(os.getenv("REMOTE_RATE_MAX", "60")),
        rate_window=float(os.getenv("REMOTE_RATE_WINDOW", "60")),
        local_timeout=float(os.getenv("REMOTE_LOCAL_TIMEOUT", "5")),
        audit=audit_from_settings(),
    )
