"""
====================================================

QuantEngine

Control & Monitoring API - read-only-first service

Phase 9P-f.

A minimal, stdlib-only, read-first monitoring surface plus a
safe PAPER control seam for the canonical RealTimeEngine. It is
intentionally NOT a trading-logic surface:

    API -> Command/Query -> Existing Runtime

    NOT: API -> strategy / risk / order logic.

The engine stays authoritative. This module only:

  - serves GET read endpoints that DELEGATE to the engine's
    existing snapshot/state/report methods (statuses, performance,
    ledger, portfolio.snapshot, runtime.state, subscriptions),
  - serves a POST /control endpoint whose verbs are a HARD
    ALLOWLIST (start / stop / restart / emergency_stop) forwarded
    to the EngineLifecycle manager, and
  - serves authenticated GET/POST /risk-policy for the operator's
    global and exact-instrument 1:1..1:20 + trailing policy.
  - guards every request with a bearer token (constant-time
    compare) and binds to localhost only.

There is no order-submission endpoint. Risk-policy changes are
restricted to validated policy fields and are consumed by the
existing risk/execution authorities; they cannot create, cancel,
or modify an order directly. Even the read surface is defensive: a serialization
fault returns a structured 500, never bubbles an exception into
the http layer.

Stdlib only: http.server, json, hmac, threading, dataclasses.
====================================================
"""

import hmac
import json
import os
import threading
import time
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.runtime.lifecycle import ControlCommandError
from core.risk.trading_policy import trading_policy_manager

CONTROL_COMMANDS = frozenset({"start", "stop", "restart", "emergency_stop", "pause", "resume"})

# Static-shell exception (documented): GET paths serving no data
# and no secrets bypass bearer authorization so a browser can
# load the dashboard shell directly. The shell itself carries no
# token and performs no requests without the operator-entered
# bearer token (memory-only); every data route — including all
# other preview JSON routes — still requires authorization.
PUBLIC_GET_PATHS = frozenset({"/dashboard"})


def _exchange():
    import config.settings as _settings

    return getattr(_settings.settings, "exchange", "DELTA")


def _tokens_equal(left, right):
    """Constant-time string comparison for bearer tokens."""

    a = (left or "").encode("utf-8")

    b = (right or "").encode("utf-8")

    return hmac.compare_digest(a, b)


_SECRET_ENV_VARS = (
    "DELTA_API_KEY", "DELTA_API_SECRET", "CONTROL_API_TOKEN",
)


def _safe_detail(exc, limit=300):
    """Bounded exception detail with configured secret values redacted.

    API error responses must never carry credentials even if an upstream
    exception message interpolates one (headers, URLs, diagnostics).
    Secrets are read from process memory only, never logged or stored.
    """
    try:
        text = str(exc)
    except Exception:
        return "unavailable"
    for var in _SECRET_ENV_VARS:
        try:
            secret = os.environ.get(var, "")
        except Exception:
            secret = ""
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:limit]


def _json_safe(value):
    """Recursively convert a snapshot into JSON-safe primitives,
    tolerating dataclasses, exceptions, sets, and non-serializable
    leaves. Never raises."""

    if value is None or isinstance(value, (str, int, float, bool)):

        return value

    if isinstance(value, dict):

        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):

        return [_json_safe(v) for v in value]

    if isinstance(value, set):

        return [_json_safe(v) for v in sorted(value, key=str)]

    if is_dataclass(value):

        try:

            return _json_safe(asdict(value))

        except Exception:

            return _json_safe(vars(value) if hasattr(value, "__dict__")
                              else value)

    if hasattr(value, "__dict__"):

        return _json_safe(vars(value))

    try:

        if isinstance(value, (BaseException,)):
            return {"error": _safe_detail(value)}

        json.dumps(value)

        return value

    except Exception:

        return str(value)


# =====================================================
# Read mappers -- pure delegation to the existing runtime
# =====================================================


