"""
====================================================

QuantEngine

Runtime Integration Tests

Phase 6E -- Real-time integration (paper mode only).

End-to-end wiring of the 6E orchestrator:

    (6B universe refresh)
        -> PipelineRegistry reconcile (ADD / RETAIN / RETIRE)
        -> (6D subscription manager) sync
        -> closed-candle delivery
            -> identity-key candle routing
            -> PaperRuntime (frozen SymbolPipeline +
               BrokerEngine dry-run + TradeRegistry ledger)

Users' required coverage:

    1. universe -> subscription -> pipeline (a BTC closed
       candle flows to the BTC runtime only)
    2. dynamic change, pass1 BTC+ETH -> pass2 BTC+SOL:
       BTC RETAINED (same object), ETH RETIRED cleanly,
       SOL ADDED -- never a rebuild on refresh
    3. candle routing isolation: BTC candles can never
       mutate the ETH pipeline (identity routing, not
       position / subscription order)
    4. duplicate protection end-to-end, including the
       reconnect boundary: replay after reconnect is NOT
       delivered twice; the post-entropy closed candle is
       processed exactly once
    5. deterministic paper execution: known setup -> paper
       fill -> target / stop -> trade, with canonical_id
       preserved, entry model preserved, PnL recorded

Paper-only: BrokerEngines all run dry_run=True through a
PaperExecutionAdapter whose live-only ops raise
PaperOnlyError. Zero exchange writes.
====================================================
"""

import unittest

from config import risk_settings

from core.runtime import (
    PaperOnlyError,
    RealTimeEngine,
)
from core.runtime.pipeline_registry import instrument_identity_key
from core.risk.order_intent import OrderIntent
from core.universe.market_universe import Instrument

from core.backtesting.trade import Trade


# ====================================================
# Fixtures
# ====================================================


def make_inst(
    symbol,
    instrument_id,
    exchange="delta",
):
    """Eligible instrument record (identity-carrying)."""

    return Instrument(
        instrument_id=instrument_id,
        symbol=symbol,
        exchange=exchange,
        trading_enabled=True,
    )


