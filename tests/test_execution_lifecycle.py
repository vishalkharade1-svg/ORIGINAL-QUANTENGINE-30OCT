"""
====================================================

QuantEngine

Phase 4C: Execution Lifecycle Invariance Tests

Run with:

    python -m unittest tests.test_execution_lifecycle -v

Proves the canonical invariant end-to-end:

    ONE SETUP ID == ONE PRIMARY ORDER == ONE TRADE

    1. OrderRegistry blocks duplicates by setup_id.
    2. ExecutionEngine is idempotent -- re-processing the same
       accepted setup produces no second signal.
    3. RiskEngine creates the order exactly once; a second pass
       on the same setup is a no-op.
    4. The pipeline deduplicates engine registration by name,
       so a double register(ExecutionEngine()) can never run the
       stage twice (the duplicate EXECUTION SIGNAL root cause).
5. Execution event counts: SETUP_ACCEPTED / ORDER_CREATED /
        EXECUTION_SIGNAL / ORDER_FILLED / TRADE_CLOSED each fire
        at most once per setup across a multi-candle run.
     6. The backtester fills a pending order exactly once, only
        when a candle trades through its entry
        (low <= entry <= high, inclusive), and on the first such
        candle even if it comes later -- a stale order that never
        gets its touch EXPIRES after MAX_WAIT_BARS and can never
        fill, nor can a FILLED or terminal order fill twice.
     7. The full identity chain flows setup_id -> order_id ->
        trade_id onto the booked Trade.

     Phase 4D (Pending Order Fill / Invalidation / Expiration
     Integrity) re-proves the lifecycle on bar-anchored metadata:

     8. No same-candle look-ahead: an order created on bar N is
        eligible from bar N + ENTRY_DELAY_BARS (default 1) only.
     9. Bar metadata is stamped at creation: created_bar,
        created_timestamp, eligible_from_bar, expires_at_bar.
    10. Expiry is bar-anchored at the END of a candle whose bar >=
        expires_at_bar -- never on the creation bar, and only AFTER
        that candle's fill/invalidation check (the expiry candle
        is still the fill's last chance).
    11. The structural stop breach is classified as ORDER_INVALIDATED
        (bullish: candle.low <= stop_loss; bearish: candle.high >=
        stop_loss), never as an expiration; on a candle that both
        breaks the stop and reaches the entry, invalidation wins.
    12. ORDER_FILLED / ORDER_EXPIRED logs carry the full bar
        diagnostics (created / eligible / filled / expired /
        waited bars, entry, candle range, price extremes since
        creation).
    13. Multiple valid pending orders coexist under
        MAX_PENDING_ORDERS (with duplicate-setup prevention and the
        exposure ceiling), one fill per candle (single position).

Stdlib only -- no network.

====================================================
"""

import logging
import unittest
from unittest import mock

from config import risk_settings

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.execution.execution_engine import ExecutionEngine
from core.risk.risk_engine import RiskEngine
from core.execution.order_registry import OrderRegistry, PENDING, FILLED
from core.execution.entry_mode import ENTRY_MODE_LIMIT_RETEST

from core.order_blocks.order_block import OrderBlock
from core.order_blocks.order_block_registry import OrderBlockRegistry

from core.fvg.fvg_registry import FVGRegistry

from core.liquidity.liquidity_target import LiquidityTarget

from core.trend.trend_state import TrendState
from core.regime.regime_state import RegimeState

from core.risk.account_state import AccountState
from core.events.candle_event import CandleEvent

from core.backtesting.trade_simulator import TradeSimulator

from backtesting.backtester import Backtester

log = logging.getLogger(__name__)


# ==========================================================
# Fixtures
# ==========================================================


class Candle:

    def __init__(self, high, low, close, timestamp):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


def ob(direction, high, low, index=5, score=85.0):
    if direction == "BULLISH":
        open_, close = high, low
    else:
        open_, close = low, high
    block = OrderBlock(
        index=index,
        timestamp=1000,
        timeframe="1m",
        direction=direction,
        open=open_,
        high=high,
        low=low,
        close=close,
        strength=score,
        displacement_strength=score,
    )
    block.score = score
    return block


def liquidity_target(price=170.0):
    return LiquidityTarget(
        side="BUY",
        price=price,
        timeframe="1m",
        score=90.0,
        probability=90.0,
        distance=13.0,
        strength=0.9,
        reason="test",
        source_pool="pool-1",
    )


def trend():
    return TrendState(direction="BULLISH")


def regime():
    return RegimeState(
        score=90.0,
        confidence=90.0,
        grade="A",
        regime="TRENDING",
    )


def seeded_world(context):
    registry = OrderBlockRegistry()
    registry.add(ob("BULLISH", 110.0, 100.0, index=5))
    context.order_blocks = registry
    context.liquidity_target = liquidity_target()
    context.trend = trend()
    context.regime = regime()
    context.fvgs = FVGRegistry()


def seeded_multi_world(context):
    # Two distinct bullish setups (distinct order-block index and
    # economics -> distinct setup_ids) so ExecutionEngine/RiskEngine
    # have more than one accept-able signal per candle (Phase 4D
    # STEP 8 multi-pending model). NOTE: under Phase 4E economic
    # deduplication these two blocks are NEAR-IDENTICAL execution
    # zones (entry 110 vs 109, stop 100 vs 100.5, target 170 --
    # inside the default 8-tick cluster tolerance), so they collapse
    # into ONE canonical setup. Use seeded_distinct_world when the
    # test needs genuinely independent pending orders.
    registry = OrderBlockRegistry()
    registry.add(ob("BULLISH", 110.0, 100.0, index=5))
    registry.add(ob("BULLISH", 109.0, 100.5, index=6))
    context.order_blocks = registry
    context.liquidity_target = liquidity_target()
    context.trend = trend()
    context.regime = regime()
    context.fvgs = FVGRegistry()


