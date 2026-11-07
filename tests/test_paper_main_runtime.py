"""
====================================================

QuantEngine

Paper Main Runtime Tests (Phase 9P-a)

Offline verification of the CANONICAL PAPER startup bridge
(core/runtime/paper_main.py + main.py) wiring the Phase 6E
RealTimeEngine runtime:

    build_paper_engine(universe_manager, transport_factory,
                       world_factory, clock, ...)
        -> RealTimeEngine (refresh -> reconcile -> sync ->
            identity-key closed-candle routing -> PaperRuntime)

Coverage required:

  1. build_paper_engine assembles a fully-wired multi-symbol
     RealTimeEngine in PAPER mode -- no network, no threads --
     from injectable collaborators (mirrors main.py's default
     call with the production defaults swapped for offline
     dummies).
  2. an explicit-symbol universe (BTC + ETH) routes ONE
     closed candle to the BTC pipeline ONLY -- identity
     routing; ETH stays untouched.
  3. a forming candle never reaches either pipeline.
  4. a candle for a symbol the universe does not know is
     unrouted, never crashes the loop.
  5. the engine is paper-only: dry_run=True, PaperOnlyError on
     live port ops.
  6. tick() drives one poll step without blocking.

No network, no threads, no caches.
====================================================
"""

import unittest

from config import risk_settings

from core.runtime.paper_main import (
    ExplicitSymbolUniverseManager,
    build_paper_engine,
    tick,
)
from core.runtime.pipeline_registry import instrument_identity_key


def make_candle(timestamp, close, symbol="BTC", closed=True,
                high=None, low=None):
    """Closed/forming candle tagged with the owning symbol (the
    6D delivery contract)."""

    from core.history.candle import Candle

    return Candle(
        timestamp=timestamp,
        open=close,
        high=(high if high is not None else close),
        low=(low if low is not None else close),
        close=close,
        volume=100.0,
        closed=closed,
        symbol=symbol,
    )