def make_candle(timestamp, close, high=None, low=None, symbol="BTC",
                open_=None, closed=True):
    """Closed candle tagged with the owning symbol (the 6D
    delivery contract)."""

    from core.history.candle import Candle

    return Candle(
        timestamp=timestamp,
        open=(open_ if open_ is not None else close),
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


class FakeUniverse:
    """MarketUniverse-compatible eligible cut."""

    def __init__(self, instruments):

        self.instruments = list(instruments)
        self.captured_at = 0.0
        self.timeframe = "1m"

    def eligible_instruments(self):

        return list(self.instruments)

    @property
    def symbols(self):

        return tuple(i.symbol for i in self.instruments)


class SnapshotManager:
    """Fake 6B UniverseManager: discovery is a no-op, the
    universe is whatever the test set last."""

    def __init__(self, instruments):

        self.instruments = list(instruments)
        self.discovery_attempts = 0

    def refresh_discovery(self, client=None, normalizer=None):

        self.discovery_attempts += 1

        return {"instruments": len(self.instruments)}

    def build_universe(self, timeframe="1m"):

        return FakeUniverse(self.instruments)


class FakeTransport:
    """One multiplexed connection carrying per-symbol routes.
    push/down target a single route so one symbol can never leak
    into another (mirrors the 6D contract)."""

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
    """A world-compatible unit (the pipeline-compatible object
    contract BrokerEngine consumes: .context / .on_candle /
    .reset). Behaves like the institutional world's per-candle
    flow but emits ONE deterministic OrderIntent on a chosen
    candle, so the 6E chain is testable without re-implementing
    the four-engine strategy."""

    def __init__(self, context):

        self.context = context

        self.on_candle_calls = 0

        self.candles_seen = []

        self.order_plan = None  # (fire_candle_index, OrderIntent)

        self.fired = False

    def plan(self, order, fire_candle_index):

        self.order_plan = (fire_candle_index, order)

    def reset(self):

        self.on_candle_calls = 0
        self.candles_seen = []
        self.fired = False

    def on_candle(self, event):

        self.on_candle_calls += 1

        candle = event.candle

        self.candles_seen.append(candle)

        # Window accumulation, exactly like the institutional world.
        self.context.add_candle(candle)

        if self.order_plan is None or self.fired:

            return

        fire_index, order = self.order_plan

        if self.on_candle_calls != fire_index:

            return

        # Register the PENDING order (the registry mints the
        # order_id) then publish it as the RiskEngine decision.
        registered, _ = self.context.order_registry.create(order)

        self.context.order = registered
        self.context.execution_signal = registered

        self.fired = True


def make_order(
    canonical_id,
    setup_id="S-1",
    entry=100.00,
    stop_loss=90.00,
    take_profit=110.00,
    quantity=1.0,
    direction="BULLISH",
    symbol="BTC",
    timeframe="1m",
    commission=0.0,
    slippage=0.0,
):

    return OrderIntent(
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=(take_profit - entry) / max(entry - stop_loss, 1e-9),
        quantity=quantity,
        risk_percent=1.0,
        risk_amount=abs(entry - stop_loss) * quantity,
        expected_loss=abs(entry - stop_loss) * quantity,
        expected_profit=abs(take_profit - entry) * quantity,
        position_value=entry * quantity,
        leverage=1.0,
        commission=commission,
        slippage=slippage,
        confidence=0.8,
        score=90.0,
        symbol=symbol,
        timeframe=timeframe,
        setup_id=setup_id,
        entry_mode=risk_settings.ENTRY_MODE,
        canonical_id=canonical_id,
        status="NEW",
        valid=True,
    )


def build_engine(
    instruments,
    worlds=None,
    refresh_interval_seconds=0,
):
    """Wire a fully offline RealTimeEngine over a snapshot
    universe and the FakeTransport."""

    clock = FakeClock(now=1000.0)

    universe_manager = SnapshotManager(instruments)

    transport = FakeTransport()

    worlds = worlds or {}

    def world_factory(context):
        config = worlds.get(context.market.symbol)
        if config is None:
            return ScriptedWorld(context)
        if callable(config):
            return config(context)
        return config(context)

    engine = RealTimeEngine(
        universe_manager=universe_manager,
        world_factory=world_factory,
        transport_factory=lambda: transport,
        clock=clock,
        timeframe="1m",
        refresh_interval_seconds=refresh_interval_seconds,
    )

    engine.start()

    return {
        "engine": engine,
        "clock": clock,
        "universe_manager": universe_manager,
        "transport": transport,
    }


# ====================================================
# 1. Universe -> subscription -> pipeline
# ====================================================

class TestUniverseToSubscriptionToPipeline(unittest.TestCase):

    def test_btc_flows_eligible_to_subscription_to_pipeline(self):

        btc = make_inst("BTC", "27")

        hub = build_engine([btc], worlds={})
        engine = hub["engine"]
        transport = hub["transport"]

        key = instrument_identity_key("delta", "27")

        # Universe -> subscription
        self.assertEqual(engine.registry.keys, (key,))
        self.assertEqual(engine.subscriptions.symbols, ("BTC",))
        self.assertEqual(transport.subscribe_calls.get("BTC"), 1)
        self.assertEqual(engine.runtimes[key].symbol, "BTC")

        runtime = engine.runtimes[key]

        # Delivery -> pipeline
        c10 = make_candle(10, 100.0, symbol="BTC")
        transport.push("BTC", c10)

        self.assertEqual(engine.routed, 1)
        self.assertEqual(runtime.processed_bars, 1)

        world = runtime.pipeline.world

        self.assertEqual(len(world.candles_seen), 1)
        self.assertEqual(world.candles_seen[0].timestamp, 10)

        # Forming candles are never delivered to the pipeline.
        transport.push("BTC", make_candle(11, 101.0, symbol="BTC",
                                          closed=False))

        self.assertEqual(engine.routed, 1)
        self.assertEqual(runtime.processed_bars, 1)

        # A delivered symbol the universe no longer knows is
        # unrouted, never crashes the loop.
        engine._on_closed_candle(
            make_candle(12, 1.0, symbol="DOGE")
        )

        self.assertEqual(engine.unrouted, 1)

        # statuses merge the runtime + 6D subscription state
        status = engine.statuses()["BTC"]

        self.assertEqual(status["subscription_status"].status, "LIVE")
        self.assertEqual(status["symbol"], "BTC")
        self.assertEqual(status["processed_bars"], 1)

        engine.stop()

        self.assertTrue(transport.closed)


# ====================================================
# 2. Dynamic universe: pass1 BTC+ETH -> pass2 BTC+SOL
# ====================================================

class TestDynamicUniverseRetainRetireCreate(unittest.TestCase):

    def test_btc_retained_eth_retired_sol_created(self):

        btc = make_inst("BTC", "27")
        eth = make_inst("ETH", "31")
        sol = make_inst("SOL", "58")

        hub = build_engine([btc, eth], worlds={})
        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("delta", "27")
        key_eth = instrument_identity_key("delta", "31")
        key_sol = instrument_identity_key("delta", "58")

        # pass 1: both live and subscribed

        self.assertEqual(
            sorted(engine.registry.keys),
            sorted((key_btc, key_eth)),
        )
        self.assertEqual(
            engine.subscriptions.symbols, ("BTC", "ETH")
        )

        btc_runtime = engine.runtimes[key_btc]
        eth_runtime = engine.runtimes[key_eth]

        btc_c10 = make_candle(10, 100.0, symbol="BTC")
        transport.push("BTC", btc_c10)

        self.assertEqual(btc_runtime.processed_bars, 1)
        self.assertEqual(eth_runtime.processed_bars, 0)

        # pass 2: universe drops ETH, adds SOL

        hub["universe_manager"].instruments = [btc, sol]

        engine.poll()  # interval 0 -> refresh due every pass

        # BTC retained as the SAME object (no rebuild)
        self.assertIs(engine.runtimes[key_btc], btc_runtime)
        self.assertIn(key_btc, engine.registry.pipelines)

        # ETH retired: dropped from active, pipeline moved to the
        # retired snapshot, subscription removed.
        self.assertNotIn(key_eth, engine.runtimes)
        self.assertNotIn(key_eth, engine.registry.pipelines)
        self.assertIn(key_eth, engine.registry.retired_pipelines)
        self.assertTrue(eth_runtime.retired)
        self.assertIn("ETH", transport.unsubscribed)

        # SOL created fresh and subscribed.
        self.assertIn(key_sol, engine.runtimes)
        self.assertIsNot(engine.runtimes[key_sol], btc_runtime)
        self.assertEqual(transport.subscribe_calls.get("SOL"), 1)

        # ETH subscription is gone: an ETH candle goes nowhere.
        self.assertEqual(engine.subscriptions.symbols, ("BTC", "SOL"))

        # BTC keeps flowing to the same runtime.
        transport.push("BTC", make_candle(11, 101.0, symbol="BTC"))
        self.assertEqual(btc_runtime.processed_bars, 2)

        # the retired ledger stays readable for analytics
        self.assertIn(key_eth, engine.registry.retired_pipelines)
        self.assertEqual(
            engine.registry.retired_pipelines[key_eth].instrument.symbol,
            "ETH",
        )


# ====================================================
# 3. Candle routing isolation
# ====================================================

class TestRoutingIsolation(unittest.TestCase):

    def test_btc_candle_never_mutates_eth_pipeline(self):

        btc = make_inst("BTC", "27")
        eth = make_inst("ETH", "31")

        hub = build_engine([btc, eth], worlds={})
        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("delta", "27")
        key_eth = instrument_identity_key("delta", "31")

        btc_runtime = engine.runtimes[key_btc]
        eth_runtime = engine.runtimes[key_eth]

        btc_world = btc_runtime.pipeline.world
        eth_world = eth_runtime.pipeline.world

        # BTC candle -> BTC SSE pipeline only.
        transport.push(
            "BTC", make_candle(10, 100.0, symbol="BTC")
        )

        self.assertEqual(len(btc_world.candles_seen), 1)
        self.assertEqual(len(eth_world.candles_seen), 0)
        self.assertEqual(eth_runtime.processed_bars, 0)

        # ETH candle -> ETH only; BTC state untouched.
        transport.push(
            "ETH", make_candle(10, 2000.0, symbol="ETH")
        )

        self.assertEqual(len(btc_world.candles_seen), 1)
        self.assertEqual(len(eth_world.candles_seen), 1)
        self.assertEqual(btc_runtime.processed_bars, 1)
        self.assertEqual(eth_runtime.processed_bars, 1)

        # Cross-symbol candles are never routed by position order:
        # both pipelines stay flat, no cross delivery.
        self.assertIsNone(btc_runtime.current_trade)
        self.assertIsNone(eth_runtime.current_trade)

        # the BTC market state timestamp was not touched by ETH
        btc_market = btc_world.context.market
        self.assertEqual(btc_market.symbol, "BTC")
        self.assertEqual(btc_market.timestamp, 10)

        eth_market = eth_world.context.market
        self.assertEqual(eth_market.symbol, "ETH")
        self.assertEqual(eth_market.timestamp, 10)


# ====================================================
# 4. Duplicate protection end-to-end (incl. reconnect)
# ====================================================

class TestDuplicateProtectionEndToEnd(unittest.TestCase):

    def test_replay_and_reconnect_never_double_deliver(self):

        btc = make_inst("BTC", "27")

        hub = build_engine([btc], worlds={})
        engine = hub["engine"]
        transport = hub["transport"]
        clock = hub["clock"]

        key_btc = instrument_identity_key("delta", "27")
        runtime = engine.runtimes[key_btc]
        world = runtime.pipeline.world

        # First closed candle delivered exactly once.
        transport.push("BTC", make_candle(100, 100.0, symbol="BTC"))

        self.assertEqual(engine.routed, 1)
        self.assertEqual(len(world.candles_seen), 1)

        # Same-pass replay dropped.
        transport.push("BTC", make_candle(100, 100.0, symbol="BTC"))

        self.assertEqual(engine.routed, 1)
        self.assertEqual(len(world.candles_seen), 1)

        # --- reconnect boundary ----
        transport.down("BTC")  # worker -> RECONNECTING

        self.assertEqual(
            runtime.state()["open_position"], False
        )

        clock.advance(120.0)
        engine.poll()  # reconnect attempt re-subscribes

        self.assertEqual(transport.subscribe_calls.get("BTC"), 2)

        # Replay of the pre-reconnect closed candle is STILL deduped.
        transport.push("BTC", make_candle(100, 100.0, symbol="BTC"))

        self.assertEqual(engine.routed, 1)
        self.assertEqual(len(world.candles_seen), 1)

        # Post-entropy new closed candle delivered exactly once.
        transport.push("BTC", make_candle(101, 101.0, symbol="BTC"))

        self.assertEqual(engine.routed, 2)
        self.assertEqual(
            [c.timestamp for c in world.candles_seen], [100, 101]
        )

        # Forming replay after reconnect never reaches the pipeline.
        transport.push("BTC", make_candle(100, 100.0, symbol="BTC",
                                          closed=False))

        self.assertEqual(engine.routed, 2)
        self.assertEqual(len(world.candles_seen), 2)


# ====================================================
# 5. Deterministic paper execution (canonical identity)
# ====================================================

class TestDeterministicPaperExecution(unittest.TestCase):

    CANONICAL = (
        "delta:27:1m:BULLISH:BREAKOUT_CONTINUATION:OB-1042"
    )

    def _world(self, context):

        world = ScriptedWorld(context)

        # Phase-15 maintenance: gate-compliant economics
        # ((170-100)/10 = RR 7.0 >= 6, zero costs so the post-cost
        # layer is vacuous), because BrokerEngine._route now
        # enforces the mandatory gates. Identity-chain intent
        # unchanged.
        order = make_order(
            canonical_id=self.CANONICAL,
            setup_id="S-DETERMINISTIC",
            entry=100.00,
            stop_loss=90.00,
            take_profit=170.00,
            quantity=1.0,
            direction="BULLISH",
            symbol="BTC",
            timeframe="1m",
        )

        world.plan(order, fire_candle_index=2)

        return world

    def test_target_win_full_identity_chain(self):

        btc = make_inst("BTC", "27")

        hub = build_engine([btc], worlds={"BTC": self._world})
        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("delta", "27")
        runtime = engine.runtimes[key_btc]

        # candle 1: window seed, no order.
        transport.push("BTC", make_candle(10, 100.0, symbol="BTC"))

        # candle 2: deterministic trigger -> paper order ->
        #           routed -> PENDING -> FILLED (paper fill).
        transport.push("BTC", make_candle(20, 101.0, symbol="BTC"))

        order = engine.runtimes[key_btc].pipeline.world.context.order

        self.assertEqual(runtime.processed_bars, 2)

        # PAPER_ORDER_CREATED audit: the would-be intent is on
        # the engine's placed trail (PENDING is the registry state
        # between create and mark_filled).
        self.assertEqual(len(runtime.executed_intents), 1)
        self.assertIs(runtime.executed_intents[0], order)

        registry = runtime.pipeline.world.context.order_registry

        self.assertEqual(registry.get(order.order_id).status, "FILLED")

        # OPEN_POSITION: the paper position is live.
        self.assertIsNotNone(runtime.current_trade)
        self.assertEqual(runtime.current_trade.direction, "BULLISH")

        # candle 3: target hit at 170 -> CLOSED WIN.
        transport.push("BTC", make_candle(30, 110.0, high=172.0,
                                          low=99.0, symbol="BTC"))

        closed = runtime.ledger.all()

        self.assertEqual(len(closed), 1)
        self.assertIsNone(runtime.current_trade)

        trade = closed[0]

        self.assertIsInstance(trade, Trade)
        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.result, "WIN")

        # P&P: canonical identity survives to the PAPER ledger.
        self.assertEqual(trade.canonical_id, self.CANONICAL)
        self.assertEqual(trade.setup_id, "S-DETERMINISTIC")
        self.assertEqual(trade.direction, "BULLISH")

        # entry model preserved (paper fill at the order entry,
        # not the next close).
        self.assertIsInstance(trade.entry, float)
        self.assertAlmostEqual(trade.entry, 100.00, places=6)
        self.assertEqual(
            trade.entry_mode, risk_settings.ENTRY_MODE
        )

        # PnL recorded: (170 - 100) * 1.0, zero costs.
        self.assertAlmostEqual(trade.pnl, 70.0, places=6)

        # account booked the realized gain.
        self.assertAlmostEqual(runtime.account.balance, 2070.0, places=6)

        # registry lifecycle: order FILLED with the closed
        # trade attached.
        order_id = order.order_id
        filled = registry.get(order_id)
        self.assertEqual(filled.status, "FILLED")
        self.assertEqual(filled.trade_id, trade.trade_id)

        # flat ledger + aggregation view
        self.assertEqual(len(engine.all_trades()), 1)
        self.assertEqual(engine.all_trades()[0].canonical_id,
                         self.CANONICAL)

        # paper-only guarantee: live ops on the execution port
        # are refused.
        self.assertEqual(runtime.port.mode, "paper")
        self.assertTrue(runtime.engine.dry_run)

        with self.assertRaises(PaperOnlyError):
            runtime.port.balance()

        with self.assertRaises(PaperOnlyError):
            runtime.port.positions()

        with self.assertRaises(PaperOnlyError):
            runtime.port.cancel("x")

    def test_stop_loss_defensive_exit_books_loss(self):

        btc = make_inst("BTC", "27")

        def world_factory(context):
            world = ScriptedWorld(context)
            world.plan(
                make_order(
                    canonical_id=(
                        "delta:27:1m:BULLISH:BREAKOUT_CONTINUATION:"
                        "OB-STOP"
                    ),
                    setup_id="S-STOP",
                    entry=100.00,
                    stop_loss=90.00,
                    take_profit=170.00,
                    quantity=1.0,
                    direction="BULLISH",
                ),
                fire_candle_index=1,
            )
            return world

        hub = build_engine([btc], worlds={"BTC": world_factory})
        engine = hub["engine"]
        transport = hub["transport"]

        key_btc = instrument_identity_key("delta", "27")
        runtime = engine.runtimes[key_btc]

        transport.push("BTC", make_candle(10, 100.0, symbol="BTC"))

        # candle 2 breaks the stop (low 85 <= 90).
        transport.push("BTC", make_candle(20, 92.0, high=93.0,
                                          low=85.0, symbol="BTC"))

        self.assertEqual(len(runtime.ledger.all()), 1)

        trade = runtime.ledger.all()[0]

        self.assertEqual(trade.result, "LOSS")
        self.assertAlmostEqual(trade.pnl, -10.0, places=6)
        self.assertEqual(
            trade.canonical_id,
            "delta:27:1m:BULLISH:BREAKOUT_CONTINUATION:OB-STOP",
        )

        # account bleeds down, never below the paper floor.
        self.assertAlmostEqual(runtime.account.balance, 1990.0, places=6)


if __name__ == "__main__":

    unittest.main()