def seeded_distinct_world(context):
    # Two bullish blocks whose execution zones are FAR apart (entry
    # 110 vs 120, stop 100 vs 109 -- both beyond the 8-tick / 0.1%
    # cluster tolerance) so they are genuinely INDEPENDENT
    # opportunities under Phase 4E and must never cluster. Both
    # clear the DecisionEngine gates: A rr = 80/10 = 8.0, B rr =
    # 70/11 ~ 6.36 (shared target 190 keeps both above the
    # authoritative 6.0 minimum).
    registry = OrderBlockRegistry()
    registry.add(ob("BULLISH", 110.0, 100.0, index=5))
    registry.add(ob("BULLISH", 120.0, 109.0, index=6))
    context.order_blocks = registry
    context.liquidity_target = liquidity_target(price=190.0)
    context.trend = trend()
    context.regime = regime()
    context.fvgs = FVGRegistry()


def seeded_same_economics_world(context):
    # Two structurally distinct bullish blocks with IDENTICAL trade
    # economics (entry 110 / stop 100 / target 170): OB-5 and OB-6
    # produce two different setup_ids but ONE economic fingerprint --
    # the exact Phase 4E economically-duplicate case (like OB-954 vs
    # OB-956 in the live regression). Exactly one pending order may
    # ever be minted for this idea.
    registry = OrderBlockRegistry()
    registry.add(ob("BULLISH", 110.0, 100.0, index=5))
    registry.add(ob("BULLISH", 110.0, 100.0, index=6))
    context.order_blocks = registry
    context.liquidity_target = liquidity_target()
    context.trend = trend()
    context.regime = regime()
    context.fvgs = FVGRegistry()


class FakeIndicators:
    """
    Minimal stand-in for the canonical IndicatorCache used by the
    scripted lifecycle harness (no indicator stack, no network):
    delivers a stable ATR_14 so the Phase 4F entry-feasibility
    snapshot has an ATR axis to normalize against. The real
    InstitutionalPipeline publishes a real IndicatorCache; the
    tracker's no-leak proof pins that these diagnostics change
    nothing about orders.
    """

    def __init__(self, atr=15.0):
        self._atr = atr

    def latest(self, name):
        if name == "ATR_14":
            return self._atr
        return None


class WorldPipeline:
    """
    Mirror of the canonical Signal -> Risk -> Order chain, driven
    explicitly per candle so the FULL lifecycle code path runs
    (TradeSetupBuilder -> DecisionEngine -> ExecutionEngine ->
    RiskEngine -> OrderRegistry) without Indicators/network. The
    world (order block + liquidity target) is identical every
    candle -- the exact duplicate-signal scenario -- so the same
    setup_id is re-derived bar after bar. World may be "single"
    (one bullish block) or "multi" (two bullish blocks).
    """

    def __init__(self, world="single"):
        self.builder = TradeSetupBuilder()
        self.decision = DecisionEngine()
        self.execution = ExecutionEngine()
        self.risk = RiskEngine()
        self.world = world
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        # Phase 4F: the scaffolded ATR so the builder can stamp an
        # ATR-normalized feasibility snapshot (diagnostic only).
        self.context.indicators = FakeIndicators()
        if self.world == "multi":
            seeded_multi_world(self.context)
        elif self.world == "distinct":
            seeded_distinct_world(self.context)
        elif self.world == "same":
            seeded_same_economics_world(self.context)
        else:
            seeded_world(self.context)
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def on_candle(self, event):
        # Backtester.run reset_cycle()s the per-candle outputs;
        # re-publish the canonical world (the indicator stack
        # would) so the same setup is re-derived every candle.
        if self.world == "multi":
            seeded_multi_world(self.context)
        elif self.world == "distinct":
            seeded_distinct_world(self.context)
        elif self.world == "same":
            seeded_same_economics_world(self.context)
        else:
            seeded_world(self.context)
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.builder.analyze(self.context)
        self.decision.analyze(self.context)
        self.execution.analyze(self.context)
        self.risk.analyze(self.context)


class EventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


def run_world(
    candles,
    max_wait_bars=None,
    world="single",
    entry_mode=None,
):
    """
    Replay candles through the canonical four-engine pipeline
    plus the real Backtester adapter. Returns
    (backtester, simulator, pipeline, registry).
    """
    entry_mode = entry_mode or ENTRY_MODE_LIMIT_RETEST
    with mock.patch.object(
        risk_settings, "MAX_WAIT_BARS", max_wait_bars or risk_settings.MAX_WAIT_BARS
    ), mock.patch.object(
        risk_settings, "ENTRY_MODE", entry_mode
    ), mock.patch.object(
        risk_settings, "ACTIVE_ENTRY_MODES", (entry_mode,)
    ):
        pipeline = WorldPipeline(world=world)
        event_bus = EventBus(pipeline)
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)
        backtester.run(candles)
        return backtester, simulator, pipeline, pipeline.context.order_registry


def touch_candle(ts):
    return Candle(high=112.0, low=109.0, close=110.0, timestamp=ts)


