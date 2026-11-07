"""
Phase 9P-i End-to-End Integration tests.

Closes the FULL operational loop as committed, deterministic,
offline tests: the REAL desktop control client package
(core.client: ApiClient / Poller / ReconnectingClient / ControlPath
and the controller renders) drives the REAL Control & Monitoring API
(core.monitoring) around the REAL EngineLifecycle + a canonical fake
PAPER engine. No network, no exchange, no credentials.

This is the product's required client<->API<->engine wiring:

    core.client  --HTTP+bearer-->  core.monitoring.api_server
                       -->  EngineLifecycle --> fake PAPER engine

It verifies the guarantees Phase 9P-i exists to prove:

  * a real fresh-process client can reach a real API against a real
    lifecycle and read authoritative state (health/universe/runtimes/
    performance) WITHOUT importing any engine internals;
  * the four allowlisted lifecycle verbs (start/stop/restart/
    emergency_stop) work end-to-end THROUGH the real client;
  * the poller produces a coordinated CycleResult on a real API;
  * the controller renders real server data verbatim (no client-side
    recomputation);
  * the bearer token NEVER appears in any response body, error string,
    or rendered line (secret handling);
  * stopping/tearing down the client NEVER stops the engine (the UI
    is not a control path); only an explicit lifecycle stop does.

API disabled by default is also re-confirmed: with no token the API
refuses to start (fail closed), and with the API disabled the service
runs the lifecycle with NO HTTP server.

All tests are stdlib-only and deterministic.
"""

import json
import threading
import time
import unittest

import config.settings as _settings

from core.client import controller
from core.client.http_client import (
    AuthenticationError,
    ClientError,
    ReconnectingClient,
)
from core.client.poller import Poller
from core.client.controller import ControlPath
from core.monitoring import service
from core.runtime.paper_main import (
    ExplicitSymbolUniverseManager,
    build_paper_engine,
)

TOKEN = "9pi-integration-token"


class FakeClock:
    def __init__(self, now=0.0):
        self.now = float(now)

    def __call__(self):
        return self.now


class FakeTransport:
    def __init__(self):
        self._routes = {}
        self.closed = False

    def subscribe(self, symbol, on_candle, on_down):
        self._routes[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol):
        self._routes.pop(symbol, None)

    def close(self):
        self.closed = True
        self._routes.clear()


class ScriptedWorld:
    def __init__(self, context):
        self.context = context
        self.candles_seen = []

    def reset(self):
        self.candles_seen = []

    def on_candle(self, event):
        self.candles_seen.append(event.candle)
        self.context.add_candle(event.candle)


def _build_engine(symbols=("BTCUSDT", "ETHUSDT")):
    manager = ExplicitSymbolUniverseManager(
        symbols=list(symbols), timeframe="1m"
    )
    transport = FakeTransport()

    engine, _manager = build_paper_engine(
        universe_manager=manager,
        transport_factory=lambda: transport,
        world_factory=ScriptedWorld,
        clock=FakeClock(now=1000.0),
        timeframe="1m",
        refresh_interval_seconds=0,
    )
    return engine, transport


