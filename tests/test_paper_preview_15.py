"""Paper preview: API/dashboard/isolation/restart/disconnect safety.

Drives the REAL preview stack offline (build_paper_engine with fake
transport + scripted worlds + ControlApiServer with preview routes):
proves the read-only browser surface, the Phase-9 A-P safety
boundaries, restart determinism, and disconnect behavior. No network.
"""

from __future__ import annotations

import http.client
import io
import json
import os
import tokenize
import unittest
from pathlib import Path

from core.history.candle import Candle
from core.runtime.paper_main import (
    ExplicitSymbolUniverseManager,
    build_paper_engine,
)

TOKEN = "preview-test-token"
ROOT = Path(__file__).resolve().parents[1]


def closed_bar(stamp, close=100.0, symbol="BTCUSDT"):
    return Candle(timestamp=stamp, open=close - 1.0, high=close + 1.0,
                  low=close - 2.0, close=close, volume=50.0,
                  symbol=symbol, closed=True)


class FakeTransport:
    def __init__(self):
        self._routes = {}
        self.closed = False
        self.down_calls = []

    def subscribe(self, symbol, on_candle, on_down):
        self._routes[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol):
        self._routes.pop(symbol, None)

    def push(self, symbol, candle):
        self._routes[symbol][0](candle)

    def drop(self, symbol):
        self._routes[symbol][1]()

    def close(self):
        self.closed = True
        self._routes.clear()

    def recent_closed(self, symbol, limit=60):
        return []

    def stats(self, symbol=None):
        return {}


class ScriptedWorld:
    def __init__(self, context):
        self.context = context
        self.candles_seen = []

    def reset(self):
        self.candles_seen = []

    def on_candle(self, event):
        self.candles_seen.append(event.candle)
        self.context.add_candle(event.candle)


class FakeClock:
    def __init__(self, now=0.0):
        self.now = float(now)

    def __call__(self):
        return self.now


def build(symbols=("BTCUSDT",)):
    manager = ExplicitSymbolUniverseManager(
        symbols=list(symbols), timeframe="1m")
    transport = FakeTransport()
    engine, _manager = build_paper_engine(
        universe_manager=manager,
        transport_factory=lambda: transport,
        world_factory=ScriptedWorld,
        clock=FakeClock(now=1000.0),
        timeframe="1m",
        refresh_interval_seconds=0,
    )
    engine.start()
    return engine, transport


def serve(engine, transport):
    from core.monitoring.api_server import ControlApiServer
    from core.monitoring.preview_routes import preview_routes

    class Lifecycle:
        def health(self):
            return {"lifecycle": "test"}

        def command(self, command):
            raise AssertionError("no control in read tests")

    server = ControlApiServer(
        engine, Lifecycle(), token=TOKEN,
        host="127.0.0.1", port=0,
        extra_routes=preview_routes(engine, transport))
    server.construct()
    import threading
    thread = threading.Thread(target=server._httpd.serve_forever,
                              daemon=True)
    thread.start()
    return server


def get(server, path, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.addr[1], timeout=10)
    conn.request("GET", path,
                 headers={"Authorization": "Bearer " + token})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, resp.getheader("Content-Type", ""), body


def post(server, path, payload, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.addr[1], timeout=10)
    conn.request("POST", path, body=json.dumps(payload),
                 headers={"Authorization": "Bearer " + token,
                          "Content-Type": "application/json"})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


class PreviewStackMixin:
    def _stack(self, symbols=("BTCUSDT",)):
        engine, transport = build(symbols)
        self.addCleanup(engine.stop)
        server = serve(engine, transport)
        self.addCleanup(server.shutdown)
        return engine, transport, server


