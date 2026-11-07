"""
====================================================

QuantEngine

Phase 11C -- realtime paper chain, soak, resources,
restart, event-loop responsiveness, Gate A determinism.

  11C-I  full realtime paper chain (REAL market-data
         input -> closed candle -> CandleBuilder ->
         RealTimeEngine -> SymbolPipeline (REAL
         InstitutionalPipeline) -> strategy -> signal ->
         risk -> OrderIntent -> PAPER execution -> fill ->
         position -> trade -> reconciliation). Paper mode,
         fake transport, zero live REST.
  11C-K  event-loop responsiveness (provider latency vs
         poll latency, reported separately)
  11C-L  multi-symbol operational soak (10 / 25 / 50)
  11C-M  resource measurement (tracemalloc + threads)
  11C-N  restart / recovery (clean restart; persistent
         trading-state recovery documented NOT
         IMPLEMENTED; catalog persistence round-trip)
  11C-U  deterministic Gate A regression (two separate
         clean processes)

Paper/fake-transport/deterministic-replay ONLY.

====================================================
"""

import statistics
import threading
import time
import unittest


# ====================================================
# Shared harness
# ====================================================


class FakeClock:

    def __init__(self, now=1_000_000.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class FakeTransport:
    """Offline multiplexed transport (mirrors the 6D
    contract). push/down target one route; subscribe_calls
    counts every (re)subscription per symbol."""

    def __init__(self, fail_on_subscribe=None):
        self._routes = {}
        self._fail = set(fail_on_subscribe or [])
        self.subscribe_calls = {}
        self.unsubscribed = []
        self.closed = False
        self.down_signals = []

    def subscribe(self, symbol, on_candle, on_down):
        self.subscribe_calls[symbol] = (
            self.subscribe_calls.get(symbol, 0) + 1
        )
        if symbol in self._fail:
            raise RuntimeError("subscribe failed: " + symbol)
        self._routes[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol):
        self._routes.pop(symbol, None)
        self.unsubscribed.append(symbol)

    def push(self, symbol, candle):
        route = self._routes.get(symbol)
        if route is not None:
            route[0](candle)

    def down(self, symbol):
        route = self._routes.get(symbol)
        if route is not None:
            self.down_signals.append(symbol)
            route[1]()

    def close(self):
        self.closed = True
        self._routes.clear()


class ScriptedWorld:
    """Pipeline-compatible world emitting ONE deterministic
    OrderIntent on a chosen candle (through the REAL
    OrderRegistry, exactly like the institutional world)."""

    def __init__(self, context):
        self.context = context
        self.on_candle_calls = 0
        self.order_plan = None
        self.fired = False

    def plan(self, order, fire_candle_index):
        self.order_plan = (fire_candle_index, order)

    def reset(self):
        self.on_candle_calls = 0
        self.fired = False

    def on_candle(self, event):
        from core.events.candle_event import CandleEvent  # noqa

        self.on_candle_calls += 1
        self.context.add_candle(event.candle)
        if self.order_plan is None or self.fired:
            return
        fire_index, order = self.order_plan
        if self.on_candle_calls != fire_index:
            return
        registered, _ = self.context.order_registry.create(order)
        self.context.order = registered
        self.context.execution_signal = registered
        self.fired = True


def make_order(symbol, entry=100.0, direction="BULLISH", idx=0):
    from config import risk_settings
    from core.risk.order_intent import OrderIntent

    # Phase-15 maintenance: gate-compliant economics (reward 14 /
    # risk 2 = RR 7.0 >= 6, zero costs so the post-cost layer is
    # vacuous), because BrokerEngine._route now enforces the
    # mandatory geometry + gross-RR + post-cost gates. Soak intent
    # (multi-symbol plumbing: subscriptions, candles, fills)
    # unchanged.
    stop = entry - 2.0 if direction == "BULLISH" else entry + 2.0
    take = entry + 14.0 if direction == "BULLISH" else entry - 14.0
    return OrderIntent(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=take,
        risk_reward=7.0,
        quantity=1.0,
        risk_percent=1.0,
        risk_amount=2.0,
        expected_loss=2.0,
        expected_profit=14.0,
        position_value=entry,
        leverage=1.0,
        commission=0.0,
        slippage=0.0,
        confidence=0.8,
        score=90.0,
        symbol=symbol,
        timeframe="1m",
        setup_id="S-11C-{}-{}".format(symbol, idx),
        entry_mode=risk_settings.ENTRY_MODE,
        canonical_id="CID-11C-{}-{}".format(symbol, idx),
        status="NEW",
        valid=True,
    )


def make_closed_candle(timestamp, price, symbol, closed=True):
    from core.history.candle import Candle

    return Candle(
        timestamp=timestamp,
        open=price,
        high=price + 0.5,
        low=price - 0.5,
        close=price,
        volume=100.0,
        closed=closed,
        symbol=symbol,
    )


def raw_product_row(symbol, pid):
    return {
        "id": pid,
        "symbol": symbol,
        "contract_type": "perpetual_futures",
        "tick_size": "0.01",
        "contract_value": "1",
        "minimum_order_size": "1",
        "state": "live",
        "underlying_asset": {"symbol": "X"},
        "quoting_asset": {"symbol": "USDT"},
        "price_precision": 2,
        "contract_value_precision": 0,
    }


class FakeProductClient:

    def __init__(self, rows):
        self.rows = list(rows)

    def fetch(self):
        return list(self.rows)


class ScriptedLiquidity:

    def __init__(self, volume=10_000_000.0, delay=0.0):
        self.volume = volume
        self.delay = delay
        self.calls = 0
        self.durations = []

    def quote_volume_24h(self, symbol):
        tick = time.perf_counter()
        if self.delay:
            time.sleep(self.delay)
        self.calls += 1
        self.durations.append(time.perf_counter() - tick)
        return self.volume


class ScriptedHistory:

    def __init__(self, bars=500, delay=0.0):
        self.bars = bars
        self.delay = delay
        self.calls = 0

    def history_bars(self, symbol, timeframe="1m"):
        if self.delay:
            time.sleep(self.delay)
        self.calls += 1
        return self.bars


def build_manager(symbols, liq=None, hist=None):
    from core.registry.instrument_registry import InstrumentRegistry
    from core.universe.universe_manager import UniverseManager

    registry = InstrumentRegistry()
    manager = UniverseManager(
        registry=registry,
        liquidity_provider=liq or ScriptedLiquidity(),
        history_provider=hist or ScriptedHistory(),
    )
    client = FakeProductClient(
        [raw_product_row(s, 101 + i) for i, s in enumerate(symbols)]
    )
    manager.refresh_discovery(client=client)
    manager.refresh_discovery(client=client)
    return manager, client


def build_engine(symbols, fire_map=None, clock=None,
                 transport=None, universe_manager=None):
    """RealTimeEngine over scripted worlds (soak path)."""
    from core.runtime.realtime_engine import RealTimeEngine

    clock = clock or FakeClock()
    transport = transport or FakeTransport()
    worlds = {}

    def world_factory(context):
        world = ScriptedWorld(context)
        plan = (fire_map or {}).get(context.market.symbol)
        if plan is not None:
            order, index = plan
            world.plan(order, index)
        worlds[context.market.symbol] = world
        return world

    engine = RealTimeEngine(
        universe_manager=universe_manager,
        clock=clock,
        transport_factory=lambda: transport,
        world_factory=world_factory,
        refresh_interval_seconds=3600,
    )
    return engine, transport, clock, worlds


def percentile(samples, pct):
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = min(len(ordered) - 1, int(len(ordered) * pct / 100.0))
    return ordered[rank]


# ====================================================
# 11C-I -- full realtime paper chain (REAL strategy)
# ====================================================


class TestRealtimePaperChain11C(unittest.TestCase):
    """The critical gate: REAL Gate A market data through the
    REAL runtime components (no Backtester shortcut)."""

    @classmethod
    def setUpClass(cls):
        import json
        from pathlib import Path

        from data.candle_builder import CandleBuilder

        raw_path = (
            Path(__file__).resolve().parent.parent
            / "docs" / "audit" / "baseline_9s_delta_5000_raw.json"
        )
        with open(raw_path) as handle:
            raw = json.load(handle)["raw"]
        builder = CandleBuilder(max_history=len(raw) or 1)
        builder.load_history(list(reversed(raw)))
        cls.history = list(builder.history)
        assert len(cls.history) == 5000

    def test_full_chain_market_data_to_reconciliation(self):
        import httpx

        from core.runtime.realtime_engine import RealTimeEngine
        from core.universe.market_universe import Instrument

        instrument = Instrument(
            instrument_id="id-BTCUSDT",
            symbol="BTCUSDT",
            exchange="delta",
            trading_enabled=True,
        )

        class SnapMgr:
            def refresh_discovery(self, client=None, normalizer=None):
                return {"instruments": 1}

            def build_universe(self, timeframe="1m"):
                class Universe:
                    def eligible_instruments(self):
                        return [instrument]

                return Universe()

        transport = FakeTransport()
        engine = RealTimeEngine(
            universe_manager=SnapMgr(),
            transport_factory=lambda: transport,
            refresh_interval_seconds=0,
        )

        # 9. Live-REST tripwire: ANY real HTTP through httpx
        # fails the test immediately (paper chain must be
        # fully offline).
        real_get = httpx.Client.get
        real_post = httpx.Client.post
        http_calls = []

        def tripwire(self, *args, **kwargs):
            http_calls.append(args)
            raise AssertionError(
                "real HTTP attempted from the paper chain: {!r}".format(
                    args[:1]
                )
            )

        httpx.Client.get = tripwire
        httpx.Client.post = tripwire
        try:
            engine.start()
            from core.history.candle import Candle

            for bar in self.history:
                transport.push(
                    "BTCUSDT",
                    Candle(
                        timestamp=bar.timestamp,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        closed=True,
                        symbol="BTCUSDT",
                    ),
                )
            engine.subscriptions.poll()
        finally:
            httpx.Client.get = real_get
            httpx.Client.post = real_post

        # 1. valid closed candles reached the SymbolPipeline.
        runtime = list(engine.runtimes.values())[0]
        self.assertEqual(runtime.processed_bars, 5000)
        self.assertEqual(engine.routed, 5000)
        self.assertEqual(engine.unrouted, 0)
        self.assertEqual(engine.route_errors, 0)
        # 2/3/4. strategy produced signals, risk validated,
        # OrderIntents reached paper execution.
        placed = runtime.engine.placed
        self.assertGreater(len(placed), 0)
        for intent in placed:
            self.assertTrue(intent.valid)
        # 5/6/7. paper fills occurred, positions updated,
        # trades recorded.
        ledger = runtime.ledger.all()
        self.assertGreater(len(ledger), 0)
        # 8. reconciliation: account balance reconciles with
        # the sum of booked trade P&L (no fabricated state).
        starting = runtime.engine._starting_balance
        booked = sum(t.pnl for t in ledger)
        self.assertAlmostEqual(
            runtime.account.balance, starting + booked, places=6
        )
        # Paper boundary intact: dry-run engine, paper port.
        self.assertTrue(runtime.engine.dry_run)
        self.assertEqual(runtime.engine.executor.mode, "paper")
        # 9. zero live REST calls.
        self.assertEqual(http_calls, [])

        # Stash chain totals for the evidence report.
        TestRealtimePaperChain11C.chain_result = {
            "candles": 5000,
            "routed": engine.routed,
            "unrouted": engine.unrouted,
            "route_errors": engine.route_errors,
            "intents": len(placed),
            "fills": len(ledger),
            "starting_balance": starting,
            "final_balance": runtime.account.balance,
            "http_calls": len(http_calls),
        }


# ====================================================
# 11C-K -- event-loop responsiveness
# ====================================================


class TestEventLoopResponsiveness11C(unittest.TestCase):

    def test_poll_never_blocks_on_slow_provider(self):
        import time

        from core.universe.async_refresh_scheduler import (
            AsyncRefreshScheduler,
        )
        from core.universe.refresh_scheduler import RefreshScheduler

        provider_latency = 0.5

        class SlowManager:
            def refresh_discovery(self, **kwargs):
                time.sleep(provider_latency)
                return {}

            def build_universe(self, timeframe="1m"):
                class Universe:
                    def eligible_instruments(self):
                        return []

                return Universe()

        inner = RefreshScheduler(manager=SlowManager(), interval_seconds=0)
        wrapper = AsyncRefreshScheduler(inner)
        samples = []
        wrapper.run_if_due()
        for _ in range(50):
            tick = time.perf_counter()
            wrapper.run_if_due()
            samples.append((time.perf_counter() - tick) * 1000.0)
        deadline = time.time() + 8.0
        while wrapper.refresh_in_progress and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(wrapper.refresh_in_progress)
        # Poll latency (event loop) is orders of magnitude
        # below provider latency; reported SEPARATELY.
        TestEventLoopResponsiveness11C.loop_result = {
            "provider_latency_ms": provider_latency * 1000.0,
            "poll_p50_ms": percentile(samples, 50),
            "poll_p95_ms": percentile(samples, 95),
            "poll_max_ms": max(samples),
            "samples": len(samples),
        }
        self.assertLess(percentile(samples, 95), 50.0)

    def test_runtime_dispatch_latency_is_bounded(self):
        symbols = ["S{:02d}".format(i) for i in range(10)]
        manager, prod_client = build_manager(symbols)
        engine, transport, clock, _worlds = build_engine(
            symbols, universe_manager=manager
        )
        engine.started = True
        engine.refresh(client=prod_client)
        latencies = []
        base = 2_000_000_000
        for index in range(30):
            for symbol in symbols:
                candle = make_closed_candle(
                    base + index * 60, 100.0 + index, symbol
                )
                tick = time.perf_counter()
                transport.push(symbol, candle)
                latencies.append((time.perf_counter() - tick) * 1000.0)
        engine.subscriptions.poll()
        TestEventLoopResponsiveness11C.dispatch_result = {
            "dispatch_p50_ms": percentile(latencies, 50),
            "dispatch_p95_ms": percentile(latencies, 95),
            "dispatch_max_ms": max(latencies),
            "samples": len(latencies),
        }
        self.assertLess(percentile(latencies, 95), 50.0)
        engine.stop()


# ====================================================
# 11C-L -- multi-symbol operational soak
# ====================================================


def run_soak(n_symbols, n_candles=120):
    symbols = ["SYM{:03d}".format(i) for i in range(n_symbols)]
    liq = ScriptedLiquidity()
    hist = ScriptedHistory()
    manager, prod_client = build_manager(symbols, liq=liq, hist=hist)
    fire_map = {}
    for index, symbol in enumerate(symbols):
        if index % 3 == 0:
            fire_map[symbol] = (
                make_order(symbol, entry=100.0 + index, idx=index),
                5,
            )
    clock = FakeClock()
    transport = FakeTransport()
    engine, transport, clock, worlds = build_engine(
        symbols,
        fire_map=fire_map,
        clock=clock,
        transport=transport,
        universe_manager=manager,
    )
    threads_before = len(threading.enumerate())
    tick_start = time.perf_counter()
    # Offline refresh: the fake product catalog client keeps
    # the soak universe stable (a client-less refresh would
    # hit the real network and delist the soak instruments).
    engine.started = True
    engine.refresh(client=prod_client)
    latencies = []
    base = 2_100_000_000
    reconnected = []
    for index in range(n_candles):
        for symbol in symbols:
            candle = make_closed_candle(
                base + index * 60, 100.0 + (index % 7), symbol
            )
            tick = time.perf_counter()
            transport.push(symbol, candle)
            latencies.append((time.perf_counter() - tick) * 1000.0)
        if index == n_candles // 2:
            # Mid-run reconnect injection on two symbols.
            transport.down(symbols[0])
            transport.down(symbols[1])
            reconnected = list(symbols[:2])
            clock.advance(2.0)
            engine.subscriptions.poll()
        if index % 30 == 0:
            clock.advance(0.5)
            engine.subscriptions.poll()
    # Duplicate + forming + unknown-symbol injection.
    dup = make_closed_candle(base, 100.0, symbols[0])
    transport.push(symbols[0], dup)
    transport.push(symbols[0], dup)
    forming = make_closed_candle(base + n_candles * 60, 100.0, symbols[0],
                                 closed=False)
    transport.push(symbols[0], forming)
    engine._on_closed_candle(
        make_closed_candle(base, 100.0, "UNKNOWN-SYM")
    )
    clock.advance(2.0)
    engine.subscriptions.poll()
    duration = time.perf_counter() - tick_start

    states = engine.subscriptions.statuses()
    delivered = sum(s.delivered for s in states.values())
    duplicates = sum(s.duplicates for s in states.values())
    out_of_order = sum(s.out_of_order for s in states.values())
    forming_skipped = sum(s.forming_skipped for s in states.values())
    received = sum(s.received for s in states.values())
    reconnect_attempts = sum(s.reconnect_attempts for s in states.values())
    intents = sum(
        len(r.engine.placed) for r in engine.runtimes.values()
    )
    fills = sum(
        r.ledger.count() for r in engine.runtimes.values()
    )
    candles_seen = sum(
        w.on_candle_calls for w in worlds.values()
    )
    threads_after = len(threading.enumerate())
    status_names = sorted({s.status for s in states.values()})
    engine.stop()

    return {
        "symbols_requested": n_symbols,
        "symbols_accepted": len(engine.runtimes),
        "subscriptions_created": len(transport.subscribe_calls),
        "subscriptions_active": len(states),
        "statuses": status_names,
        "frames_received": received,
        "closed_candles": delivered,
        "candles_to_pipeline": candles_seen,
        "strategy_evaluations": candles_seen,
        "signals": intents,
        "risk_decisions": intents,
        "paper_orders": intents,
        "paper_fills": fills,
        "duplicate_frames": duplicates,
        "out_of_order_frames": out_of_order,
        "forming_skipped": forming_skipped,
        "malformed_frames": "NOT MEASURED",
        "stale_candles": "NOT MEASURED",
        "rejected_frames": duplicates + out_of_order,
        "subscription_failures": len(engine.subscriptions.errors),
        "reconnects": reconnected,
        "reconnect_attempts": reconnect_attempts,
        "subscribe_calls_symbol0": transport.subscribe_calls.get(
            symbols[0], 0
        ),
        "task_threads_before": threads_before,
        "task_threads_after": threads_after,
        "exceptions": (
            list(engine.subscriptions.errors)
            + ([engine.last_route_error] if engine.route_errors else [])
        ),
        "route_errors": engine.route_errors,
        "unrouted": engine.unrouted,
        "routed": engine.routed,
        "reconcile_errors": engine.reconcile_errors,
        "queue_depth": "NOT MEASURED",
        "dispatch_p50_ms": percentile(latencies, 50),
        "dispatch_p95_ms": percentile(latencies, 95),
        "dispatch_max_ms": max(latencies) if latencies else 0.0,
        "dispatch_samples": len(latencies),
        "provider_calls": liq.calls,
        "runtime_duration_s": duration,
    }


class TestMultiSymbolSoak11C(unittest.TestCase):

    def test_soak_10_symbols(self):
        result = run_soak(10)
        TestMultiSymbolSoak11C.soak_10 = result
        self.assertEqual(result["symbols_accepted"], 10)
        self.assertEqual(result["subscriptions_active"], 10)
        self.assertGreater(result["closed_candles"], 0)
        self.assertGreater(result["paper_fills"], 0)
        self.assertEqual(result["route_errors"], 0)
        self.assertEqual(result["reconcile_errors"], 0)
        # Reconnect recovered without duplicate workers.
        self.assertEqual(result["subscriptions_active"], 10)

    def test_soak_25_symbols(self):
        result = run_soak(25)
        TestMultiSymbolSoak11C.soak_25 = result
        self.assertEqual(result["symbols_accepted"], 25)
        self.assertEqual(result["subscriptions_active"], 25)
        self.assertGreater(result["closed_candles"], 0)
        self.assertGreater(result["paper_fills"], 0)
        self.assertEqual(result["route_errors"], 0)

    def test_soak_50_symbols(self):
        result = run_soak(50)
        TestMultiSymbolSoak11C.soak_50 = result
        self.assertEqual(result["symbols_accepted"], 50)
        self.assertEqual(result["subscriptions_active"], 50)
        self.assertGreater(result["closed_candles"], 0)
        self.assertGreater(result["paper_fills"], 0)
        self.assertEqual(result["route_errors"], 0)


# ====================================================
# 11C-M -- resource measurement
# ====================================================


class TestResourceMeasurement11C(unittest.TestCase):

    def test_soak_resource_envelope(self):
        import gc
        import tracemalloc

        gc.collect()
        tracemalloc.start()
        threads_initial = len(threading.enumerate())
        objects_initial = len(gc.get_objects())
        initial_current, _initial_peak = tracemalloc.get_traced_memory()

        result = run_soak(25, n_candles=60)

        gc.collect()
        final_current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        threads_final = len(threading.enumerate())
        objects_final = len(gc.get_objects())

        TestResourceMeasurement11C.resource_result = {
            "tracemalloc_initial_bytes": initial_current,
            "tracemalloc_peak_bytes": peak,
            "tracemalloc_final_bytes": final_current,
            "threads_initial": threads_initial,
            "threads_final": threads_final,
            "gc_objects_initial": objects_initial,
            "gc_objects_final": objects_final,
            "gc_objects_growth": objects_final - objects_initial,
            "process_rss": "NOT MEASURED",
            "cpu_utilization": "NOT MEASURED",
        }
        # No orphan threads from the soak.
        self.assertLessEqual(threads_final, threads_initial + 1)
        self.assertEqual(result["route_errors"], 0)


# ====================================================
# 11C-N -- restart / recovery
# ====================================================


class TestRestartRecovery11C(unittest.TestCase):

    def test_no_persistent_trading_state(self):
        """QuantEngine has NO durable runtime trading state
        (positions / ledgers / accounts persist nowhere):
        PERSISTENT STATE RECOVERY NOT IMPLEMENTED. Only the
        instrument CATALOG persists (registry JSON)."""
        from core.runtime.paper_runtime import PaperRuntime
        from core.runtime.realtime_engine import RealTimeEngine

        for cls in (PaperRuntime, RealTimeEngine):
            for method in ("save", "load", "restore", "snapshot",
                           "checkpoint", "persist"):
                self.assertFalse(
                    hasattr(cls, method),
                    msg="{}.{}".format(cls.__name__, method),
                )
        TestRestartRecovery11C.persistence = (
            "PERSISTENT STATE RECOVERY NOT IMPLEMENTED"
        )

    def test_catalog_persistence_round_trip(self):
        import tempfile
        from pathlib import Path

        from core.registry.instrument_registry import InstrumentRegistry

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            registry = InstrumentRegistry(path=path)
            manager, _client = build_manager(("AAA", "BBB"))
            for inst in manager.registry.all():
                registry.upsert(inst)
            registry.save()
            restored = InstrumentRegistry(path=path)
            self.assertEqual(len(restored), len(registry))
            TestRestartRecovery11C.catalog = {
                "saved": len(registry),
                "restored": len(restored),
            }

    def test_clean_restart_rebuilds_state(self):
        symbols = ["R{:02d}".format(i) for i in range(5)]
        manager, prod_client = build_manager(symbols)
        clock = FakeClock()
        transport = FakeTransport()
        engine, transport, clock, _worlds = build_engine(
            symbols, clock=clock, transport=transport,
            universe_manager=manager,
        )
        engine.started = True
        engine.refresh(client=prod_client)
        base = 2_200_000_000
        for index in range(10):
            for symbol in symbols:
                transport.push(
                    symbol,
                    make_closed_candle(base + index * 60, 100.0, symbol),
                )
        before = {
            key: rt.processed_bars
            for key, rt in engine.runtimes.items()
        }
        self.assertTrue(all(v == 10 for v in before.values()))
        engine.stop()
        self.assertTrue(transport.closed)

        # Restart from clean state: new engine, new transport.
        clock2 = FakeClock()
        transport2 = FakeTransport()
        engine2, _t, _c, _w = build_engine(
            symbols, clock=clock2, transport=transport2,
            universe_manager=manager,
        )
        engine2.started = True
        engine2.refresh(client=prod_client)
        for index in range(10, 15):
            for symbol in symbols:
                transport2.push(
                    symbol,
                    make_closed_candle(base + index * 60, 101.0, symbol),
                )
        engine2.subscriptions.poll()
        after = {
            key: rt.processed_bars
            for key, rt in engine2.runtimes.items()
        }
        # Fresh ledgers, rebuilt pipelines, safe continuation.
        self.assertTrue(all(v == 5 for v in after.values()))
        self.assertEqual(
            sum(r.ledger.count() for r in engine2.runtimes.values()), 0
        )
        engine2.stop()
        TestRestartRecovery11C.restart = {
            "bars_before_restart": before,
            "bars_after_restart": after,
        }


# ====================================================
# 11C-U -- deterministic Gate A (two clean processes)
# ====================================================


class TestGateADeterminism11C(unittest.TestCase):

    def test_gate_a_identical_across_processes(self):
        import os
        import subprocess
        import sys

        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        script = os.path.join(root, "scripts", "verify_gate_a.py")
        env = dict(os.environ)
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")

        def summary_of(output):
            for line in output.splitlines():
                if "orders " in line and "fills " in line:
                    return line.strip()
            return ""

        summaries = []
        passed = []
        for _ in range(2):
            proc = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                env=env,
                cwd=root,
                timeout=600,
            )
            self.assertEqual(proc.returncode, 0)
            summaries.append(summary_of(proc.stdout))
            passed.append("[PASS] GATE A PASSED" in proc.stdout)
        self.assertTrue(all(passed))
        self.assertEqual(summaries[0], summaries[1])
        # Gate-A economics (frozen-snapshot replay, zero-cost
        # defaults) under the ACTIVE minimum-R policy: 5 orders /
        # 2 fills / 1W / 1L (verified deterministic, Phase 106).
        # History (preserved, not reverted): 25 / 2 / 0W / 2L was
        # the pre-dedup baseline; economic-dedup + re-entry
        # cooldowns collapsed it to 4 / 1; the directed 6R-floor
        # removal (active policy governs) admits one more erosion
        # fill at actual RR in [1,6) -> 5 / 2. Determinism across
        # processes is the actual subject of this test; the
        # economics pin below keeps the new baseline honest.
        self.assertIn("orders 5", summaries[0])
        self.assertIn("fills 2", summaries[0])
        TestGateADeterminism11C.gate_a = {"summaries": summaries}


if __name__ == "__main__":
    unittest.main()