class FakeClock:

    def __init__(self, now=0.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class FakeTransport:
    """One multiplexed connection carrying per-symbol routes.
    push/down target a single route (mirrors the 6D contract)."""

    def __init__(self):
        self._routes = {}
        self.subscribe_calls = {}
        self.unsubscribed = []
        self.closed = False

    def subscribe(self, symbol, on_candle, on_down):
        self.subscribe_calls[symbol] = (
            self.subscribe_calls.get(symbol, 0) + 1
        )
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
            route[1]()

    def close(self):
        self.closed = True
        self._routes.clear()


class ScriptedWorld:
    """A world-compatible unit (.context / .on_candle / .reset)
    that just records candles -- proves delivery routing without
    re-implementing the four-engine strategy."""

    def __init__(self, context):
        self.context = context
        self.candles_seen = []

    def reset(self):
        self.candles_seen = []

    def on_candle(self, event):
        self.candles_seen.append(event.candle)
        self.context.add_candle(event.candle)


def build(
    symbols,
    worlds=None,
    refresh_interval_seconds=0,
):
    """Assemble the paper-main engine over a fake snapshot
    universe + fake transport + scripted worlds (the offline
    stand-in for main.py's default build_paper_engine())."""

    clock = FakeClock(now=1000.0)

    manager = ExplicitSymbolUniverseManager(
        symbols=symbols,
        timeframe="1m",
    )

    transport = FakeTransport()

    worlds = worlds or {}

    def world_factory(context):
        maker = worlds.get(context.market.symbol)
        if maker is None:
            return ScriptedWorld(context)
        return maker(context)

    engine, manager_out = build_paper_engine(
        universe_manager=manager,
        transport_factory=lambda: transport,
        world_factory=world_factory,
        clock=clock,
        timeframe="1m",
        refresh_interval_seconds=refresh_interval_seconds,
    )

    engine.start()

    return {
        "engine": engine,
        "clock": clock,
        "universe_manager": manager_out,
        "transport": transport,
    }


class TestExplicitSymbolUniverseManager(unittest.TestCase):

    def test_explicit_cut_is_eligible(self):
        manager = ExplicitSymbolUniverseManager(symbols=["BTC", "ETH"])

        self.assertEqual(manager.discovery_attempts, 0)

        summary = manager.refresh_discovery()

        self.assertEqual(summary["instruments"], 2)
        self.assertEqual(manager.discovery_attempts, 1)

        universe = manager.build_universe(timeframe="1m")

        self.assertEqual(universe.symbols, ("BTC", "ETH"))

        for inst in universe.eligible_instruments():
            self.assertEqual(inst.state, "ELIGIBLE")
            self.assertTrue(inst.valid)
            self.assertTrue(inst.valid_precision)

    def test_blank_symbols_filtered(self):
        manager = ExplicitSymbolUniverseManager(
            symbols=["BTC", "  ", None, "ETH"],
        )
        self.assertEqual(manager.build_universe().symbols, ("BTC", "ETH"))


class TestPaperMainBuild(unittest.TestCase):

    def test_assembles_multi_symbol_engine(self):
        hub = build(["BTC", "ETH"])

        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("DELTA", "BTC")
        key_eth = instrument_identity_key("DELTA", "ETH")

        # universe -> subscription -> pipeline (all three present)
        self.assertEqual(
            sorted(engine.registry.keys),
            sorted((key_btc, key_eth)),
        )
        self.assertEqual(engine.subscriptions.symbols, ("BTC", "ETH"))
        self.assertEqual(transport.subscribe_calls.get("BTC"), 1)
        self.assertEqual(transport.subscribe_calls.get("ETH"), 1)

        # paper-only: dry run through the PaperExecutionAdapter
        runtime_btc = engine.runtimes[key_btc]
        self.assertTrue(runtime_btc.engine.dry_run)
        self.assertEqual(runtime_btc.port.mode, "paper")

        engine.stop()
        self.assertTrue(transport.closed)

    def test_identity_routing_isolates_symbols(self):
        hub = build(["BTC", "ETH"])

        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("DELTA", "BTC")
        key_eth = instrument_identity_key("DELTA", "ETH")

        btc_world = engine.runtimes[key_btc].pipeline.world
        eth_world = engine.runtimes[key_eth].pipeline.world

        transport.push("BTC", make_candle(10, 100.0, symbol="BTC"))

        self.assertEqual(engine.routed, 1)
        self.assertEqual(len(btc_world.candles_seen), 1)
        self.assertEqual(len(eth_world.candles_seen), 0)

        transport.push("ETH", make_candle(10, 2000.0, symbol="ETH"))

        self.assertEqual(engine.routed, 2)
        self.assertEqual(len(btc_world.candles_seen), 1)
        self.assertEqual(len(eth_world.candles_seen), 1)

        # cross-symbol candles never mutate the neighbouring pipeline
        self.assertEqual(btc_world.context.market.symbol, "BTC")
        self.assertEqual(eth_world.context.market.symbol, "ETH")

        engine.stop()

    def test_forming_candle_never_reaches_pipeline(self):
        hub = build(["BTC"])

        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("DELTA", "BTC")
        runtime = engine.runtimes[key_btc]
        world = runtime.pipeline.world

        transport.push("BTC", make_candle(10, 100.0, symbol="BTC"))
        transport.push(
            "BTC", make_candle(11, 101.0, symbol="BTC", closed=False)
        )

        self.assertEqual(engine.routed, 1)
        self.assertEqual(runtime.processed_bars, 1)
        self.assertEqual(len(world.candles_seen), 1)

        engine.stop()

    def test_unknown_symbol_unrouted_never_crashes(self):
        hub = build(["BTC"])

        engine = hub["engine"]

        engine._on_closed_candle(make_candle(12, 1.0, symbol="DOGE"))

        self.assertEqual(engine.unrouted, 1)

        engine.stop()

    def test_tick_drives_one_poll_step(self):
        clock = FakeClock(now=0.0)

        manager = ExplicitSymbolUniverseManager(symbols=["BTC"])

        transport = FakeTransport()

        engine, _ = build_paper_engine(
            universe_manager=manager,
            transport_factory=lambda: transport,
            world_factory=ScriptedWorld,
            clock=clock,
            timeframe="1m",
            refresh_interval_seconds=0,
        )

        tick(engine)

        key_btc = instrument_identity_key("DELTA", "BTC")
        self.assertIn(key_btc, engine.registry.pipelines)

        engine.stop()


class TestPaperMainPaperOnlyBoundary(unittest.TestCase):

    def test_live_port_ops_refused(self):
        hub = build(["BTC"])

        engine = hub["engine"]

        key_btc = instrument_identity_key("DELTA", "BTC")
        port = engine.runtimes[key_btc].port

        from core.runtime import PaperOnlyError

        with self.assertRaises(PaperOnlyError):
            port.balance()

        with self.assertRaises(PaperOnlyError):
            port.positions()

        with self.assertRaises(PaperOnlyError):
            port.cancel("x")

        engine.stop()


if __name__ == "__main__":

    unittest.main()