def _health_snapshot(engine, lifecycle):
    """Engine + lifecycle health (no invented engine state)."""
    base = lifecycle.health()

    base["exchange"] = _exchange()

    base["timeframe"] = getattr(engine, "timeframe", None)

    base["started"] = bool(getattr(engine, "started", False))

    base["runtimes"] = len(getattr(engine, "runtimes", {}) or {})

    # Phase 96: fold subscription staleness into health. A started
    # engine whose feeds are all STALE/FAILED must not report as
    # healthy: entries cannot occur without candles, but open
    # exposure would sit unmanaged, so the feed verdict is part of
    # health. Additive only; existing keys untouched.
    base["data_feed"] = _feed_health(engine)

    return base


_DEGRADED_FEED_STATES = frozenset({"STALE", "FAILED"})


def _feed_state_of(state):
    """Best-effort status string from a subscription state object."""
    if state is None:
        return "UNKNOWN"
    if isinstance(state, str):
        return state.upper()
    status = getattr(state, "status", None)
    if isinstance(status, str) and status:
        return status.upper()
    if isinstance(state, dict):
        status = state.get("status", state.get("state"))
        if isinstance(status, str) and status:
            return status.upper()
    return "UNKNOWN"


def _feed_health(engine):
    """Deterministic feed-freshness verdict from 6D subscription states.

    fresh=True only when at least one subscription is tracked and none
    is STALE/FAILED. Zero tracked symbols -> fresh=False with an
    explicit reason (no data flowing is not health). Never raises.
    """
    try:
        subs = getattr(engine, "subscriptions", None)
        raw = (subs.statuses() or {}) if subs is not None else {}
    except Exception:
        return {"fresh": False, "tracked": 0, "live": [],
                "degraded": {}, "reason": "statuses_unreadable"}
    live = []
    degraded = {}
    for symbol, state in raw.items():
        status = _feed_state_of(state)
        if status in _DEGRADED_FEED_STATES:
            degraded[str(symbol)] = status
        else:
            live.append(str(symbol))
    tracked = len(raw)
    if tracked == 0:
        return {"fresh": False, "tracked": 0, "live": [],
                "degraded": {}, "reason": "no_subscriptions"}
    if degraded:
        return {"fresh": False, "tracked": tracked,
                "live": sorted(live), "degraded": degraded,
                "reason": "stale_or_failed_feeds"}
    return {"fresh": True, "tracked": tracked, "live": sorted(live),
            "degraded": {}, "reason": "all_feeds_live_or_transitional"}


def _universe_snapshot(engine):
    """Eligible universe + per-symbol reasons via the canonical
    RefreshScheduler.last_universe and the engine._instruments."""

    scheduler = getattr(engine, "refresh_scheduler", None)

    last = getattr(scheduler, "last_universe", None) if scheduler else None

    reasons = {}

    if last is not None and hasattr(last, "reasons"):

        reasons = dict(getattr(last, "reasons", {}) or {})

    instruments = getattr(engine, "_instruments", {}) or {}

    symbols = sorted(instruments.keys())

    return {
        "mode": getattr(engine, "universe_mode", "explicit"),
        "timeframe": getattr(engine, "timeframe", None),
        "eligible_count": len(symbols),
        "eligible_symbols": symbols,
        "reasons": _json_safe(reasons),
        "last_run": (
            getattr(scheduler, "last_run", None) if scheduler else None
        ),
        "runs": getattr(scheduler, "runs", 0) if scheduler else 0,
    }


def _subscription_snapshot(engine):
    """Per-symbol subscription status via the 6D manager."""

    subs = getattr(engine, "subscriptions", None)

    if subs is None:

        return {"enabled": False, "symbols": []}

    statuses = {}

    try:

        raw = subs.statuses() or {}

    except Exception:

        raw = {}

    for symbol, state in raw.items():

        statuses[str(symbol)] = _json_safe(state)

    return {
        "enabled": True,
        "symbols": sorted(statuses.keys()),
        "statuses": statuses,
        "errors": _json_safe(getattr(subs, "errors", [])),
    }


def _runtime_status_snapshot(engine):
    """Per-symbol runtime snapshot merged with subscription status
    via engine.statuses() (the canonical observable surface)."""

    try:

        statuses = engine.statuses()

    except Exception:

        statuses = {}

    return _json_safe(statuses)


