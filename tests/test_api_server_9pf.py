"""
Phase 9P-f Control & Monitoring API server tests.

Exercises the REAL stdlib HTTP server (ThreadingHTTPServer on an
ephemeral localhost port) end-to-end against a FakeEngine, covering
auth (bearer token, fail-closed, constant-time), the full GET
read surface, and the PAPER-only allowlisted POST /control seam.

No network/exchange is involved.
"""

import http.client
import json
import threading
import time
import unittest
from dataclasses import dataclass, field

from core.monitoring.api_server import ControlApiServer
from core.runtime.lifecycle import EngineLifecycle

TOKEN = "test-token-1234"


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


@dataclass
class FakeMarket:
    symbol: str = "BTCUSDT"
    timeframe: str = "1m"
    mark_price: float = 50000.0
    best_bid: float = 49999.0
    best_ask: float = 50001.0
    spread: float = 2.0
    timestamp: int = 1000
    connected: bool = True


class FakePipeline:
    def __init__(self):
        self.market = FakeMarket()
        self.execution_signal = {"action": "BUY"}
        self.execution_signals = [{"action": "BUY"}, {"action": "SELL"}]


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


@dataclass
class FakeTrade:
    direction: str = "LONG"
    entry: float = 50000.0
    status: str = "OPEN"
    symbol: str = "BTCUSDT"
    pnl: float = 0.0


class FakeRuntime:
    def __init__(self):
        self.instrument = None
        self.pipeline = FakePipeline()
        self.current_trade = FakeTrade()
        self.executed_intents = ({"order_id": "o1", "side": "BUY"},)
        self.account = FakeAccount()
        self.engine = type(
            "E", (), {"dry_run": True, "placed": [], "registry": FakeLedger()}
        )()
        self.retired = False

    @property
    def symbol(self):
        return "BTCUSDT"

    @property
    def ledger(self):
        return FakeLedger()

    def state(self):
        return {
            "symbol": "BTCUSDT",
            "exchange": "DELTA",
            "instrument_id": "P-BTCUSDT",
            "retired": False,
            "processed_bars": 12,
            "open_position": True,
            "trades": 3,
            "balance": 99000.0,
            "equity": 99500.0,
        }


class FakeLedger:
    def open(self):
        return [FakeTrade()]

    def count(self):
        return 3


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


def _client(port):
    return http.client.HTTPConnection("127.0.0.1", port, timeout=10)


def _auth_get(port, path, token=TOKEN, headers=None):
    conn = _client(port)
    conn.request("GET", path, headers={
        "Authorization": "Bearer %s" % token,
        **(headers or {}),
    })
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(body)
    except Exception:
        return resp.status, body


def _auth_post(port, path, payload, token=TOKEN):
    conn = _client(port)
    body = json.dumps(payload)
    conn.request("POST", path, body=body, headers={
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json",
    })
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(data)
    except Exception:
        return resp.status, data


class ApiServerTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = FakeEngine()
        cls.lifecycle = EngineLifecycle(cls.engine, poll_interval_seconds=0.001)
        cls.server = ControlApiServer(
            cls.engine, cls.lifecycle, token=TOKEN, port=0
        )
        cls.server.construct()
        cls.port = cls.server.addr[1]
        cls.server.serve_forever_threaded()
        # give the daemon a moment to bind
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.lifecycle.emergency_stop()
        except Exception:
            pass
        cls.server.shutdown()


class TestAuthentication(ApiServerTestCase):

    def test_missing_token_is_401(self):
        status, _ = _auth_get(self.port, "/health", token="")
        self.assertEqual(status, 401)

    def test_wrong_token_is_401(self):
        status, _ = _auth_get(self.port, "/health", token="nope")
        self.assertEqual(status, 401)

    def test_correct_token_is_200(self):
        status, body = _auth_get(self.port, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "STOPPED")


class TestReadEndpoints(ApiServerTestCase):

    def _expect_200(self, path):
        status, body = _auth_get(self.port, path)
        self.assertEqual(status, 200, msg=path)
        return body

    def test_health(self):
        b = self._expect_200("/health")
        self.assertIn("engine_started", b)
        self.assertIn("uptime_seconds", b)
        self.assertIn("runtimes", b)

    def test_universe(self):
        b = self._expect_200("/universe")
        self.assertEqual(b["eligible_count"], 2)
        self.assertIn("BTCUSDT", b["eligible_symbols"])

    def test_subscriptions(self):
        b = self._expect_200("/subscriptions")
        self.assertEqual(b["enabled"], True)
        self.assertIn("BTCUSDT", b["statuses"])
        self.assertTrue(b["errors"])

    def test_runtimes(self):
        b = self._expect_200("/runtimes")
        self.assertIn("BTCUSDT", b)

    def test_market(self):
        b = self._expect_200("/market")
        self.assertEqual(b["BTCUSDT"]["symbol"], "BTCUSDT")
        self.assertEqual(b["BTCUSDT"]["mark_price"], 50000.0)

    def test_signals(self):
        b = self._expect_200("/signals")
        self.assertEqual(b["BTCUSDT"]["signal"]["action"], "BUY")

    def test_positions(self):
        b = self._expect_200("/positions")
        self.assertEqual(b["BTCUSDT"]["current_trade"]["direction"], "LONG")

    def test_orders(self):
        b = self._expect_200("/orders")
        self.assertEqual(b["BTCUSDT"]["intents"][0]["order_id"], "o1")

    def test_account(self):
        b = self._expect_200("/account")
        self.assertEqual(b["sum_balance"], 99000.0)
        self.assertIn("shared_capital", b)

    def test_risk(self):
        b = self._expect_200("/risk")
        self.assertEqual(b["portfolio"]["current_risk"], 500.0)

    def test_performance(self):
        b = self._expect_200("/performance")
        self.assertEqual(b["aggregate"]["total_trades"], 1)

    def test_errors(self):
        b = self._expect_200("/errors")
        self.assertTrue(b["errors"])

    def test_unknown_route_is_404(self):
        status, _ = _auth_get(self.port, "/nonexistent")
        self.assertEqual(status, 404)