class TestPreviewApiSurface(PreviewStackMixin, unittest.TestCase):
    def test_read_routes_reachable(self):
        _engine, _transport, server = self._stack()
        for path in ("/health", "/preview", "/market", "/signals",
                     "/positions", "/orders", "/account", "/risk",
                     "/performance", "/errors", "/runtimes",
                     "/universe", "/subscriptions", "/candles",
                     "/evidence"):
            status, content_type, body = get(server, path)
            self.assertEqual(status, 200, path)
            self.assertIn("application/json", content_type, path)
            json.loads(body.decode("utf-8"))

    def test_unauthorized_refused(self):
        _engine, _transport, server = self._stack()
        status, _, _ = get(server, "/health", token="wrong")
        self.assertEqual(status, 401)

    def test_dashboard_serves_html(self):
        _engine, _transport, server = self._stack()
        status, content_type, body = get(server, "/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        text = body.decode("utf-8")
        self.assertIn("PAPER", text)
        self.assertIn("LIVE EXECUTION", text)

    def test_preview_identity(self):
        _engine, _transport, server = self._stack()
        _status, _, body = get(server, "/preview")
        meta = json.loads(body.decode("utf-8"))
        self.assertEqual(meta["mode"], "PAPER_ONLY")
        self.assertFalse(meta["live_execution"])
        self.assertFalse(meta["is_production_ready"])

    def test_no_order_mutation_routes(self):
        _engine, _transport, server = self._stack()
        paths = sorted(k[1] for k in server.routes.keys())
        for forbidden in ("/order", "/buy", "/sell", "/cancel",
                          "/close", "/enable-live", "/production",
                          "/trade", "/position"):
            self.assertNotIn(forbidden, paths, forbidden)
        posts = sorted(k[1] for k in server.routes.keys()
                       if k[0] == "POST")
        # PAPER lifecycle control remains separate from the authenticated
        # risk/exit policy configuration surface.  Neither is a trade
        # submission route; the dashboard may call only /risk-policy.
        self.assertEqual(posts, ["/control", "/risk-policy", "/risk-policy/reset"])

    def test_control_not_called_by_dashboard(self):
        text = (ROOT / "core" / "monitoring"
                / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("/control", text)
        self.assertIn('apiPost("/risk-policy"', text)
        self.assertNotIn('apiPost("/order"', text)
        self.assertNotIn('apiPost("/buy"', text)
        self.assertNotIn('apiPost("/sell"', text)
        self.assertNotIn('apiPost("/cancel"', text)
        self.assertNotIn('apiPost("/close"', text)


class TestPreviewIsolation(PreviewStackMixin, unittest.TestCase):
    def test_paper_runtimes_all_dry_run(self):
        engine, _transport, _server = self._stack()
        self.assertTrue(engine.runtimes)
        for runtime in engine.runtimes.values():
            self.assertTrue(runtime.engine.dry_run)

    def test_closed_candles_route_no_duplicates(self):
        engine, transport, _server = self._stack()
        bars = [closed_bar(1000 + 60 * i, 100.0 + i)
                for i in range(5)]
        for candle in bars:
            transport.push("BTCUSDT", candle)
        # Redeliver everything: router dedupe must hold.
        for candle in bars:
            transport.push("BTCUSDT", candle)
        world = engine.runtimes[("DELTA", "BTCUSDT")].pipeline.world
        self.assertEqual(len(world.candles_seen), 5)
        self.assertEqual(engine.routed, 5)

    def test_disconnect_creates_no_orders(self):
        engine, transport, _server = self._stack()
        transport.drop("BTCUSDT")
        for runtime in engine.runtimes.values():
            self.assertIsNone(runtime.current_trade)
            self.assertEqual(len(runtime.ledger.all()), 0)

    def test_preview_files_have_no_live_submission_calls(self):
        # Code-token scan (strings/comments blanked): preview
        # files must never call live order submission.
        files = [
            ROOT / "data" / "delta" / "rest_candle_transport.py",
            ROOT / "core" / "monitoring" / "preview_routes.py",
            ROOT / "scripts" / "paper_preview.py",
        ]
        for path in files:
            src = path.read_text(encoding="utf-8")
            code = "".join(
                " " * (t.end[1] - t.start[1]) if t.type in
                (tokenize.STRING, tokenize.COMMENT) else t.string
                for t in tokenize.generate_tokens(
                    io.StringIO(src).readline))
            for token in ("DeltaOrderExecutor(",
                          ".place_order(", ".submit_order(",
                          ".cancel_order("):
                self.assertNotIn(token, code,
                                 "%s:%s" % (path.name, token))

    def test_dashboard_has_no_trading_controls(self):
        text = (ROOT / "core" / "monitoring"
                / "dashboard.html").read_text(encoding="utf-8")
        lowered = text.lower()
        # Risk/exit policy controls are intentionally present and
        # authenticated. Trading/order controls remain absent.
        self.assertIn("save global / instrument", lowered)
        self.assertIn("reset instrument override", lowered)
        self.assertNotIn("enable live", lowered)
        self.assertNotIn("enable production", lowered)
        self.assertNotIn('apipost("/order"', lowered)
        self.assertNotIn('apipost("/buy"', lowered)
        self.assertNotIn('apipost("/sell"', lowered)
        self.assertNotIn('apipost("/cancel"', lowered)
        self.assertNotIn('apipost("/close"', lowered)


class TestPreviewProductionFlags(unittest.TestCase):
    def test_production_flags_false(self):
        from core.monitoring.preview_routes import (
            LIVE_EXECUTION,
            PREVIEW_MODE,
        )

        self.assertEqual(PREVIEW_MODE, "PAPER_ONLY")
        self.assertIs(LIVE_EXECUTION, False)

    def test_research_reports_stay_non_production(self):
        from core.research.regime.report import RegimeReport

        self.assertIs(RegimeReport().is_production_ready, False)

    def test_rr_boundaries(self):
        from core.risk.costs import post_cost_rr

        refused = post_cost_rr(
            direction="BULLISH", entry=100.0, stop=90.0,
            target=105.0, quantity=2.0, commission=0.0,
            slippage=0.0)
        self.assertFalse(refused.allowed)
        accepted = post_cost_rr(
            direction="BULLISH", entry=101.0, stop=98.5,
            target=116.0, quantity=1.5, commission=0.0,
            slippage=0.0)
        self.assertTrue(accepted.allowed)
        self.assertAlmostEqual(accepted.rr, 6.0, places=9)

    def test_paper_semantics_without_contract_or_costs(self):
        # Missing contract metadata: legacy UNAVAILABLE
        # pass-through (existing paper semantics preserved).
        from core.risk.contract_gate import UNAVAILABLE, resolve_terms
        from core.risk.order_intent import OrderIntent

        _terms, status = resolve_terms(
            OrderIntent(direction="BULLISH", entry=100.0))
        self.assertEqual(status, UNAVAILABLE)
        # Missing economics: zero costs keep the cost-aware layer
        # vacuous (existing semantics preserved).
        from core.risk.costs import post_cost_rr

        verdict = post_cost_rr(
            direction="BULLISH", entry=100.0, stop=90.0,
            target=170.0, quantity=2.0, commission=0.0,
            slippage=0.0)
        self.assertTrue(verdict.allowed)


class TestPreviewRestart(unittest.TestCase):
    def test_rebuild_replay_is_deterministic_no_duplication(self):
        # Two fresh runs over identical bars produce identical
        # registries (deterministic replay, never duplication).
        def run_once():
            engine, transport = build()
            bars = [closed_bar(1000 + 60 * i, 100.0 + (i % 3))
                    for i in range(8)]
            for candle in bars:
                transport.push("BTCUSDT", candle)
            transport.close()
            counts = {}
            pnls = {}
            for key, runtime in engine.runtimes.items():
                trades = runtime.ledger.all()
                counts[key] = len(trades)
                pnls[key] = round(sum(
                    float(getattr(t, "pnl", 0.0) or 0.0)
                    for t in trades), 6)
            engine.stop()
            return counts, pnls

        first = run_once()
        second = run_once()
        self.assertEqual(first, second)


class TestPreviewLauncherRefusal(unittest.TestCase):
    @staticmethod
    def _load_launcher():
        import importlib.util

        path = (ROOT / "scripts" / "paper_preview.py")
        spec = importlib.util.spec_from_file_location(
            "paper_preview_launcher", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_launcher_refuses_live_mode(self):
        import os
        from unittest import mock

        launcher = self._load_launcher()
        with mock.patch.dict(os.environ, {"LIVE_MODE": "true"}):
            with self.assertRaises(SystemExit) as ctx:
                launcher._refuse_live()
            self.assertEqual(ctx.exception.code, 2)
        with mock.patch.dict(os.environ,
                             {"EXECUTION_MODE": "LIVE",
                              "LIVE_MODE": ""}):
            with self.assertRaises(SystemExit) as ctx:
                launcher._refuse_live()
            self.assertEqual(ctx.exception.code, 2)

    def test_launcher_refuses_unknown_execution_mode(self):
        import os
        from unittest import mock

        launcher = self._load_launcher()
        with mock.patch.dict(os.environ,
                             {"EXECUTION_MODE": "MARS",
                              "LIVE_MODE": ""}):
            with self.assertRaises(SystemExit):
                launcher._refuse_live()


class TestLauncherDirectExecution(unittest.TestCase):
    def test_bootstrap_resolves_repo_root_packages(self):
        # Static contract: the launcher establishes the repo root
        # on sys.path BEFORE any QuantEngine import, using the
        # canonical scripts/ convention (parents[1]).
        text = (ROOT / "scripts" / "paper_preview.py").read_text(
            encoding="utf-8")
        self.assertIn("parents[1]", text)
        self.assertIn("sys.path.insert", text)
        core_import = text.find("from core.monitoring import")
        bootstrap = text.find("sys.path.insert")
        self.assertGreaterEqual(core_import, 0)
        self.assertGreaterEqual(bootstrap, 0)
        self.assertLess(bootstrap, core_import)

    @unittest.skipUnless(os.getenv("QE_LIVE_NETWORK") == "1",
                         "requires live public network")
    def test_direct_script_command_starts_preview(self):
        # The exact documented command, run as a direct script
        # from the repository root (regression for
        # ModuleNotFoundError: No module named 'core').
        import os
        import subprocess
        import sys

        env = dict(os.environ)
        env["PREVIEW_RUN_SECONDS"] = "10"
        env["PREVIEW_PORT"] = "8799"
        env.pop("LIVE_MODE", None)
        env.pop("EXECUTION_MODE", None)
        proc = subprocess.run(
            [sys.executable, "scripts/paper_preview.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=180, env=env)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("ModuleNotFoundError", combined)
        self.assertIn("QuantEngine PAPER PREVIEW", proc.stdout)
        self.assertIn("PAPER_ONLY", proc.stdout)
        self.assertIn("LIVE EXECUTION  : DISABLED", proc.stdout)
        self.assertEqual(proc.returncode, 0)


class TestDashboardAuthFlow(PreviewStackMixin, unittest.TestCase):
    def _anon(self, server, path):
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", server.addr[1], timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        ctype = resp.getheader("Content-Type", "")
        conn.close()
        return resp.status, ctype, body

    def test_dashboard_shell_needs_no_token(self):
        _engine, _transport, server = self._stack()
        status, ctype, body = self._anon(server, "/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        text = body.decode("utf-8")
        self.assertIn("PAPER", text)
        # The shell carries no token and no persistence.
        self.assertNotIn("paper-preview-local-dev", text)
        self.assertNotIn("localStorage", text)
        self.assertNotIn("sessionStorage", text)
        self.assertNotIn("document.cookie", text)

    def test_data_routes_reject_missing_token(self):
        _engine, _transport, server = self._stack()
        for path in ("/preview", "/candles", "/evidence",
                     "/health", "/market", "/signals", "/orders",
                     "/positions", "/account"):
            status, _, _ = self._anon(server, path)
            self.assertEqual(status, 401, path)

    def test_data_routes_reject_wrong_token(self):
        _engine, _transport, server = self._stack()
        status, _, _ = get(server, "/evidence", token="wrong")
        self.assertEqual(status, 401)

    def test_data_routes_accept_valid_token(self):
        _engine, _transport, server = self._stack()
        for path in ("/preview", "/candles", "/evidence"):
            status, _, body = get(server, path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)

    def test_server_stays_localhost_only(self):
        _engine, _transport, server = self._stack()
        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.addr[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