def _market_snapshot(engine):
    """Latest per-symbol MarketState from each runtime pipeline
    context."""

    out = {}

    runtimes = getattr(engine, "runtimes", {}) or {}

    for key, runtime in runtimes.items():

        context = getattr(runtime, "pipeline", None)

        if context is None:

            continue

        market = getattr(context, "market", None)

        if market is None:

            continue

        out[getattr(runtime, "symbol", str(key))] = _json_safe(market)

    return out


def _signal_snapshot(engine):
    """Per-symbol latest signal(s) from each runtime pipeline
    context. The engine's short-lived per-candle signal fields are
    surfaced verbatim; empty when no signal is currently set."""

    out = {}

    runtimes = getattr(engine, "runtimes", {}) or {}

    for key, runtime in runtimes.items():

        context = getattr(runtime, "pipeline", None)

        if context is None:

            continue

        symbol = getattr(runtime, "symbol", str(key))

        out[symbol] = {
            "signal": _json_safe(getattr(context, "execution_signal", None)),
            "signals": _json_safe(
                getattr(context, "execution_signals", None)
            ),
        }

    return out


def _positions_snapshot(engine):
    """Per-symbol open positions: the runtime's current_trade plus
    any OPEN trades on its ledger."""

    out = {}

    runtimes = getattr(engine, "runtimes", {}) or {}

    for key, runtime in runtimes.items():

        symbol = getattr(runtime, "symbol", str(key))

        current = getattr(runtime, "current_trade", None)

        open_trades = []

        try:

            registry = getattr(runtime, "ledger", None)

            if registry is not None and hasattr(registry, "open"):

                open_trades = list(registry.open())

        except Exception:

            open_trades = []

        out[symbol] = {
            "current_trade": _json_safe(current),
            "open_trades": _json_safe(open_trades),
        }

    return out


def _orders_snapshot(engine):
    """Per-symbol dry-run order intents from the paper execution
    port / broker audit trail (never exchange orders)."""

    out = {}

    runtimes = getattr(engine, "runtimes", {}) or {}

    for key, runtime in runtimes.items():

        symbol = getattr(runtime, "symbol", str(key))

        intents = list(getattr(runtime, "executed_intents", ()) or ())

        out[symbol] = {
            "count": len(intents),
            "intents": _json_safe(intents),
        }

    return out


def _account_snapshot(engine):
    """Aggregate account + shared capital from the canonical
    portfolio snapshot and per-runtime accounts."""

    runtimes = getattr(engine, "runtimes", {}) or {}

    balance = 0.0

    equity = 0.0

    accounts = []

    for runtime in runtimes.values():

        account = getattr(runtime, "account", None)

        if account is None:

            continue

        accounts.append(_json_safe(account))

        balance += float(getattr(account, "balance", 0.0) or 0.0)

        equity += float(getattr(account, "equity", 0.0) or 0.0)

    portfolio = getattr(engine, "portfolio", None)

    portfolio_snapshot = None

    if portfolio is not None and hasattr(portfolio, "snapshot"):

        try:

            portfolio_snapshot = _json_safe(portfolio.snapshot())

        except Exception:

            portfolio_snapshot = None

    return {
        "per_runtime": accounts,
        "sum_balance": balance,
        "sum_equity": equity,
        "shared_capital": portfolio_snapshot,
    }


def _risk_snapshot(engine):
    """Risk state: shared portfolio snapshot (exposure, current
    risk, direction risk) + per-runtime risk-relevant account state."""

    portfolio_snapshot = None

    portfolio = getattr(engine, "portfolio", None)

    if portfolio is not None and hasattr(portfolio, "snapshot"):

        try:

            portfolio_snapshot = _json_safe(portfolio.snapshot())

        except Exception:

            portfolio_snapshot = None

    runtimes = getattr(engine, "runtimes", {}) or {}

    per_symbol = {}

    for key, runtime in runtimes.items():

        symbol = getattr(runtime, "symbol", str(key))

        account = getattr(runtime, "account", None)

        state = getattr(account, "state", None) if account else None

        per_symbol[symbol] = _json_safe(
            {
                "drawdown": getattr(state, "drawdown", None),
                "drawdown_percent": getattr(state, "drawdown_percent", None),
                "current_risk": getattr(state, "portfolio_risk", None),
                "exposure": getattr(state, "exposure", None),
            }
        )

    return {
        "portfolio": portfolio_snapshot,
        "per_symbol": per_symbol,
    }


