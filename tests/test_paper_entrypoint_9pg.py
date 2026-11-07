"""
Phase 9P-g Production PAPER Entrypoint integration tests.

Drives the REAL main.py PAPER startup path (core/monitoring/service)
offline: build the canonical engine -> start the lifecycle -> start
the monitoring API -> exercise the read surface -> POST a PAPER
control stop -> clean shutdown.

This is the acceptance path:
    main.py -> build PAPER engine -> start lifecycle ->
    start monitoring API -> GET /health -> GET /universe ->
    GET /performance -> POST /control/stop -> clean shutdown

The API is disabled by default, so the API-disabled case must run
the paper loop with NO HTTP server (preserving pre-9P-g behaviour).

No network / no exchange: the engine is assembled with fake
transport + explicit manager + scripted worlds (mirroring
test_paper_main_runtime), and the HTTP server binds localhost on an
ephemeral port.
"""

import http.client
import json
import threading
import time
import unittest

import config.settings as _settings

from core.monitoring import service
from core.runtime.paper_main import (
    ExplicitSymbolUniverseManager,
    build_paper_engine,
)

TOKEN = "entrypoint-token"


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


def _client(port):
    return http.client.HTTPConnection("127.0.0.1", port, timeout=10)


def _get(port, path, token=TOKEN):
    conn = _client(port)
    conn.request("GET", path, headers={"Authorization": "Bearer %s" % token})
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    return resp.status, json.loads(data)


def _post(port, path, payload, token=TOKEN):
    conn = _client(port)
    body = json.dumps(payload)
    conn.request("POST", path, body=body, headers={
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json",
    })
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    return resp.status, json.loads(data)


class PaperEntrypointTestCase(unittest.TestCase):

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

        # mirror the production run_paper_with_monitoring loop: a
        # blocker waits until the lifecycle leaves RUNNING then shuts
        # down both the lifecycle and the HTTP server.
        self._blocker_done = threading.Event()

        def block():
            service.block_until_stopped(self.lifecycle, self.server)
            self._blocker_done.set()

        self._blocker = threading.Thread(target=block, daemon=True)
        self._blocker.start()

        # wait for the server to accept connections
        deadline = time.time() + 3.0
        while True:
            try:
                status, _ = _get(self.port, "/health")
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
        self._blocker.join(timeout=5.0)

        s = _settings.settings
        s.CONTROL_API_ENABLED = self._saved["enabled"]
        s.CONTROL_API_TOKEN = self._saved["token"]
        s.CONTROL_API_PORT = self._saved["port"]
        s.CONTROL_API_POLL_SECONDS = self._saved["poll"]


class TestAcceptancePath(PaperEntrypointTestCase):

    def test_health_universe_performance_control_stop_shutdown(self):
        # GET /health
        status, body = _get(self.port, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "RUNNING")
        self.assertTrue(body["engine_started"])

        # GET /universe (explicit -> settings symbols)
        status, body = _get(self.port, "/universe")
        self.assertEqual(status, 200)
        self.assertIn("BTCUSDT", body["eligible_symbols"])
        self.assertIn("ETHUSDT", body["eligible_symbols"])

        # GET /performance (empty ledger -> aggregate present)
        status, body = _get(self.port, "/performance")
        self.assertEqual(status, 200)
        self.assertIn("aggregate", body)

        # POST /control/stop -> clean shutdown of the runtime loop
        status, body = _post(self.port, "/control", {"command": "stop"})
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "STOPPED")

        # the blocker loop must drain: shutting down BOTH the lifecycle
        # and the HTTP server when the runtime leaves RUNNING.
        self.assertTrue(self._blocker_done.wait(timeout=5.0))
        self.assertFalse(self._blocker.is_alive())
        self.assertFalse(self.server.running())
        self.assertFalse(self.lifecycle.running())
        self.assertFalse(self.engine.started)

    def test_reads_and_control_share_the_authoritative_runtime(self):
        # /runtimes reflects the actual engine runtimes
        status, runtimes = _get(self.port, "/runtimes")
        self.assertEqual(status, 200)
        self.assertEqual(len(runtimes), 2)

        # /subscriptions reflects the actual subscription manager
        status, subs = _get(self.port, "/subscriptions")
        self.assertEqual(status, 200)
        self.assertEqual(subs["enabled"], True)

        # engine has stopped by lifecycle stop
        _post(self.port, "/control", {"command": "stop"})
        self.assertFalse(self.engine.started)


class TestApiDisabledDefault(unittest.TestCase):
    """With CONTROL_API_ENABLED=false (the safe default) the PAPER
    entrypoint must start the lifecycle but NOT bind any HTTP server,
    preserving the pre-9P-g run_paper_forever behaviour."""

    def setUp(self):
        self._saved = {
            "enabled": _settings.settings.CONTROL_API_ENABLED,
            "token": _settings.settings.CONTROL_API_TOKEN,
            "port": _settings.settings.CONTROL_API_PORT,
        }
        _settings.settings.CONTROL_API_ENABLED = False
        _settings.settings.CONTROL_API_TOKEN = ""
        _settings.settings.CONTROL_API_PORT = 0

    def tearDown(self):
        s = _settings.settings
        s.CONTROL_API_ENABLED = self._saved["enabled"]
        s.CONTROL_API_TOKEN = self._saved["token"]
        s.CONTROL_API_PORT = self._saved["port"]

    def test_disabled_runs_lifecycle_without_http_server(self):
        engine, _transport = _build_engine(symbols=("BTCUSDT",))

        lifecycle, server = service.start_paper_service(
            engine, poll_interval_seconds=0.001
        )

        self.assertIsNotNone(lifecycle)
        self.assertIsNone(server)  # no HTTP surface when disabled
        self.assertTrue(lifecycle.running())
        self.assertTrue(engine.started)

        # a stop still cleanly tears the loop down
        lifecycle.emergency_stop()
        self.assertFalse(lifecycle.running())
        self.assertFalse(engine.started)


if __name__ == "__main__":
    unittest.main()