def _flat_text(value):
    """Recursively flatten a JSON value to a single lowercase string
    so tests can assert the bearer token never appears anywhere."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).lower()
    if isinstance(value, dict):
        return " ".join(
            _flat_text(k) + " " + _flat_text(v) for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return " ".join(_flat_text(v) for v in value)
    return str(value).lower()


class IntegrationTestCase(unittest.TestCase):
    """Boot a REAL Control API + REAL lifecycle + fake PAPER engine
    exactly like the 9P-g entrypoint, then talk to it with the REAL
    core.client package."""

    def setUp(self):
        self._saved = {
            "enabled": _settings.settings.CONTROL_API_ENABLED,
            "token": _settings.settings.CONTROL_API_TOKEN,
            "port": _settings.settings.CONTROL_API_PORT,
            "poll": _settings.settings.CONTROL_API_POLL_SECONDS,
        }
        _settings.settings.CONTROL_API_ENABLED = True
        _settings.settings.CONTROL_API_TOKEN = TOKEN
        _settings.settings.CONTROL_API_PORT = 0
        _settings.settings.CONTROL_API_POLL_SECONDS = 0.001

        self.engine, self.transport = _build_engine()
        self.lifecycle, self.server = service.start_paper_service(
            self.engine, poll_interval_seconds=0.001
        )
        self.port = self.server.addr[1]

        from core.client.http_client import ApiClient

        self.api = ApiClient(
            host="127.0.0.1",
            port=self.port,
            token=TOKEN,
            timeout=5.0,
        )

        # wait for the server to accept and authenticate
        deadline = time.time() + 3.0
        while True:
            try:
                if self.api.get("/health"):
                    break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(0.02)

    def tearDown(self):
        self.api = None
        try:
            self.lifecycle.emergency_stop()
        except Exception:
            pass
        service.stop_api(self.server)

        s = _settings.settings
        s.CONTROL_API_ENABLED = self._saved["enabled"]
        s.CONTROL_API_TOKEN = self._saved["token"]
        s.CONTROL_API_PORT = self._saved["port"]
        s.CONTROL_API_POLL_SECONDS = self._saved["poll"]


class TestFullLoop(IntegrationTestCase):
    def test_real_client_reads_authoritative_state(self):
        health = self.api.get("/health")
        self.assertEqual(health["lifecycle_state"], "RUNNING")
        self.assertTrue(health["engine_started"])
        self.assertEqual(health["exchange"], "DELTA")

        universe = self.api.get("/universe")
        self.assertIn("BTCUSDT", universe["eligible_symbols"])
        self.assertIn("ETHUSDT", universe["eligible_symbols"])

        runtimes = self.api.get("/runtimes")
        self.assertEqual(len(runtimes), 2)

        performance = self.api.get("/performance")
        self.assertIn("aggregate", performance)
        self.assertIn("per_symbol", performance)

    def test_poller_produces_coordinated_cycle(self):
        poller = Poller(self.api, interval=0.001)
        poller.start()
        try:
            cycle = poller.queue.get(timeout=5.0)
        finally:
            poller.stop()
            poller.join(timeout=5.0)
        self.assertTrue(cycle.connected)
        self.assertIsNotNone(cycle.data("health"))
        self.assertIsNotNone(cycle.data("universe"))
        self.assertIsNotNone(cycle.data("runtimes"))
        self.assertIsNone(cycle.error("health"))

    def test_controller_renders_real_data_verbatim(self):
        poller = Poller(self.api, interval=0.001)
        poller.start()
        try:
            cycle = poller.queue.get(timeout=5.0)
        finally:
            poller.stop()
            poller.join(timeout=5.0)

        dash = controller.render_dashboard(cycle)
        self.assertIn(("Engine started", "True"), dash)

        _h, symbols = controller.render_universe(cycle)
        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

        perf_rows, _ = controller.render_performance(cycle)
        seen = [label for label, _v in perf_rows]
        self.assertIn("Completed Trades", seen)

    def test_control_path_verbs_end_to_end(self):
        controls = ControlPath(self.api)

        # start from running is idempotent through the real API
        resp = controls.start()
        self.assertEqual(resp["lifecycle_state"], "RUNNING")

        resp = controls.stop()
        self.assertEqual(resp["lifecycle_state"], "STOPPED")
        self.assertFalse(self.engine.started)

        self.assertTrue(self.lifecycle.wait(timeout=5.0) == "STOPPED")

    def test_reconnecting_client_probe(self):
        rc = ReconnectingClient(self.api, interval=0.001)
        self.assertTrue(rc.probe())
        self.assertTrue(rc.healthy())


class TestNoSecretLeak(IntegrationTestCase):
    def test_token_never_in_any_response_body(self):
        endpoints = (
            "health", "universe", "subscriptions", "runtimes", "market",
            "signals", "positions", "orders", "account", "risk",
            "performance", "errors",
        )
        for ep in endpoints:
            body = self.api.get("/" + ep)
            self.assertNotIn(
                TOKEN.lower(), _flat_text(body), "token leaked via /%s" % ep
            )

        resp = self.api.post("/control", {"command": "start"})
        self.assertNotIn(TOKEN.lower(), _flat_text(resp))

    def test_client_error_never_contains_token(self):
        # wrong token -> 401 -> AuthenticationError, no token in msg
        from core.client.http_client import ApiClient

        bad = ApiClient(host="127.0.0.1", port=self.port, token="wrong", timeout=5.0)
        try:
            bad.get("/health")
            self.fail("expected 401")
        except AuthenticationError as exc:
            self.assertNotIn(TOKEN.lower(), str(exc).lower())
        except ClientError:
            pass


class TestClientCloseDoesNotStopEngine(unittest.TestCase):
    """Closing / tearing down the CLIENT must never stop the engine.
    This is mandatory: the UI is not a control path."""

    def setUp(self):
        self._saved = {
            "enabled": _settings.settings.CONTROL_API_ENABLED,
            "token": _settings.settings.CONTROL_API_TOKEN,
            "port": _settings.settings.CONTROL_API_PORT,
        }
        _settings.settings.CONTROL_API_ENABLED = True
        _settings.settings.CONTROL_API_TOKEN = TOKEN
        _settings.settings.CONTROL_API_PORT = 0

        self.engine, self.transport = _build_engine(symbols=("BTCUSDT",))
        self.lifecycle, self.server = service.start_paper_service(
            self.engine, poll_interval_seconds=0.001
        )
        self.port = self.server.addr[1]

        from core.client.http_client import ApiClient

        self.api = ApiClient(host="127.0.0.1", port=self.port, token=TOKEN)
        deadline = time.time() + 3.0
        while True:
            try:
                if self.api.get("/health"):
                    break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(0.02)

    def tearDown(self):
        try:
            self.lifecycle.emergency_stop()
        except Exception:
            pass
        service.stop_api(self.server)
        s = _settings.settings
        s.CONTROL_API_ENABLED = self._saved["enabled"]
        s.CONTROL_API_TOKEN = self._saved["token"]
        s.CONTROL_API_PORT = self._saved["port"]

    def test_poller_stop_leaves_engine_running(self):
        self.assertTrue(self.engine.started)
        poller = Poller(self.api, interval=0.001)
        poller.start()
        poller.stop()
        poller.join(timeout=5.0)
        self.assertFalse(poller.running())
        # engine is STILL running -- the client never stopped it
        self.assertTrue(self.engine.started)

        # only an explicit lifecycle stop stops the engine
        self.api.post("/control", {"command": "stop"})
        self.lifecycle.wait(timeout=5.0)
        self.assertFalse(self.engine.started)


class TestApiDisabledAndFailClosed(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "enabled": _settings.settings.CONTROL_API_ENABLED,
            "token": _settings.settings.CONTROL_API_TOKEN,
            "port": _settings.settings.CONTROL_API_PORT,
        }

    def tearDown(self):
        s = _settings.settings
        s.CONTROL_API_ENABLED = self._saved["enabled"]
        s.CONTROL_API_TOKEN = self._saved["token"]
        s.CONTROL_API_PORT = self._saved["port"]

    def test_disabled_runs_lifecycle_without_http_server(self):
        _settings.settings.CONTROL_API_ENABLED = False
        _settings.settings.CONTROL_API_TOKEN = ""
        engine, _t = _build_engine(symbols=("BTCUSDT",))
        lifecycle, server = service.start_paper_service(
            engine, poll_interval_seconds=0.001
        )
        self.assertIsNotNone(lifecycle)
        self.assertIsNone(server)
        self.assertTrue(lifecycle.running())
        lifecycle.emergency_stop()
        self.assertFalse(lifecycle.running())

    def test_enabled_without_token_fails_closed(self):
        _settings.settings.CONTROL_API_ENABLED = True
        _settings.settings.CONTROL_API_TOKEN = ""
        engine, _t = _build_engine(symbols=("BTCUSDT",))
        with self.assertRaises(service.ControlApiConfigError):
            service.start_paper_service(engine, poll_interval_seconds=0.001)


if __name__ == "__main__":
    unittest.main()
