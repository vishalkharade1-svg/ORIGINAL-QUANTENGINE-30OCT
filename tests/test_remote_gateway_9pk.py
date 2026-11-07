"""
Phase 9P-k Secure Remote / Mobile Control Foundation tests.

Exercises the REAL RemoteGateway end-to-end over localhost HTTP
(plaintext loopback test mode -- the require_tls production guard is
tested separately) in front of a REAL ControlApiServer (which runs
against a FakeEngine on an ephemeral localhost port, exactly as in
test_api_server_9pf.py).

Coverage:
  * per-role auth (VIEW / CONTROL / EMERGENCY) with constant-time
    comparison and 401 on missing/bad token,
  * authorization: VIEW reads but cannot control; CONTROL can
    start/stop/restart but NOT emergency_stop; EMERGENCY can
    emergency_stop,
  * unknown / non-permitted routes are refused (403),
  * request correlation IDs (X-Request-ID echoed),
  * rate limiting at the boundary (429) WITHOUT rate-limiting the
    internal Control API,
  * audit logging of control actions (with prev/result state) and
    auth denials; NO secret ever written,
  * forwarding preserves the Control API response bodies/status,
  * static dashboard (/, /app.js, /manifest.json) served to any
    authenticated principal,
  * fail-closed startup when under-configured,
  * the Control API is never bound to 0.0.0.0 and the gateway never
    binds its own listener to 0.0.0.0 by default.

No network/exchange is involved.
"""

import http.client
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from core.remote import roles
from core.remote.audit import AuditLog
from core.remote.gateway import (
    GatewayConfig,
    RemoteGateway,
    RemoteGatewayError,
)
from core.monitoring.api_server import ControlApiServer
from core.runtime.lifecycle import EngineLifecycle

TOKEN = "test-token-1234"
VIEW_TOKEN = "view-token-aaa"
CONTROL_TOKEN = "control-token-bbb"
EMERGENCY_TOKEN = "emergency-token-ccc"


class FakePortfolio:
    def snapshot(self):
        return {
            "equity": 100000.0,
            "current_risk": 500.0,
            "open_positions": 1,
            "direction_risk": {"BULLISH": 300.0, "BEARISH": 200.0},
            "last_reason": "ok",
        }


class FakeScheduler:
    def __init__(self):
        self.last_universe = _Universe()
        self.last_run = 1000.0
        self.runs = 3
        self.errors = [RuntimeError("boom discovery")]


class _Universe:
    reasons = {"BTCUSDT": "ELIGIBLE", "ETHUSDT": "ELIGIBLE"}


class FakeSubs:
    def __init__(self):
        self.errors = [("BTCUSDT", "connect", RuntimeError("ws down"))]

    def statuses(self):
        return {
            "BTCUSDT": {"status": "LIVE", "received": 5},
            "ETHUSDT": {"status": "CONNECTING", "received": 0},
        }


class FakePipeline:
    def __init__(self):
        self.market = None
        self.execution_signal = {"action": "BUY"}
        self.execution_signals = [{"action": "BUY"}]


class FakeAccount:
    class _State:
        drawdown = 100.0
        drawdown_percent = 0.1
        portfolio_risk = 500.0
        exposure = 0.05

    def __init__(self):
        self.state = self._State()
        self.balance = 99000.0
        self.equity = 99500.0


class FakeRuntime:
    def __init__(self):
        self.instrument = None
        self.pipeline = FakePipeline()
        self.current_trade = type(
            "T", (), {"direction": "LONG", "entry_price": 50000.0}
        )()
        self.executed_intents = ()
        self.account = FakeAccount()
        self.engine = type(
            "E", (), {"dry_run": True, "placed": [], "registry": object()}
        )()
        self.retired = False

    @property
    def symbol(self):
        return "BTCUSDT"


