"""
Phase 9P-h desktop control client tests.

Offline / no network: an in-process fake Control API server
(http.server on 127.0.0.1 ephemeral port) stands in for the real
9P-f API. These tests exercise the HTTP client, configuration,
background poller, control path, and controller presentation --
all display-free (no tkinter window is constructed).

The client is verified to talk HTTP only: assertions confirm the
bearer header, the exact GET paths, and the POST /control body
contract {"command": ...}. No engine internals are imported.
"""

import http.client
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.client.config import ClientConfig
from core.client.controller import (
    ControlPath,
    render_dashboard,
    render_errors,
    render_market,
    render_performance,
    render_positions,
    render_signals,
    render_universe,
)
from core.client.http_client import (
    ApiClient,
    AuthenticationError,
    BadResponseError,
    ClientError,
    ControlRejectedError,
    ReconnectingClient,
    ServerError,
    TimeoutErrorWithCause,
)
from core.client.poller import CycleResult, Poller

TOKEN = "s3cret-token"


class FakeControlServer:
    """In-process Control API stand-in.

    Behavior knobs (set on the shared handler before requests):
      token_required   bool   -> 401 when the bearer token mismatches
      status_payload   dict   -> returned for every GET
      post_result      dict   -> returned for POST /control
      bad_json         bool   -> serve non-JSON on 200
      delay_seconds    float  -> sleep before responding (timeout tests)
      server_error     bool   -> respond 500
    """

    def __init__(self, token=TOKEN):
        self.requests = []  # (method, path, body, auth_header)
        self.token = token
        self.token_required = True
        self.status_payload = {
            "lifecycle_state": "RUNNING",
            "started": True,
            "exchange": "DELTA",
            "timeframe": "1m",
            "runtimes": 2,
            "uptime": 42.0,
        }
        self.post_result = {"command": "stop", "lifecycle_state": "STOPPED"}
        self.bad_json = False
        self.delay_seconds = 0.0
        self.server_error = False

        handler = self._make_handler_class()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._thread.start()

    def _make_handler_class(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _authorized(self):
                if not owner.token_required:
                    return True
                auth = self.headers.get("Authorization", "") or ""
                parts = auth.split(" ", 1)
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    return False
                return parts[1].strip() == owner.token

            def _send(self, status, payload, raw=None):
                if owner.delay_seconds:
                    time.sleep(owner.delay_seconds)
                if raw is not None:
                    data = raw.encode("utf-8")
                else:
                    data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except Exception:
                    pass

            def _record(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = {}
                if length > 0:
                    try:
                        body = json.loads(self.rfile.read(length).decode())
                    except Exception:
                        body = {}
                owner.requests.append(
                    (
                        self.command,
                        self.path,
                        body,
                        self.headers.get("Authorization", ""),
                    )
                )
                return body

            def do_GET(self):
                self._record()
                if not self._authorized():
                    self._send(401, {"error": "unauthorized"})
                    return
                if owner.server_error:
                    self._send(500, {"error": "internal_error"})
                    return
                if owner.bad_json:
                    self._send(200, None, raw="this is not json")
                    return
                self._send(200, owner.status_payload)

            def do_POST(self):
                body = self._record()
                if not self._authorized():
                    self._send(401, {"error": "unauthorized"})
                    return
                self._send(200, owner.post_result)

            def log_message(self, *args, **kwargs):
                pass

        return Handler

    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=3.0)


class HttpClientTestCase(unittest.TestCase):

    def setUp(self):
        self.server = FakeControlServer()
        self.addCleanup(self.server.close)
        self.client = ApiClient(
            host="127.0.0.1", port=self.server.port, token=TOKEN
        )

    def test_get_success_decodes_json(self):
        body = self.client.get("/health")
        self.assertEqual(body["lifecycle_state"], "RUNNING")

    def test_bearer_header_sent(self):
        self.client.get("/health")
        method, path, _body, auth = self.server.requests[-1]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/health")
        self.assertEqual(auth, "Bearer %s" % TOKEN)

    def test_post_control_sends_command_body(self):
        result = self.client.post("/control", {"command": "stop"})
        self.assertEqual(result["lifecycle_state"], "STOPPED")
        method, path, body, _auth = self.server.requests[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/control")
        self.assertEqual(body, {"command": "stop"})

    def test_missing_token_is_401(self):
        bad = ApiClient(
            host="127.0.0.1", port=self.server.port, token="wrong"
        )
        with self.assertRaises(AuthenticationError):
            bad.get("/health")

    def test_server_error_raises_server_error(self):
        self.server.server_error = True
        with self.assertRaises(ServerError):
            self.client.get("/health")

    def test_malformed_json_raises_bad_response(self):
        self.server.bad_json = True
        with self.assertRaises(BadResponseError):
            self.client.get("/health")

    def test_timeout_raises_timeout_error(self):
        self.server.delay_seconds = 1.5
        slow = ApiClient(
            host="127.0.0.1", port=self.server.port, token=TOKEN, timeout=0.2
        )
        with self.assertRaises(TimeoutErrorWithCause):
            slow.get("/health")

    def test_unreachable_host_raises_client_error(self):
        # Reaching a non-listening host may raise ConnectionErrorWithCause
        # (connection refused) or TimeoutErrorWithCause (firewall drop)
        # depending on the host OS; both are correct "cannot reach"
        # semantics and must surface as an ApiClientError, never a crash.
        closed = ApiClient(
            host="127.0.0.1", port=9, token=TOKEN, timeout=0.5
        )
        with self.assertRaises(ClientError):
            closed.get("/health")


class ControlRejectedTestCase(unittest.TestCase):

    def test_400_control_rejected_classified(self):
        class _Slow:
            pass

        server = FakeControlServer()
        self.addCleanup(server.close)

        # simulate a 400 control_rejected: wrap the handler via a custom
        # client against a dedicated that returns 400
        from core.client.http_client import _classify

        exc = _classify(400, {"error": "control_rejected", "detail": "nope"})
        self.assertIsInstance(exc, ControlRejectedError)


class ReconnectingClientTestCase(unittest.TestCase):

    def test_probe_connected(self):
        server = FakeControlServer()
        self.addCleanup(server.close)
        api = ApiClient(host="127.0.0.1", port=server.port, token=TOKEN)
        rc = ReconnectingClient(api)
        self.assertTrue(rc.probe())
        self.assertTrue(rc.healthy())

    def test_probe_disconnected(self):
        api = ApiClient(host="127.0.0.1", port=9, token=TOKEN, timeout=0.3)
        rc = ReconnectingClient(api)
        self.assertFalse(rc.probe())
        self.assertFalse(rc.healthy())
        self.assertIsInstance(rc.conn_error, ClientError)


class ConfigTestCase(unittest.TestCase):

    def test_defaults(self):
        cfg = ClientConfig()
        self.assertEqual(cfg.host, "127.0.0.1")
        self.assertEqual(cfg.port, 8787)
        self.assertFalse(cfg.token)
        self.assertGreater(cfg.poll_interval, 0)

    def test_custom_values(self):
        cfg = ClientConfig(host="localhost", port=9000, token="x", poll_interval=7)
        self.assertEqual(cfg.host, "localhost")
        self.assertEqual(cfg.port, 9000)
        self.assertEqual(cfg.token, "x")
        self.assertEqual(cfg.poll_interval, 7)

    def test_from_env_token_and_host(self):
        cfg = ClientConfig.from_env(
            env={
                "QENGINE_CLIENT_HOST": "192.168.1.5",
                "QENGINE_CLIENT_PORT": "8123",
                "QENGINE_CLIENT_POLL": "5",
                "QENGINE_CLIENT_TOKEN": "env-tok",
            }
        )
        self.assertEqual(cfg.host, "192.168.1.5")
        self.assertEqual(cfg.port, 8123)
        self.assertEqual(cfg.poll_interval, 5)
        self.assertEqual(cfg.token, "env-tok")

    def test_as_dict_never_exposes_token(self):
        cfg = ClientConfig(token="secret")
        d = cfg.as_dict()
        self.assertNotIn("token", d)
        self.assertEqual(d["token_configured"], True)


class PollerTestCase(unittest.TestCase):

    def _make_api(self):
        server = FakeControlServer()
        self.addCleanup(server.close)
        api = ApiClient(host="127.0.0.1", port=server.port, token=TOKEN)
        return api

    def test_results_reach_queue(self):
        api = self._make_api()
        poller = Poller(api, interval=0.05)
        poller.start()
        try:
            result = poller.queue.get(timeout=5.0)
        finally:
            poller.stop()
            poller.join(timeout=5.0)
        self.assertIsInstance(result, CycleResult)
        self.assertTrue(result.connected)
        self.assertIsNotNone(result.data("health"))

    def test_connection_failure_does_not_crash_and_records_error(self):
        api = ApiClient(host="127.0.0.1", port=9, token=TOKEN, timeout=0.3)
        poller = Poller(api, interval=0.05)
        poller.start()
        try:
            result = poller.queue.get(timeout=5.0)
        finally:
            poller.stop()
            poller.join(timeout=5.0)
        self.assertFalse(result.connected)
        self.assertIsNotNone(result.error("health"))
        # individual endpoint errors are recorded, not fatal
        self.assertIsNotNone(result.error("universe"))

    def test_stop_is_clean(self):
        api = self._make_api()
        poller = Poller(api, interval=0.05)
        poller.start()
        self.assertTrue(poller.running())
        poller.stop()
        poller.join(timeout=5.0)
        self.assertFalse(poller.running())


class ControlPathTestCase(unittest.TestCase):

    def test_control_path_sends_verbs_to_correct_endpoint(self):
        server = FakeControlServer()
        self.addCleanup(server.close)

        class RecordingApi:
            def __init__(self):
                self.sent = []

            def post(self, path, payload):
                self.sent.append((path, payload))
                # mirror the fake server's recorded response
                return {"command": payload["command"],
                        "lifecycle_state": "OK"}

        api = RecordingApi()
        cp = ControlPath(api)
        cp.start()
        cp.stop()
        cp.restart()
        cp.emergency_stop()

        verbs = [p["command"] for _, p in api.sent]
        self.assertEqual(
            verbs, ["start", "stop", "restart", "emergency_stop"]
        )
        for path, _ in api.sent:
            self.assertEqual(path, "/control")


class ControllerRenderTestCase(unittest.TestCase):

    def _cycle(self, endpoints):
        return CycleResult(endpoints=endpoints, connected=True, at=1000.0)

    def test_dashboard_renders_authoritative_fields(self):
        cycle = self._cycle(
            {
                "health": {
                    "ok": True,
                    "data": {
                        "lifecycle_state": "RUNNING",
                        "exchange": "DELTA",
                        "runtimes": 2,
                    },
                    "error": None,
                },
                "universe": {"ok": True, "data": {"eligible_count": 3}, "error": None},
                "runtimes": {"ok": True, "data": {"a": {}, "b": {}}, "error": None},
                "errors": {"ok": True, "data": {"errors": []}, "error": None},
            }
        )
        rows = render_dashboard(cycle)
        self.assertEqual(rows[0], ("Lifecycle", "RUNNING"))
        self.assertEqual(rows[1], ("Engine started", "Unavailable"))

    def test_universe_returns_symbols(self):
        cycle = self._cycle(
            {
                "universe": {
                    "ok": True,
                    "data": {"eligible_symbols": ["BTCUSDT", "ETHUSDT"]},
                    "error": None,
                }
            }
        )
        _headers, symbols = render_universe(cycle)
        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_empty_universe_is_empty_result(self):
        # an empty eligible list is a VALID server result, not an error
        cycle = self._cycle(
            {
                "universe": {
                    "ok": True,
                    "data": {"eligible_symbols": []},
                    "error": None,
                }
            }
        )
        headers, symbols = render_universe(cycle)
        self.assertEqual(symbols, [])
        self.assertEqual((headers, symbols), ([], []))

    def test_performance_uses_server_report_fields(self):
        cycle = self._cycle(
            {
                "performance": {
                    "ok": True,
                    "data": {
                        "aggregate": {
                            "profit_factor": 1.8,
                            "net_pnl": 100.0,
                        }
                    },
                    "error": None,
                }
            }
        )
        rows, _ = render_performance(cycle)
        mapping = dict(rows)
        self.assertEqual(mapping["Profit Factor"], "1.8")
        self.assertEqual(mapping["Net Pnl"], "100.0")

    def test_positions_display_only_supplied_fields(self):
        cycle = self._cycle(
            {
                "positions": {
                    "ok": True,
                    "data": {
                        "BTCUSDT": {
                            "current_trade": {
                                "side": "BUY",
                                "quantity": 0.5,
                                "entry_price": 65000,
                            }
                        }
                    },
                    "error": None,
                }
            }
        )
        _headers, rows = render_positions(cycle)
        self.assertEqual(rows[0][0], "BTCUSDT")
        self.assertEqual(rows[0][1], "BUY")

    def test_error_endpoint_renders_readably_without_secrets(self):
        cycle = self._cycle(
            {
                "errors": {
                    "ok": True,
                    "data": {
                        "errors": [
                            {
                                "source": "refresh_scheduler",
                                "error": "network down",
                            }
                        ]
                    },
                    "error": None,
                }
            }
        )
        _headers, rows = render_errors(cycle)
        combined = " ".join(rows)
        self.assertIn("refresh_scheduler", combined)
        self.assertNotIn(TOKEN, combined)


if __name__ == "__main__":
    unittest.main()