class TestControlEndpoints(ApiServerTestCase):

    def test_start_command(self):
        status, body = _auth_post(self.port, "/control", {"command": "start"})
        self.assertEqual(status, 200)
        self.assertEqual(body["command"], "start")
        self.assertEqual(body["lifecycle_state"], "RUNNING")
        self.assertTrue(self.engine.started)

    def test_stop_command(self):
        self.lifecycle.start()
        status, body = _auth_post(self.port, "/control", {"command": "stop"})
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "STOPPED")
        self.assertFalse(self.engine.started)

    def test_restart_command(self):
        status, body = _auth_post(
            self.port, "/control", {"command": "restart"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "RUNNING")

    def test_emergency_stop_command(self):
        self.lifecycle.start()
        status, body = _auth_post(
            self.port, "/control", {"command": "emergency_stop"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["lifecycle_state"], "STOPPED")

    def test_unknown_command_is_400(self):
        status, body = _auth_post(
            self.port, "/control", {"command": "place_order"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "control_rejected")
        self.assertFalse(self.engine.started)

    def test_non_command_body_is_400(self):
        status, _ = _auth_post(self.port, "/control", {"foo": 1})
        self.assertEqual(status, 400)

    def test_control_requires_auth(self):
        status, _ = _auth_post(
            self.port, "/control", {"command": "start"}, token="bad"
        )
        self.assertEqual(status, 401)
        self.assertEqual(self.lifecycle.state, "STOPPED")


class TestPaperGuard(unittest.TestCase):
    """Defensive runtime assertion: control is PAPER-only. Refuses when
    an active runtime is not dry_run, or the process is LIVE-mode."""

    def test_refuses_non_dry_run_runtime(self):
        from core.monitoring.api_server import _assert_paper_capable
        from core.runtime.lifecycle import ControlCommandError

        class _LiveRuntime:
            class _E:
                dry_run = False

            engine = _E()

        engine = type("E", (), {"runtimes": {"x": _LiveRuntime()}})()

        with self.assertRaises(ControlCommandError):
            _assert_paper_capable(engine)

    def test_allows_dry_run_runtime(self):
        from core.monitoring.api_server import _assert_paper_capable

        class _PaperRuntime:
            class _E:
                dry_run = True

            engine = _E()

        engine = type("E", (), {"runtimes": {"x": _PaperRuntime()}})()

        # must not raise
        _assert_paper_capable(engine)

    def test_refuses_when_live_mode_configured_without_paper(self):
        from core.monitoring.api_server import _assert_paper_capable
        from core.runtime.lifecycle import ControlCommandError

        engine = type("E", (), {"runtimes": {}})()

        import config.settings as _settings

        saved_live = _settings.settings.LIVE_MODE
        saved_paper = _settings.settings.PAPER_MODE
        try:
            _settings.settings.LIVE_MODE = True
            _settings.settings.PAPER_MODE = False
            with self.assertRaises(ControlCommandError):
                _assert_paper_capable(engine)
        finally:
            _settings.settings.LIVE_MODE = saved_live
            _settings.settings.PAPER_MODE = saved_paper


if __name__ == "__main__":
    unittest.main()
class TestRiskPolicyApi(ApiServerTestCase):
    def test_risk_policy_get_and_instrument_override(self):
        status, body = _auth_get(self.port, "/risk-policy")
        self.assertEqual(status, 200)
        self.assertEqual(body["global"]["min_rr"], 1.0)
        self.assertEqual(body["global"]["max_rr"], 20.0)
        self.assertIn("instruments", body)

    def test_risk_policy_rejects_out_of_bounds(self):
        status, body = _auth_post(self.port, "/risk-policy", {
            "scope": "global",
            "policy": {"min_rr": 0.5, "max_rr": 20.0},
        })
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "bad_request")

    def test_risk_policy_instrument_round_trip(self):
        from core.risk.trading_policy import trading_policy_manager
        manager = trading_policy_manager()
        before = manager.snapshot()
        try:
            status, body = _auth_post(self.port, "/risk-policy", {
                "scope": "instrument",
                "symbol": "TEST-API",
                "policy": {
                    "min_rr": 2.0,
                    "max_rr": 10.0,
                    "trailing_enabled": True,
                    "trailing_activation_r": 1.25,
                    "trailing_distance_r": 0.5,
                    "auto_exit_on_opposite_signal": True,
                },
            })
            self.assertEqual(status, 200)
            self.assertEqual(body["instruments"]["TEST-API"]["min_rr"], 2.0)
            self.assertEqual(body["instruments"]["TEST-API"]["max_rr"], 10.0)
            status, body = _auth_post(self.port, "/risk-policy/reset", {"symbol": "TEST-API"})
            self.assertEqual(status, 200)
            self.assertNotIn("TEST-API", body["instruments"])
        finally:
            manager.set_global(before["global"])
            for key in list(manager.snapshot()["instruments"]):
                manager.reset_instrument(key)
            for key, values in before["instruments"].items():
                manager.set_instrument(key, values)