def miss_candle(ts):
    return Candle(high=108.0, low=106.0, close=107.5, timestamp=ts)


def hold_candle(ts):
    return Candle(high=111.0, low=109.0, close=110.5, timestamp=ts)


def tp_candle(ts):
    return Candle(high=171.0, low=170.5, close=170.8, timestamp=ts)


def sl_candle(ts):
    return Candle(high=101.0, low=99.0, close=99.5, timestamp=ts)


def invalidate_candle(ts):
    # BULLISH order on stop 100.0 / entry 110.0: low 99.0 breaches
    # the stop but high 105.0 never reaches the entry.
    return Candle(high=105.0, low=99.0, close=102.0, timestamp=ts)


def both_candle(ts):
    # Same-candle ambiguity: low breaches the stop AND high reaches
    # the entry. Phase 4D STEP 4 resolves it conservatively --
    # invalidation before entry-fill.
    return Candle(high=111.0, low=99.0, close=105.0, timestamp=ts)


def a_touch_candle(ts):
    # Touches setup A (entry 110.0) but NOT setup B (entry 109.0):
    # low 109.5 -> 110 in [109.5, 111], 109 not in range. Stops of
    # both blocks (100.0 / 100.5) are safe.
    return Candle(high=111.0, low=109.5, close=110.5, timestamp=ts)


def orders_for(registry, setup_id):
    return [
        o for o in registry.all()
        if getattr(o, "setup_id", "") == setup_id
    ]