def _performance_snapshot(engine):
    """Canonical aggregate + per-symbol performance reports via
    engine.performance() (the single 9P-b/9P-c analytics source)."""

    aggregate = None

    per_symbol = {}

    try:

        aggregate = _json_safe(engine.performance(None))

    except Exception:

        aggregate = None

    runtimes = getattr(engine, "runtimes", {}) or {}

    for key, runtime in runtimes.items():

        symbol = getattr(runtime, "symbol", str(key))

        try:

            per_symbol[symbol] = _json_safe(engine.performance(symbol))

        except Exception:

            per_symbol[symbol] = None

    return {
        "aggregate": aggregate,
        "per_symbol": per_symbol,
    }


def _errors_snapshot(engine):
    """Aggregated error/log-ish events from the canonical error
    holders: RefreshScheduler.errors + subscription errors."""

    errors = []

    scheduler = getattr(engine, "refresh_scheduler", None)

    if scheduler is not None:

        for exc in getattr(scheduler, "errors", []) or []:

            errors.append(
                {"source": "refresh_scheduler", "error": _safe_detail(exc)}
            )

    subs = getattr(engine, "subscriptions", None)

    if subs is not None:

        for entry in getattr(subs, "errors", []) or []:

            if isinstance(entry, tuple) and len(entry) >= 3:

                errors.append(
                    {
                        "source": "subscriptions",
                        "symbol": str(entry[0]),
                        "operation": str(entry[1]),
                        "error": _safe_detail(entry[2]),
                    }
                )

            else:

                errors.append({"source": "subscriptions", "error": _safe_detail(entry)})

    return {"errors": _json_safe(errors)}


# =====================================================
# Route table
# =====================================================


def _assert_paper_capable(engine):
    """Defensive runtime assertion that control targets a PAPER
    engine only. Refuses control when the process is configured for
    LIVE execution, or when any active runtime is not dry_run."""

    def raise_paper_guard(reason):
        raise ControlCommandError(
            "Control is PAPER-only and was refused: %s" % reason
        )

    try:

        import config.settings as _settings

        live = bool(getattr(_settings.settings, "LIVE_MODE", False))

        paper = bool(getattr(_settings.settings, "PAPER_MODE", True))

    except Exception:

        live, paper = False, True

    if live and not paper:

        raise_paper_guard(
            "LIVE execution is configured; only start/stop/restart "
            "of the PAPER runtime is permitted."
        )

    runtimes = getattr(engine, "runtimes", {}) or {}

    for runtime in runtimes.values():

        runtime_engine = getattr(runtime, "engine", None)

        dry_run = getattr(runtime_engine, "dry_run", None)

        if dry_run is False:

            raise_paper_guard(
                "an active runtime is not in dry_run (PAPER) mode."
            )