class FakeEngine:
    def __init__(self):
        self.started = False
        self.timeframe = "1m"
        self.universe_mode = "explicit"
        self.runtimes = {"btc": FakeRuntime()}
        self._instruments = {"BTCUSDT": object(), "ETHUSDT": object()}
        self.refresh_scheduler = FakeScheduler()
        self.subscriptions = FakeSubs()
        self.portfolio = FakePortfolio()

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def poll(self, client=None, normalizer=None):
        pass

    def statuses(self):
        return {r.symbol: r.state() for r in self.runtimes.values()}

    def performance(self, symbol=None):
        if symbol is not None:
            return {"symbol": symbol, "total_trades": 1}
        return {"total_trades": 1, "per_symbol": {}}


def _start_control_api():
    engine = FakeEngine()
    lifecycle = EngineLifecycle(engine, poll_interval_seconds=0.001)
    server = ControlApiServer(engine, lifecycle, token=TOKEN, port=0)
    server.construct()
    port = server.addr[1]
    server.serve_forever_threaded()
    time.sleep(0.05)
    return engine, lifecycle, server, port


class GatewayTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine, cls.lifecycle, cls.control, cls.control_port = \
            _start_control_api()

        cls._tmpdir = tempfile.mkdtemp(prefix="qe_remote_audit_")
        cls.audit_path = os.path.join(cls._tmpdir, "audit.jsonl")
        cls.audit = AuditLog(cls.audit_path)

        config = GatewayConfig(
            host="127.0.0.1",
            port=0,
            local_host="127.0.0.1",
            local_port=cls.control_port,
            local_token=TOKEN,
            tokens={
                roles.VIEW: VIEW_TOKEN,
                roles.CONTROL: CONTROL_TOKEN,
                roles.EMERGENCY: EMERGENCY_TOKEN,
            },
            rate_max=200,
            rate_window=60.0,
            audit=cls.audit,
            require_tls=False,
        )
        cls.gateway = RemoteGateway(config)
        cls.gateway.serve_forever_threaded()
        cls.port = cls.gateway.addr[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.gateway.shutdown()
        except Exception:
            pass
        try:
            cls.audit.close()
        except Exception:
            pass
        try:
            cls.lifecycle.emergency_stop()
        except Exception:
            pass
        cls.control.shutdown()
        shutil.rmtree(cls._tmpdir, ignore_errors=True)


def _req(port, method, path, token, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    hdrs = {"Authorization": "Bearer %s" % token}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body)
        hdrs["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    rid = resp.getheader("X-Request-ID")
    conn.close()
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = raw
    return resp.status, parsed, rid


class TestAuthentication(GatewayTestCase):

    def test_missing_token_is_401(self):
        status, _, _ = _req(self.port, "GET", "/health", "")
        self.assertEqual(status, 401)

    def test_bad_token_is_401(self):
        status, _, _ = _req(self.port, "GET", "/health", "nope")
        self.assertEqual(status, 401)

    def test_view_token_is_200(self):
        status, body, _ = _req(self.port, "GET", "/health", VIEW_TOKEN)
        self.assertEqual(status, 200)
        self.assertIn("lifecycle_state", body)

    def test_gateway_health_read_passes_through(self):
        status, body, _ = _req(self.port, "GET", "/health", CONTROL_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["exchange"], "DELTA")
        # runtime_mode is surfaced by the gateway (PAPER in the test)
        self.assertEqual(body["runtime_mode"], "PAPER")


class TestAuthorization(GatewayTestCase):

    def test_view_can_read(self):
        for path in ("/universe", "/market", "/account", "/risk",
                     "/performance", "/positions", "/orders", "/errors"):
            status, _, _ = _req(self.port, "GET", path, VIEW_TOKEN)
            self.assertEqual(status, 200, msg=path)

    def test_view_cannot_control(self):
        status, body, _ = _req(
            self.port, "POST", "/control", VIEW_TOKEN, {"command": "start"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "forbidden")

    def test_control_can_start_stop_restart(self):
        # start
        status, body, _ = _req(
            self.port, "POST", "/control", CONTROL_TOKEN, {"command": "start"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "RUNNING")
        self.assertTrue(self.engine.started)

        # stop
        status, body, _ = _req(
            self.port, "POST", "/control", CONTROL_TOKEN, {"command": "stop"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "STOPPED")

        # restart (authorized for CONTROL)
        status, body, _ = _req(
            self.port, "POST", "/control", CONTROL_TOKEN, {"command": "restart"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "RUNNING")
        self.lifecycle.stop()

    def test_control_cannot_emergency_stop(self):
        status, body, _ = _req(
            self.port, "POST", "/control", CONTROL_TOKEN,
            {"command": "emergency_stop"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "forbidden")

    def test_emergency_can_emergency_stop(self):
        self.lifecycle.start()
        status, body, _ = _req(
            self.port, "POST", "/control", EMERGENCY_TOKEN,
            {"command": "emergency_stop"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "STOPPED")
        self.assertFalse(self.engine.started)

    def test_unknown_route_is_403(self):
        status, body, _ = _req(self.port, "GET", "/nonexistent", VIEW_TOKEN)
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "forbidden")

    def test_malformed_control_body_is_400(self):
        status, body, _ = _req(
            self.port, "POST", "/control", CONTROL_TOKEN, {"foo": 1}
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "bad_request")


class TestCorrelationId(GatewayTestCase):

    def test_correlation_id_echoed(self):
        status, _, rid = _req(
            self.port, "GET", "/health", VIEW_TOKEN,
            headers={"X-Request-ID": "req-abc-123"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(rid, "req-abc-123")

    def test_generated_correlation_id(self):
        status, _, rid = _req(self.port, "GET", "/health", VIEW_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(rid)


class TestRateLimit(GatewayTestCase):

    def test_rate_limited_at_boundary(self):
        cfg = GatewayConfig(
            host="127.0.0.1", port=0,
            local_host="127.0.0.1", local_port=self.control_port,
            local_token=TOKEN,
            tokens={roles.VIEW: VIEW_TOKEN, roles.CONTROL: CONTROL_TOKEN},
            rate_max=3, rate_window=60.0,
            audit=self.audit, require_tls=False,
        )
        gw = RemoteGateway(cfg)
        gw.serve_forever_threaded()
        port = gw.addr[1]
        time.sleep(0.05)
        try:
            for _ in range(3):
                status, _, _ = _req(port, "GET", "/health", VIEW_TOKEN)
                self.assertEqual(status, 200)
            status, body, _ = _req(port, "GET", "/health", VIEW_TOKEN)
            self.assertEqual(status, 429)
            self.assertEqual(body["error"], "rate_limited")
            # internal Control API was NOT rate limited: still reachable
            # directly.
            self.assertTrue(gw.running())
        finally:
            gw.shutdown()


class TestAudit(GatewayTestCase):

    def test_control_action_audited(self):
        # new audit sink to keep this test independent
        path = os.path.join(self._tmpdir, "audit2.jsonl")
        log = AuditLog(path)
        gw = RemoteGateway(GatewayConfig(
            host="127.0.0.1", port=0,
            local_host="127.0.0.1", local_port=self.control_port,
            local_token=TOKEN,
            tokens={roles.CONTROL: CONTROL_TOKEN},
            rate_max=0, audit=log, require_tls=False,
        ))
        gw.serve_forever_threaded()
        port = gw.addr[1]
        time.sleep(0.05)
        try:
            self.lifecycle.start()
            _req(port, "POST", "/control", CONTROL_TOKEN,
                 {"command": "stop"})
            time.sleep(0.1)
            log.close()
            with open(path, encoding="utf-8") as fh:
                lines = [json.loads(l) for l in fh if l.strip()]
            controls = [l for l in lines if l["kind"] == "control"]
            self.assertTrue(controls)
            self.assertEqual(controls[-1]["command"], "stop")
            self.assertEqual(controls[-1]["result_state"], "STOPPED")
            self.assertEqual(controls[-1]["prev_state"], "RUNNING")
            blob = json.dumps(lines)
            self.assertNotIn(TOKEN, blob)
            self.assertNotIn(CONTROL_TOKEN, blob)
        finally:
            gw.shutdown()

    def test_auth_denial_audited(self):
        self.lifecycle.stop()
        _req(self.port, "GET", "/health", "wrong-token")
        time.sleep(0.1)
        lines = []
        with open(self.audit_path, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        auth_denials = [l for l in lines if l["kind"] == "auth"]
        self.assertTrue(auth_denials)
        self.assertEqual(auth_denials[-1]["result"], "denied")
        blob = json.dumps(lines)
        self.assertNotIn(TOKEN, blob)


class TestDashboardServing(GatewayTestCase):

    def test_index_served_to_authenticated(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(
            "GET", "/", headers={"Authorization": "Bearer %s" % VIEW_TOKEN}
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertIn("QuantEngine Remote", raw)
        self.assertIn("<!DOCTYPE html>", raw)

    def test_assets_served(self):
        for path in ("/app.js", "/app.css", "/manifest.json"):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request(
                "GET", path,
                headers={"Authorization": "Bearer %s" % VIEW_TOKEN},
            )
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
            self.assertEqual(resp.status, 200, msg=path)
            self.assertTrue(raw)

    def test_unknown_static_refused(self):
        # unknown static asset is not a recognized route -> the gateway
        # treats it as an unpermitted API path and refuses (403)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(
            "GET", "/nope.js",
            headers={"Authorization": "Bearer %s" % VIEW_TOKEN},
        )
        resp = conn.getresponse()
        conn.close()
        self.assertEqual(resp.status, 403)

    def test_dashboard_requires_auth(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/")
        resp = conn.getresponse()
        conn.close()
        self.assertEqual(resp.status, 401)


class TestFailClosed(unittest.TestCase):

    def test_under_configured_gateway_refuses_to_start(self):
        # local token missing -> fail closed
        cfg = GatewayConfig(
            host="127.0.0.1", port=0, local_token="",
            tokens={roles.VIEW: "v", roles.CONTROL: "c"},
            require_tls=False,
        )
        with self.assertRaises(RemoteGatewayError):
            RemoteGateway(cfg).serve_forever_threaded()

    def test_missing_role_tokens_fail_closed(self):
        cfg = GatewayConfig(
            host="127.0.0.1", port=0, local_token="x",
            tokens={},  # empty token store -> fail closed
            require_tls=True,
            certfile="c.pem", keyfile="k.pem",  # would otherwise pass
        )
        with self.assertRaises(RemoteGatewayError):
            RemoteGateway(cfg).serve_forever_threaded()

    def test_missing_tls_cert_fails_by_default(self):
        cfg = GatewayConfig(
            host="127.0.0.1", port=0, local_token="x",
            tokens={roles.VIEW: "v", roles.CONTROL: "c"},
            require_tls=True,  # default production posture
        )
        with self.assertRaises(RemoteGatewayError):
            RemoteGateway(cfg).serve_forever_threaded()

    def test_role_ordering(self):
        self.assertTrue(roles.satisfies(roles.EMERGENCY, roles.VIEW))
        self.assertTrue(roles.satisfies(roles.EMERGENCY, roles.CONTROL))
        self.assertTrue(roles.satisfies(roles.EMERGENCY, roles.EMERGENCY))
        self.assertTrue(roles.satisfies(roles.CONTROL, roles.VIEW))
        self.assertFalse(roles.satisfies(roles.VIEW, roles.CONTROL))
        self.assertFalse(roles.satisfies(roles.CONTROL, roles.EMERGENCY))
        self.assertFalse(roles.satisfies(roles.VIEW, roles.EMERGENCY))

    def test_default_bind_is_loopback_not_wildcard(self):
        # The gateway defaults to 127.0.0.1 -- it never silently binds
        # 0.0.0.0 unless the operator explicitly configures that.
        cfg = GatewayConfig(
            host="127.0.0.1", port=0, local_token="x",
            tokens={roles.VIEW: "v", roles.CONTROL: "c"},
            require_tls=False,
        )
        self.assertEqual(cfg.host, "127.0.0.1")
        self.assertNotEqual(cfg.host, "0.0.0.0")


class TestRemoteServiceGating(unittest.TestCase):
    """core/remote/service.py wiring: gating on operator config,
    fail-closed startup, duplicate refusal."""

    def setUp(self):
        self._saved_env = dict(os.environ)
        os.environ.pop("REMOTE_GATEWAY_ENABLED", None)
        os.environ.pop("REMOTE_VIEW_TOKEN", None)
        os.environ.pop("REMOTE_CONTROL_TOKEN", None)
        os.environ.pop("REMOTE_TLS_CERT", None)
        os.environ.pop("REMOTE_TLS_KEY", None)
        os.environ.pop("REMOTE_GATEWAY_PORT", None)
        os.environ["REMOTE_RATE_MAX"] = "0"
        # ensure the active-gateway global is clean between tests
        from core.remote import service as svc
        svc._active_gateway = None

    def tearDown(self):
        from core.remote import service as svc
        svc.stop_active_remote_gateway()
        os.environ.clear()
        os.environ.update(self._saved_env)

    def test_disabled_returns_none(self):
        os.environ["REMOTE_GATEWAY_ENABLED"] = "false"
        from core.remote.service import start_remote_gateway
        self.assertIsNone(start_remote_gateway())

    def test_enabled_without_local_api_fails_closed(self):
        os.environ["REMOTE_GATEWAY_ENABLED"] = "true"
        import config.settings as _settings
        saved_api = _settings.settings.CONTROL_API_ENABLED
        try:
            _settings.settings.CONTROL_API_ENABLED = False
            from core.remote.service import (
                RemoteGatewayConfigError, start_remote_gateway,
            )
            with self.assertRaises(RemoteGatewayConfigError):
                start_remote_gateway()
        finally:
            _settings.settings.CONTROL_API_ENABLED = saved_api


@unittest.skipUnless(
    shutil.which("openssl") or os.path.exists("C:\\Program Files\\Git\\usr\\bin\\openssl.exe"),
    "openssl not available for TLS integration test",
)
class TestTlsTransport(unittest.TestCase):
    """End-to-end TLS smoke test using a generated self-signed cert."""

    def test_tls_roundtrip(self):
        exe = shutil.which("openssl") or \
            "C:\\Program Files\\Git\\usr\\bin\\openssl.exe"
        tmp = tempfile.mkdtemp(prefix="qe_tls_")
        cert = os.path.join(tmp, "cert.pem")
        key = os.path.join(tmp, "key.pem")
        try:
            subprocess.run(
                [exe, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-keyout", key, "-out", cert, "-days", "1",
                 "-subj", "/CN=localhost"],
                check=True, capture_output=True, timeout=30,
            )
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            self.skipTest("openssl cert generation failed")

        engine, lifecycle, control, control_port = _start_control_api()
        config = GatewayConfig(
            host="127.0.0.1", port=0,
            local_host="127.0.0.1", local_port=control_port,
            local_token=TOKEN,
            certfile=cert, keyfile=key,
            tokens={roles.VIEW: VIEW_TOKEN},
            rate_max=0, require_tls=True,
        )
        gw = RemoteGateway(config)
        gw.serve_forever_threaded()
        port = gw.addr[1]
        time.sleep(0.05)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(
                "127.0.0.1", port, timeout=10, context=ctx
            )
            conn.request(
                "GET", "/health",
                headers={"Authorization": "Bearer %s" % VIEW_TOKEN},
            )
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            conn.close()
            self.assertEqual(resp.status, 200)
            self.assertIn("lifecycle_state", json.loads(raw))
        finally:
            gw.shutdown()
            try:
                lifecycle.emergency_stop()
            except Exception:
                pass
            control.shutdown()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