class _Capture(logging.Handler):

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def attach(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    cap = _Capture()
    logger.addHandler(cap)
    return cap, logger


def counts(cap, needle):
    return sum(
        1 for r in cap.records
        if needle in r.getMessage()
    )


# ==========================================================
# 1. OrderRegistry unit lifecycle
# ==========================================================


class TestOrderRegistryLifecycle(unittest.TestCase):

    def _intent(self, setup_id, entry=110.0):
        from core.risk.order_intent import OrderIntent
        intent = OrderIntent(
            direction="BULLISH",
            entry=entry,
            stop_loss=100.0,
            take_profit=170.0,
            risk_reward=6.0,
            quantity=1.0,
            confidence=85.0,
            score=85.0,
            setup_id=setup_id,
            valid=True,
        )
        return intent

    def test_order_registry_blocks_duplicate_order(self):
        registry = OrderRegistry()
        a = self._intent("S-1")
        b = self._intent("S-1")

        first, a_id = registry.create(a)
        second, b_id = registry.create(b)

        self.assertEqual(a_id, b_id)
        self.assertIs(first, second)
        self.assertEqual(len(registry.all()), 1)
        self.assertTrue(registry.has_order_for_setup("S-1"))
        self.assertEqual(a.status, PENDING)

    def test_distinct_setups_get_distinct_orders(self):
        registry = OrderRegistry()
        a, a_id = registry.create(self._intent("S-1"))
        b, b_id = registry.create(self._intent("S-2"))

        self.assertNotEqual(a_id, b_id)
        self.assertEqual(len(registry.all()), 2)

    def test_order_id_format_embeds_setup_id(self):
        registry = OrderRegistry()
        _, a_id = registry.create(self._intent("S-1"))
        self.assertTrue(a_id.startswith("S-1-ORDER-"))

    def test_mark_filled_consumes_exactly_once(self):
        registry = OrderRegistry()
        order, order_id = registry.create(self._intent("S-1"))

        trade = type("T", (), {})()
        first = registry.mark_filled(order, trade)
        second = registry.mark_filled(order, trade)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(order.status, FILLED)
        self.assertEqual(trade.trade_id, first)
        self.assertTrue(first.startswith("S-1-ORDER-1-TRADE-1"))
        self.assertEqual(trade.setup_id, "S-1")
        self.assertEqual(trade.order_id, order_id)

    def test_advance_expires_stale_pending_orders(self):
        registry = OrderRegistry(max_wait_bars=2)
        order, _ = registry.create(self._intent("S-1"))

        registry.advance("t1")  # wb=1
        registry.advance("t2")  # wb=2
        self.assertEqual(order.status, PENDING)

        registry.advance("t3")  # wb=3 > 2 -> EXPIRED
        self.assertEqual(order.status, "EXPIRED")
        self.assertEqual(len(registry.pending()), 0)
        self.assertTrue(registry.terminal())

    def test_terminal_order_is_not_fillable(self):
        registry = OrderRegistry(max_wait_bars=1)
        order, _ = registry.create(self._intent("S-1"))

        registry.advance("t1")  # wb=1 (still pending)
        registry.advance("t2")  # wb=2 > 1 -> EXPIRED

        trade = type("T", (), {})()
        self.assertIsNone(registry.mark_filled(order, trade))
        self.assertIsNone(getattr(trade, "trade_id", None))


# ==========================================================
# 2. Engine idempotency + registration dedupe
# ==========================================================


class TestEngineIdempotency(unittest.TestCase):

    def _world_once(self):
        pipeline = WorldPipeline()
        context = pipeline.context
        context.account = AccountState(
            starting_balance=10000.0,
            balance=10000.0,
            equity=10000.0,
            peak_equity=10000.0,
            drawdown=0.0,
            drawdown_percent=0.0,
        )
        return pipeline, context

    def test_same_setup_processed_twice_creates_one_order(self):
        pipeline, context = self._world_once()
        candle = touch_candle(1)

        for _ in range(2):
            pipeline.on_candle(CandleEvent(candle=candle))

        setup = context.trade_setups[0]
        orders = orders_for(context.order_registry, setup.setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, PENDING)
        self.assertTrue(context.order_registry.has_order_for_setup(setup.setup_id))

    def test_execution_engine_is_idempotent(self):
        pipeline, context = self._world_once()

        pipeline.builder.analyze(context)
        pipeline.decision.analyze(context)
        pipeline.execution.analyze(context)
        pipeline.risk.analyze(context)

        self.assertIsNotNone(context.execution_signal)
        self.assertIsNotNone(context.order)

        setup = context.trade_setups[0]

        # Re-running the whole chain on a re-derived identical
        # setup must clear the signal (dedupe guard) ...
        pipeline.decision.analyze(context)
        pipeline.execution.analyze(context)

        self.assertIsNone(context.execution_signal)

        # ... and RiskEngine then produces no second order.
        pipeline.risk.analyze(context)
        self.assertIsNone(context.order)
        self.assertEqual(
            len(orders_for(context.order_registry, setup.setup_id)), 1
        )

    def test_risk_engine_not_called_twice_for_same_setup(self):
        pipeline, context = self._world_once()
        setup_id = "{}-{}-{}-OB-{}-{:.2f}-{:.2f}-{:.2f}".format(
            "TEST", "1m", "BULLISH", 5, 110.0, 100.0, 170.0
        )

        registry = context.order_registry
        self.assertFalse(registry.has_order_for_setup(setup_id))

        for _ in range(2):
            pipeline.builder.analyze(context)
            pipeline.decision.analyze(context)
            pipeline.execution.analyze(context)
            pipeline.risk.analyze(context)

        self.assertEqual(
            len(orders_for(registry, setup_id)), 1
        )

    def test_pipeline_registration_dedupes_by_name(self):
        pipeline = InstitutionalPipeline(PipelineContext())
        before = [
            e for e in pipeline.engines
            if e.name == "ExecutionEngine"
        ]
        pipeline.register(ExecutionEngine())
        after = [
            e for e in pipeline.engines
            if e.name == "ExecutionEngine"
        ]
        self.assertEqual(len(before), 1)
        self.assertEqual(len(after), 1)
        self.assertIs(before[0], after[0])


# ==========================================================
# 3. Backtester fill lifecycle (consume-once + entry touch)
# ==========================================================


class TestBacktesterLifecycle(unittest.TestCase):

    def test_backtester_consumes_order_once(self):
        candles = [
            touch_candle(1),
            hold_candle(2),
            hold_candle(3),
            tp_candle(4),
        ]
        backtester, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, FILLED)
        self.assertEqual(len(registry.filled()), 1)
        self.assertEqual(simulator.registry.count(), 1)

    def test_same_setup_regression_no_second_order_over_bars(self):
        # 30 candles where the identical world re-derives the same
        # setup every bar: exactly one order, one fill, one trade.
        candles = (
            [touch_candle(1)] +
            [hold_candle(i) for i in range(2, 30)] +
            [tp_candle(30)]
        )
        backtester, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id

        self.assertEqual(len(orders_for(registry, setup_id)), 1)
        self.assertEqual(len(registry.all()), 1)
        self.assertEqual(simulator.registry.count(), 1)
        self.assertEqual(backtester.processed_bars, 30)

    def test_pending_order_does_not_fill_without_entry_touch(self):
        backtester, simulator, pipeline, registry = run_world(
            [miss_candle(1), miss_candle(2)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, PENDING)
        self.assertEqual(simulator.registry.count(), 0)

    def test_pending_order_fills_on_later_entry_touch(self):
        backtester, simulator, pipeline, registry = run_world(
            [miss_candle(1), miss_candle(2), touch_candle(3)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, FILLED)

        trade = simulator.current_trade
        self.assertIsNotNone(trade)
        self.assertEqual(trade.setup_id, setup_id)
        self.assertEqual(trade.order_id, orders[0].order_id)

    def test_entry_boundaries_inclusive(self):
        # Phase 4D eligibility: an order created on bar 1 may not
        # fill on bar 1 (no same-candle look-ahead). Create it on a
        # miss bar, then low == entry on the eligible bar -> fills.
        low_eq = Candle(high=110.5, low=110.0, close=110.2, timestamp=2)
        _, simulator, _, registry = run_world(
            [miss_candle(1), low_eq]
        )
        self.assertIsNotNone(simulator.current_trade)

        # entry strictly above the whole candle range but the stop
        # intact (low 106 > 100): stays pending even when eligible.
        far = Candle(high=108.0, low=106.0, close=107.0, timestamp=2)
        _, sim2, pipe2, reg2 = run_world([miss_candle(1), far])
        setup_id = pipe2.context.trade_setups[0].setup_id
        self.assertEqual(sim2.registry.count(), 0)
        self.assertEqual(orders_for(reg2, setup_id)[0].status, PENDING)

    def test_same_order_cannot_fill_twice(self):
        # Order created on candle 1 (ineligible), fills on candle 2
        # which also touches; a later touch cannot refill it.
        candles = [
            touch_candle(1),
            touch_candle(2),   # same world, same setup, fills here
            tp_candle(3),
        ]
        _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, FILLED)
        self.assertEqual(simulator.registry.count(), 1)

    def test_terminal_order_cannot_fill_after_expiry(self):
        # An order created on bar 1 (created_bar=1, ENTRY_DELAY=1,
        # MAX_WAIT=2) is eligible on bars 2..4 and EXPIRES at the
        # very END of bar 4 (after its fill check). A touch on bar 5
        # therefore cannot fill it.
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            candles = [
                miss_candle(1),   # created here
                miss_candle(2),   # eligible, no touch
                miss_candle(3),   # no touch
                miss_candle(4),   # expiry bar: fill check misses -> EXPIRED
                touch_candle(5),  # entry touched but order terminal
            ]
            _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, "EXPIRED")
        self.assertEqual(orders[0].terminal_bar, 4)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(len(registry.filled()), 0)

    def test_setup_to_order_to_trade_identity_chain(self):
        candles = [touch_candle(1), hold_candle(2), tp_candle(3)]
        _, simulator, pipeline, registry = run_world(candles)

        setup = pipeline.context.trade_setups[0]
        order = orders_for(registry, setup.setup_id)[0]
        trade = simulator.registry.all()[0]

        self.assertEqual(order.setup_id, setup.setup_id)
        self.assertEqual(trade.setup_id, setup.setup_id)
        self.assertEqual(trade.order_id, order.order_id)
        self.assertEqual(trade.trade_id, order.trade_id)
        self.assertTrue(trade.trade_id.startswith(
            f"{order.order_id}-TRADE-"
        ))
        self.assertTrue(order.order_id.startswith(
            f"{setup.setup_id}-ORDER-"
        ))

    def test_lifecycle_events_fire_at_most_once_each(self):
        candles = [
            touch_candle(1),
            hold_candle(2),
            hold_candle(3),
            tp_candle(4),
        ]

        decision_name = "core.setup.decision_engine"
        risk_name = "core.risk.risk_engine"
        backtester_name = "backtesting.backtester"
        sim_name = "core.backtesting.trade_simulator"

        caps = {}

        with mock.patch.object(
            risk_settings, "MAX_WAIT_BARS", risk_settings.MAX_WAIT_BARS
        ):
            for name in (decision_name, risk_name,
                         backtester_name, sim_name):
                cap, _ = attach(name)
                caps[name] = cap

            _, simulator, pipeline, registry = run_world(candles)

            setup_id = pipeline.context.trade_setups[0].setup_id

        self.assertEqual(
            counts(caps[decision_name], "SETUP_ACCEPTED"), 1
        )
        self.assertEqual(
            counts(caps[risk_name], "ORDER_CREATED setup_id=%s" % setup_id), 1
        )
        self.assertEqual(
            counts(caps[risk_name], "EXECUTION_SIGNAL setup_id=%s" % setup_id),
            1,
        )
        self.assertEqual(
            counts(caps[backtester_name], "ORDER_FILLED setup_id=%s" % setup_id),
            1,
        )
        self.assertEqual(
            counts(caps[sim_name], "TRADE_CLOSED setup_id=%s" % setup_id), 1
        )

        # And the aggregates agree with the registry-truth.
        self.assertEqual(len(registry.all()), 1)
        self.assertEqual(simulator.registry.count(), 1)