def _build_routes(engine, lifecycle):
    """Map (method, path) -> callable returning (JSON body dict).
    GET routes delegate to the read mappers; POST /control routes to
    the lifecycle allowlist."""

    reads = {
        "/health": lambda: _health_snapshot(engine, lifecycle),
        "/universe": lambda: _universe_snapshot(engine),
        "/subscriptions": lambda: _subscription_snapshot(engine),
        "/runtimes": lambda: _runtime_status_snapshot(engine),
        "/market": lambda: _market_snapshot(engine),
        "/signals": lambda: _signal_snapshot(engine),
        "/positions": lambda: _positions_snapshot(engine),
        "/orders": lambda: _orders_snapshot(engine),
        "/account": lambda: _account_snapshot(engine),
        "/risk": lambda: _risk_snapshot(engine),
        "/performance": lambda: _performance_snapshot(engine),
        "/errors": lambda: _errors_snapshot(engine),
    }

    def control_handler(body):
        """POST /control -- PAPER-only, allowlisted verbs only."""

        if not isinstance(body, dict) or "command" not in body:

            raise ValueError("expected JSON body {\"command\": ...}")

        command = body["command"]

        if command not in CONTROL_COMMANDS:

            raise ControlCommandError(
                "Unsupported control command: %r. Allowed (PAPER only): "
                "%s" % (command, ", ".join(sorted(CONTROL_COMMANDS)))
            )

        _assert_paper_capable(engine)

        state = lifecycle.command(command)

        return {"command": command, "lifecycle_state": state}

    def risk_policy_get():
        return trading_policy_manager().snapshot()

    def risk_policy_set(body):
        if not isinstance(body, dict):
            raise ValueError("expected JSON policy object")
        manager = trading_policy_manager()
        values = dict(body.get("policy") or {})
        allowed = {
            "min_rr", "max_rr", "trailing_enabled",
            "trailing_activation_r", "trailing_distance_r",
            "trailing_method", "trailing_step_r",
            "auto_exit_on_opposite_signal",
        }
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError("unsupported policy fields: %s" % ", ".join(unknown))
        if not values:
            raise ValueError("policy must contain at least one supported field")
        current = manager.get(body.get("symbol"))
        merged = {
            "min_rr": current.min_rr,
            "max_rr": current.max_rr,
            "trailing_enabled": current.trailing_enabled,
            "trailing_activation_r": current.trailing_activation_r,
            "trailing_distance_r": current.trailing_distance_r,
            "trailing_method": current.trailing_method,
            "trailing_step_r": current.trailing_step_r,
            "auto_exit_on_opposite_signal": current.auto_exit_on_opposite_signal,
        }
        merged.update(values)
        symbol = str(body.get("symbol") or "").strip()
        if symbol:
            manager.set_instrument(symbol, merged)
        elif body.get("scope", "global") == "global":
            manager.set_global(merged)
        else:
            raise ValueError("symbol is required for instrument scope")
        return manager.snapshot()

    def risk_policy_reset(body):
        if not isinstance(body, dict):
            raise ValueError("expected JSON body")
        symbol = str(body.get("symbol") or "").strip()
        if not symbol:
            raise ValueError("symbol is required to reset an instrument override")
        trading_policy_manager().reset_instrument(symbol)
        return trading_policy_manager().snapshot()

    routes = {}

    for path, handler in reads.items():

        routes[("GET", path)] = handler

    routes[("POST", "/control")] = control_handler
    routes[("GET", "/risk-policy")] = risk_policy_get
    routes[("POST", "/risk-policy")] = risk_policy_set
    routes[("POST", "/risk-policy/reset")] = risk_policy_reset

    return routes


# =====================================================
# HTTP handler
# =====================================================