# ==========================================================
# Phase 4D: Pending-order fill / invalidation / expiration
# integrity (bar-anchored lifecycle)
# ==========================================================


class TestPendingOrderIntegrity(unittest.TestCase):

    # --------------------------------------------------
    # Eligibility (no same-candle look-ahead)
    # --------------------------------------------------

    def test_new_order_cannot_expire_same_bar(self):
        # MAX_WAIT_BARS=0 still cannot expire the order on its own
        # creation bar: eligible_from = 1 + 1 = 2, expires_at = 2.
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 0):
            _, simulator, pipeline, registry = run_world(
                [miss_candle(1)]
            )

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, PENDING)
        self.assertEqual(orders[0].created_bar, 1)
        self.assertEqual(orders[0].eligible_from_bar, 2)
        self.assertEqual(orders[0].expires_at_bar, 2)
        self.assertEqual(simulator.registry.count(), 0)

    def test_order_becomes_eligible_next_bar(self):
        # A touch candle on the CREATION bar is ineligible (the
        # signal only exists at that candle's close -- filling
        # inside its own range would be look-ahead). The same touch
        # on the next bar fills.
        _, sim0, pipe0, reg0 = run_world([touch_candle(1)])
        setup0 = pipe0.context.trade_setups[0].setup_id
        order0 = orders_for(reg0, setup0)[0]

        self.assertEqual(order0.status, PENDING)
        self.assertIsNone(sim0.current_trade)

        _, sim, pipe, reg = run_world(
            [touch_candle(1), miss_candle(2), touch_candle(3),
             tp_candle(4)]
        )
        setup_id = pipe.context.trade_setups[0].setup_id
        order = orders_for(reg, setup_id)[0]

        self.assertEqual(order.status, FILLED)
        self.assertEqual(order.filled_bar, 3)
        self.assertEqual(sim.registry.count(), 1)

    # --------------------------------------------------
    # Fill only on entry touch
    # --------------------------------------------------

    def test_order_waits_until_entry_is_touched(self):
        _, simulator, pipeline, registry = run_world(
            [miss_candle(1), miss_candle(2), touch_candle(3)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, FILLED)
        self.assertEqual(order.filled_bar, 3)
        self.assertEqual(order.waited_bars, 1)  # 3 - eligible_from(2)
        self.assertIsNotNone(simulator.current_trade)

    def test_order_fills_when_entry_is_inside_candle_range(self):
        # entry 110.0 sits inside the [109.0, 111.0] range of
        # hold_candle on the eligible bar 2
        _, simulator, pipeline, registry = run_world(
            [miss_candle(1), hold_candle(2)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, FILLED)
        self.assertEqual(order.filled_bar, 2)
        self.assertEqual(order.entry, 110.0)
        # Phase 4E excursions: the eligible fill bar rolls the
        # lifetime low/high at least once (and the stale
        # min/max_price_since_creation no longer exists).
        self.assertTrue(
            getattr(order, "min_low_since_creation", None) is not None
        )
        self.assertTrue(
            getattr(order, "max_high_since_creation", None) is not None
        )
        self.assertFalse(
            hasattr(order, "min_price_since_creation")
        )
        self.assertIsNotNone(simulator.current_trade)

    def test_order_does_not_fill_when_entry_not_reached(self):
        _, simulator, pipeline, registry = run_world(
            [miss_candle(1), miss_candle(2)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, PENDING)
        self.assertEqual(simulator.registry.count(), 0)

    # --------------------------------------------------
    # Expiration (bar-anchored, last step of the cycle)
    # --------------------------------------------------

    def test_order_expires_exactly_at_expiry_bar(self):
        # created=1, eligible=2, expires_at=2 + 2 = 4. Bars 2,3,4 are
        # all eligible; the END of bar 4 terminales the order (its
        # fill check missed on that bar first).
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            _, simulator, pipeline, registry = run_world(
                [miss_candle(1), miss_candle(2),
                 miss_candle(3), miss_candle(4)]
            )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, "EXPIRED")
        self.assertEqual(order.eligible_from_bar, 2)
        self.assertEqual(order.expires_at_bar, 4)
        self.assertEqual(order.terminal_bar, 4)
        self.assertEqual(order.waited_bars, 2)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(len(registry.filled()), 0)

    def test_fill_prevents_later_expiration(self):
        # The order fills on bar 3 (before its expiry bar 4); a
        # later touch cannot refill it and it is never EXPIRED.
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            _, simulator, pipeline, registry = run_world(
                [touch_candle(1), miss_candle(2), touch_candle(3),
                 touch_candle(4), tp_candle(5)]
            )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, FILLED)
        self.assertEqual(order.filled_bar, 3)
        self.assertEqual(simulator.registry.count(), 1)
        self.assertEqual(len(registry.expired()), 0)

    def test_terminal_order_cannot_fill_after_expiry(self):
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            candles = [
                miss_candle(1),   # created here
                miss_candle(2),   # eligible, no touch
                miss_candle(3),   # no touch
                miss_candle(4),   # expiry bar: fill check misses -> EXPIRED
                touch_candle(5),  # entry touched but order terminal
            ]
            _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        orders = orders_for(registry, setup_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, "EXPIRED")
        self.assertEqual(orders[0].terminal_bar, 4)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(len(registry.filled()), 0)

    # --------------------------------------------------
    # Invalidation (structural stop breach, NOT expiration)
    # --------------------------------------------------

    def test_order_invalidates_before_expiration(self):
        # Bar 2 low (99.0) breaches the bullish stop (100.0) before
        # the order would ever expire -> ORDER_INVALIDATED.
        _, simulator, pipeline, registry = run_world(
            [miss_candle(1), invalidate_candle(2)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, "INVALIDATED")
        self.assertEqual(order.terminal_bar, 2)
        self.assertEqual(order.invalidation_price, 99.0)
        self.assertEqual(order.invalidation_level, 100.0)
        self.assertTrue(order.reason)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(len(registry.pending()), 0)
        self.assertEqual(len(registry.filled()), 0)

    def test_invalidation_precedes_fill_on_same_candle(self):
        # Intrabar ambiguity: the same candle reaches the entry
        # (high 111 >= 110) AND breaks the stop (low 99 <= 100).
        # STEP 4 ordering makes invalidation win -- never a fill.
        _, simulator, pipeline, registry = run_world(
            [miss_candle(1), both_candle(2)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, "INVALIDATED")
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(len(registry.filled()), 0)

    # --------------------------------------------------
    # Multi-pending (MAX_PENDING_ORDERS) + metadata
    # --------------------------------------------------

    def test_multiple_pending_orders_respect_limit(self):
        # Two accepted setups on the distinct world (genuinely
        # independent zones under Phase 4E clustering -- they never
        # collapse into one). With MAX_PENDING_ORDERS=1 the
        # RiskEngine mints exactly one order -- the best-scoring
        # (ties resolve to A, the first block) -- and the second
        # setup is queued, not orphaned.
        with mock.patch.object(
            risk_settings, "MAX_PENDING_ORDERS_TOTAL", 1
        ):
            _, simulator, pipeline, _ = run_world(
                [miss_candle(1)], world="distinct"
            )

        setup_ids = {
            s.setup_id for s in pipeline.context.trade_setups
        }
        self.assertEqual(len(setup_ids), 2)

        registry = pipeline.context.order_registry

        self.assertEqual(len(registry.all()), 1)
        ordered = registry.all()[0]
        self.assertIn("OB-5", ordered.setup_id)
        self.assertTrue(ordered.setup_id in setup_ids)
        self.assertEqual(simulator.registry.count(), 0)

    def test_multiple_pending_orders_can_both_sit_pending(self):
        _, simulator, pipeline, registry = run_world(
            [miss_candle(1), a_touch_candle(2)], world="distinct"
        )

        setup_ids = {
            s.setup_id for s in pipeline.context.trade_setups
        }
        self.assertEqual(len(setup_ids), 2)

        # Exactly two primary orders, one per accepted setup.
        self.assertEqual(len(registry.all()), 2)
        self.assertEqual(len(registry.pending()) + len(registry.filled()), 2)

        # best-scoring first: A (OB-5, entry 110) fills on bar 2
        # when its entry is the only one touched; B stays pending.
        filled = registry.filled()
        pending = registry.pending()

        self.assertEqual(len(filled), 1)
        self.assertEqual(len(pending), 1)
        self.assertIn("OB-5", filled[0].setup_id)
        self.assertIn("OB-6", pending[0].setup_id)

        # Single-position model: exactly one trade opened.
        trade = simulator.current_trade
        self.assertIsNotNone(trade)
        self.assertEqual(trade.setup_id, filled[0].setup_id)
        self.assertEqual(trade.order_id, filled[0].order_id)

    def test_created_order_bar_metadata_is_correct(self):
        _, _, pipeline, registry = run_world(
            [miss_candle(1), miss_candle(2)]
        )

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.created_bar, 1)
        self.assertEqual(order.created_timestamp, 1)
        self.assertEqual(order.eligible_from_bar, 2)
        self.assertEqual(
            order.expires_at_bar,
            2 + risk_settings.MAX_WAIT_BARS,
        )
        self.assertIsNone(order.filled_bar)
        self.assertIsNone(order.terminal_bar)

    def test_order_created_to_expired_log_chain(self):
        # Regression fixture: 40 bars that never reach the entry
        # with the default MAX_WAIT_BARS=30 -> created on bar 1,
        # EXPIRED at the end of bar 32 with full diagnostics, and
        # zero trades.
        backtester_name = "backtesting.backtester"

        candles = [
            miss_candle(i) for i in range(1, 41)
        ]

        cap, _ = attach(backtester_name)

        _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id

        self.assertEqual(len(registry.all()), 1)
        orders = orders_for(registry, setup_id)
        self.assertEqual(orders[0].status, "EXPIRED")
        self.assertEqual(orders[0].terminal_bar, 32)
        self.assertEqual(simulator.registry.count(), 0)

        exp = [r for r in cap.records if "ORDER_EXPIRED" in r.getMessage()]
        self.assertEqual(len(exp), 1)
        msg = exp[0].getMessage()
        self.assertIn("created_bar=1", msg)
        self.assertIn("eligible_from_bar=2", msg)
        self.assertIn("expired_bar=32", msg)
        self.assertIn("waited_bars=30", msg)
        self.assertIn("max_wait_bars=30", msg)
        self.assertIn("entry=110.00", msg)
        # Phase 4E lifetime-excursion diagnostics: every miss candle
        # is high 108 / low 106, so the whole eligible lifetime ran
        # 106..108 -- 30 eligible bars plus the expiry bar.
        self.assertIn("min_low_since_creation=106.0", msg)
        self.assertIn("max_high_since_creation=108.0", msg)
        self.assertIn("bars_pending=31", msg)
        # entry 110 never reached (nearest extreme 108 -> distance 2)
        self.assertIn(
            "entry_distance_from_nearest_price=2.0", msg
        )


# ==========================================================
# Phase 4E: Order excursion tracking (lifetime min/max since
# creation, init on the first eligible candle, rolled EVERY
# eligible pending candle -- including while a position is open)
# ==========================================================


class TestOrderExcursionTracking(unittest.TestCase):

    # Phase 4E Problem 1: a pending order's diagnostics must
    # reflect its WHOLE eligible lifetime. Before Phase 4E the
    # min/max "since creation" fields were rolled before the
    # eligibility check AND the whole pending pass was skipped
    # while a position was open -- so expiries could log
    # identical stale values (e.g. min==max==77538.5 across
    # different orders and bars). These tests pin the corrected
    # lifetime rolling.

    # --------------------------------------------------

    def test_order_tracks_minimum_low_across_multiple_bars(self):
        # Eligible bars 2..4 roll lows 105 -> 104 -> 103; the
        # creation candle (low 106) is INELIGIBLE and must never
        # count toward the excursion.
        candles = [
            miss_candle(1),
            Candle(high=107.5, low=105.0, close=106.0, timestamp=2),
            Candle(high=107.0, low=104.0, close=105.0, timestamp=3),
            Candle(high=106.5, low=103.0, close=104.0, timestamp=4),
        ]
        _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, PENDING)
        self.assertEqual(order.min_low_since_creation, 103.0)
        # The creation candle's low (106.0) was excluded -- the
        # excursion starts on the first ELIGIBLE candle.
        self.assertEqual(order.bars_pending, 3)
        self.assertEqual(simulator.registry.count(), 0)

    # --------------------------------------------------

    def test_order_tracks_maximum_high_across_multiple_bars(self):
        # Eligible bars 2..4 roll highs 109 -> 109.5 -> 108.5; the
        # creation candle (high 108) contributes nothing.
        candles = [
            miss_candle(1),
            Candle(high=109.0, low=105.5, close=106.0, timestamp=2),
            Candle(high=109.5, low=104.5, close=105.0, timestamp=3),
            Candle(high=108.5, low=103.5, close=104.0, timestamp=4),
        ]
        _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, PENDING)
        self.assertEqual(order.max_high_since_creation, 109.5)
        self.assertEqual(order.min_low_since_creation, 103.5)
        self.assertEqual(order.bars_pending, 3)
        self.assertEqual(simulator.registry.count(), 0)

    # --------------------------------------------------

    def test_each_pending_order_has_independent_excursion_data(self):
        # Distinct world: A (entry 110/stop 100, target 190) and B
        # (entry 120/stop 109, target 190). A fills on bar 2; B --
        # the FROZEN case -- must keep rolling its own excursion on
        # bars 3-4 while A's position is OPEN (before Phase 4E the
        # pending pass was skipped entirely during an open position).
        candles = [
            miss_candle(1),
            a_touch_candle(2),   # A fills (110 touched); B untouched
            Candle(high=116.0, low=110.0, close=112.0, timestamp=3),
            Candle(high=118.5, low=109.1, close=110.0, timestamp=4),
        ]
        backtester, simulator, pipeline, registry = run_world(
            candles, world="distinct"
        )

        a = [o for o in registry.all() if "OB-5" in o.setup_id][0]
        b = [o for o in registry.all() if "OB-6" in o.setup_id][0]

        self.assertEqual(a.status, FILLED)
        self.assertEqual(b.status, PENDING)

        # A is terminal on bar 2: its excursion covers exactly its
        # single eligible bar (109.5..111).
        self.assertEqual(a.min_low_since_creation, 109.5)
        self.assertEqual(a.max_high_since_creation, 111.0)
        self.assertEqual(a.bars_pending, 1)

        # B rides bars 2..4 -- including two bars (3,4) while A's
        # position is literally open -- and its values are its own
        # (bar 4's low 109.1 beats its own bar-2 init of 109.5).
        self.assertEqual(b.min_low_since_creation, 109.1)
        self.assertEqual(b.max_high_since_creation, 118.5)
        self.assertEqual(b.bars_pending, 3)

        self.assertIsNot(a, b)
        self.assertNotEqual(
            a.min_low_since_creation,
            b.min_low_since_creation,
        )

        # The position opened by A is still live at the end -- the
        # rolling happened INSIDE it.
        self.assertIsNotNone(simulator.current_trade)
        # Pending capacity metrics: 2 after the creation bar (A+B),
        # then 1 while A's trade is open (B only).
        self.assertEqual(backtester.pending_orders_average, 1.25)
        self.assertEqual(backtester.pending_orders_max, 2)

    # --------------------------------------------------

    def test_expiration_log_uses_lifetime_excursion(self):
        # MAX_WAIT=2: eligible bars 2..4; the order expires at the
        # END of bar 4. The ORDER_EXPIRED log must report the
        # lifetime excursion (lows 105/104/102 -> min 102; highs
        # 107/106/105 -> max 107) and the distance from the entry
        # to the nearer extreme (entry 110 vs extremes 102..107 ->
        # 3.0), NOT creation-candle or expiry-candle-only values.
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            candles = [
                miss_candle(1),
                Candle(high=107.0, low=105.0, close=106.0, timestamp=2),
                Candle(high=106.0, low=104.0, close=105.0, timestamp=3),
                Candle(high=105.0, low=102.0, close=103.0, timestamp=4),
            ]
            cap, _ = attach("backtesting.backtester")
            _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, "EXPIRED")
        self.assertEqual(order.terminal_bar, 4)
        self.assertEqual(order.min_low_since_creation, 102.0)
        self.assertEqual(order.max_high_since_creation, 107.0)
        self.assertEqual(order.bars_pending, 3)
        self.assertEqual(
            order.entry_distance_from_nearest_price, 3.0
        )

        exp = [r for r in cap.records if "ORDER_EXPIRED" in r.getMessage()]
        self.assertEqual(len(exp), 1)
        msg = exp[0].getMessage()
        self.assertIn("min_low_since_creation=102.0", msg)
        self.assertIn("max_high_since_creation=107.0", msg)
        self.assertIn("bars_pending=3", msg)
        self.assertIn(
            "entry_distance_from_nearest_price=3.0", msg
        )
        self.assertEqual(simulator.registry.count(), 0)

    # --------------------------------------------------

    def test_entry_touch_is_detected_before_expiration(self):
        # MAX_WAIT=2 -> eligible bars 2..4, order expires at the end
        # of bar 4. A touch may come at ANY eligible bar; when it
        # lands ON the expiry bar itself the order FILLS, never
        # expires (expiry is processed after that bar's fill check).
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            candles = [
                miss_candle(1),
                miss_candle(2),
                miss_candle(3),
                touch_candle(4),   # the expiry bar -- last chance
            ]
            _, simulator, pipeline, registry = run_world(candles)

        setup_id = pipeline.context.trade_setups[0].setup_id
        order = orders_for(registry, setup_id)[0]

        self.assertEqual(order.status, FILLED)
        self.assertEqual(order.filled_bar, 4)
        self.assertEqual(order.terminal_bar, 4)
        self.assertEqual(order.waited_bars, 2)   # 4 - eligible(2)
        self.assertEqual(len(registry.expired()), 0)
        self.assertIsNotNone(simulator.current_trade)

        # The excursion range brackets the entry (106..112 covers
        # 110), proving the market reached it within the lifetime.
        self.assertEqual(order.min_low_since_creation, 106.0)
        self.assertEqual(order.max_high_since_creation, 112.0)
        self.assertEqual(order.bars_pending, 3)


if __name__ == "__main__":

    unittest.main()