class _ApiHandler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"

    routes = {}

    token = ""

    body_limit = 65536

    def _send(self, status, payload):
        """Write a response. PAYLOAD is JSON-safe, except the
        preview-dashboard envelope {"__html__": str}, which is
        served as text/html so the browser renders it."""

        if (isinstance(payload, dict) and set(payload) == {"__html__"}
                and isinstance(payload["__html__"], str)):
            data = payload["__html__"].encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type",
                             "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(data)
            except Exception:
                pass
            return

        data = json.dumps(payload, default=_json_safe).encode("utf-8")

        self.send_response(status)

        self.send_header("Content-Type", "application/json")

        self.send_header("Content-Length", str(len(data)))

        self.send_header("Connection", "close")

        self.end_headers()

        try:

            self.wfile.write(data)

        except Exception:

            pass

    def _unauthorized(self):

        self._send(
            401,
            {"error": "unauthorized", "detail": "valid bearer token required"},
        )

    def _read_body(self):
        """Read up to body_limit bytes of a request body."""

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

            return {}

    def _authorized(self):
        """Constant-time bearer-token check. When no token is
        configured the service refuses all requests (fail closed)."""

        if not self.token:

            return False

        header = self.headers.get("Authorization", "") or ""

        parts = header.split(" ", 1)

        if len(parts) != 2 or parts[0].lower() != "bearer":

            return False

        return _tokens_equal(parts[1].strip(), self.token)

    def _dispatch(self, method):
        """Route one request. Read-only GETs delegate to the read
        mappers; POST /control enforces PAPER-only allowlist.
        Bearer authorization applies to every route except the
        static-shell PUBLIC_GET_PATHS (currently only the
        data-free dashboard shell)."""

        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if not (method == "GET" and path in PUBLIC_GET_PATHS):
            if not self._authorized():
                self._unauthorized()
                return

        key = (method, path)

        if key not in self.routes:

            self._send(404, {"error": "not_found", "path": path})

            return

        handler = self.routes[key]

        try:

            if method == "POST":

                body = self._read_body()

                payload = handler(body)

            else:

                payload = handler()

            self._send(200, payload)

        except ControlCommandError as exc:

            self._send(400, {"error": "control_rejected",
                             "detail": _safe_detail(exc)})

        except ValueError as exc:

            self._send(400, {"error": "bad_request", "detail": _safe_detail(exc)})

        except Exception as exc:

            self._send(
                500,
                {
                    "error": "internal_error",
                    "path": path,
                    "detail": _safe_detail(exc),
                },
            )

    def do_GET(self):

        self._dispatch("GET")

    def do_POST(self):

        self._dispatch("POST")

    def log_message(self, *args, **kwargs):
        """Silence default stderr request logging."""

        pass


# =====================================================
# Server
# =====================================================


class ControlApiServer:

    """Thin stdlib HTTP service around an engine + lifecycle.

    Binds to 127.0.0.1 only. Serves on a daemon thread. Provides
    serve_forever_threaded() and shutdown() so the process can be
    torn down cleanly from main.py.
    """

    def __init__(
        self,
        engine,
        lifecycle,
        token="",
        host="127.0.0.1",
        port=8787,
        extra_routes=None,
    ):

        self.engine = engine

        self.lifecycle = lifecycle

        self.token = token or ""

        self.host = "127.0.0.1"  # localhost binding is enforced

        self.port = int(port)

        self.routes = _build_routes(engine, lifecycle)

        # Preview/extension seam (additive): extra read-only routes
        # merged BEFORE construct() binds them to the handler. Keys
        # are (method, path) tuples like the built-ins. Callers must
        # only add GET routes (dashboard/static/read snapshots);
        # mutation stays behind the existing POST /control
        # PAPER-only allowlist, which this seam never touches.
        for key, handler in dict(extra_routes or {}).items():
            self.routes[key] = handler

        self._httpd = None

        self._thread = None

    @classmethod
    def from_settings(cls, engine, lifecycle, extra_routes=None):
        """Build from config.settings; raises if the API is enabled
        without a token (fail closed)."""

        from config.settings import settings

        token = getattr(settings, "CONTROL_API_TOKEN", "") or ""

        port = int(getattr(settings, "CONTROL_API_PORT", 8787) or 8787)

        return cls(engine, lifecycle, token=token, port=port,
                   extra_routes=extra_routes)

    def construct(self):
        """Create the (un-started) ThreadingHTTPServer."""

        handler = type("_BoundApiHandler", (_ApiHandler,), {})
        handler.routes = self.routes
        handler.token = self.token

        self._httpd = ThreadingHTTPServer(
            (self.host, self.port), handler
        )

        return self._httpd

    def serve_forever_threaded(self):
        """Start serving on a daemon thread (non-blocking)."""

        if self._httpd is None:

            self.construct()

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="quantengine-monitoring",
            daemon=True,
        )

        self._thread.start()

    def running(self):

        return self._thread is not None and self._thread.is_alive()

    @property
    def addr(self):

        if self._httpd is None:

            return None

        return self._httpd.server_address

    def shutdown(self):
        """Stop the http server + join its thread."""

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
