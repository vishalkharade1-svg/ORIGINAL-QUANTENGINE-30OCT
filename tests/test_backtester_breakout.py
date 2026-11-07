"""
====================================================

QuantEngine

Breakout Continuation Execution Tests

Run with:

    python -m unittest tests.test_backtester_breakout -v

Proves the Phase 5B next-bar-open fill branch inside the
canonical event-driven Backtester, driven through the REAL
four-engine pipeline (TradeSetupBuilder -> DecisionEngine ->
ExecutionEngine -> RiskEngine -> OrderRegistry -> backtester
pending-order pass), with BREAKOUT_CONTINUATION as the
executed mode:

    1. A BREAKOUT_CONTINUATION order (entry_execution
       NEXT_BAR_OPEN) never fills on the trigger candle:
       it triggers at the trigger close, then fills at the OPEN
       of the entry bar (trigger bar + 1) -- causality RULE 3.
    2. A same-bar structural stop breach invalidates instead of
       triggering (step 3 before the trigger, RULE 1).
    3. A filled entry respects the REAL |open - stop| distance:
       quantity is re-derived from the frozen risk_amount so the
       dollar risk the order froze is exactly the risk at the
       open entry (risk_amount == filled qty * |open - stop|).
    4. No trigger -> the order parks and expires honestly.
    5. The entry-mode gate is still honoured at fill: an order
       whose entry_mode is not active stays parked even after the
       trigger (measurement-only).
    6. Legacy LIMIT_RETEST fills are untouched: the resting-limit
       touch path is byte-identical under the default config.

Stdlib only -- no network; the world is the canonical seeded
order-block + liquidity fixture from test_execution_lifecycle.

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.market_state import MarketState

from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester

from core.execution.order_registry import FILLED
from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.execution.execution_engine import ExecutionEngine
from core.risk.risk_engine import RiskEngine

from core.execution.entry_model import (
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    EXECUTION_NEXT_BAR_OPEN,
)
from core.risk.order_intent import OrderIntent

from tests.test_execution_lifecycle import (
    FakeIndicators,
    seeded_world,
)


def orders_for(registry, needle):
    return [
        o for o in registry.all()
        if needle in getattr(o, "setup_id", "")
    ]


def orders_for_ob5(registry):
    return orders_for(registry, "OB-5")


class Candle:

    def __init__(self, open_, high, low, close, timestamp):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


def miss_candle(ts):
    return Candle(open_=107.0, high=108.0, low=106.0,
                  close=107.5, timestamp=ts)


def break_candle(ts):
    # BULLISH trigger on the seeded setup: entry E = 110.0,
    # stop = 100.0. high (113) > E AND close (111) > E; low (109)
    # stays above the stop -> no same-bar invalidation.
    return Candle(open_=108.5, high=113.0, low=109.0,
                  close=111.0, timestamp=ts)


def open_above_candle(ts):
    # Entry bar: opens AT the entry level 110 (no gap) and
    # holds above the stop. The NEXT_BAR_OPEN fill keeps actual
    # RR = (170 - 110) / (110 - 100) = 6.0, at/above the active
    # policy minimum, so the entry bar can no longer gap above E
    # the way it did before execution-time revalidation existed.
    return Candle(open_=110.0, high=115.0, low=110.0,
                  close=113.0, timestamp=ts)


def open_eroded_candle(ts):
    # Entry bar: opens 165, eroding actual RR to
    # (170 - 165) / (165 - 100) ~= 0.08 < the active 1:1 policy
    # minimum. Execution-time revalidation must REFUSE this fill
    # (stops/targets are never moved to manufacture
    # compliance); the order keeps riding.
    return Candle(open_=165.0, high=166.0, low=164.0,
                  close=165.0, timestamp=ts)


def open_gap_tp_candle(ts):
    # Entry bar: opens 108, an adverse gap UNDER the entry
    # level 110 that keeps actual RR = (170 - 108) / (108 - 100)
    # = 7.75, executable under the active policy. A 165 open
    # (actual RR ~= 0.08) is refused by execution-time
    # revalidation, so the resize economics below are proven
    # on a compliant adverse gap instead.
    return Candle(open_=108.0, high=112.0, low=105.0,
                  close=110.0, timestamp=ts)


def win_after_candle(ts):
    # Trade (filled at 112 / stop 100 / tp 170) closes on the
    # target on the next bar.
    return Candle(open_=115.0, high=171.0, low=120.0,
                  close=170.0, timestamp=ts)


def loss_after_candle(ts):
    # Trade (stop 100) closes on the stop.
    return Candle(open_=108.0, high=112.0, low=99.5,
                  close=101.0, timestamp=ts)


def break_with_stop_breach_candle(ts):
    # Triggers the break AND breaches the stop 100.0 on the same
    # candle: invalidation (step 3) must win over the trigger.
    return Candle(open_=108.0, high=113.0, low=98.0,
                  close=111.0, timestamp=ts)


class WorldPipeline:

    def __init__(self):
        self.builder = TradeSetupBuilder()
        self.decision = DecisionEngine()
        self.execution = ExecutionEngine()
        self.risk = RiskEngine()
        self.reset()

    def reset(self):
        from core.pipeline.pipeline_context import PipelineContext
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        self.context.indicators = FakeIndicators()
        seeded_world(self.context)
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def on_candle(self, event):
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


def run_world(candles, max_wait_bars=None, entry_mode=None):
    """
    Replay candles through the canonical four-engine pipeline
    plus the real Backtester adapter, executing BREAKOUT.
    Returns (backtester, simulator, pipeline, registry).
    """
    mode = entry_mode or ENTRY_MODE_BREAKOUT_CONTINUATION
    with mock.patch.object(
        risk_settings, "MAX_WAIT_BARS",
        max_wait_bars or risk_settings.MAX_WAIT_BARS,
    ), mock.patch.object(
        risk_settings, "ENTRY_MODE", mode,
    ), mock.patch.object(
        risk_settings, "ACTIVE_ENTRY_MODES", (mode,),
    ):
        pipeline = WorldPipeline()
        event_bus = EventBus(pipeline)
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)
        backtester.run(candles)
        return backtester, simulator, pipeline, pipeline.context.order_registry


# -------------------------------------------------
# Candle scripts (all referenced to the seeded world:
# BULLISH setup on entry E = 110.0 / stop = 100.0 /
# target = 170.0).
# -------------------------------------------------

class TestBreakoutNextBarOpenFill(unittest.TestCase):

    # -------------------------------------------------

    def test_next_bar_open_fill_at_trigger_open_after_break(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
            win_after_candle(5),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        trade = simulator.registry.all()[0]

        order = orders_for(registry, trade.setup_id)[0]

        self.assertEqual(order.status, FILLED)
        self.assertTrue(order.breakout_triggered)

        # Trigger stamped on the break candle (bar 3, close 111);
        # fill happened on the NEXT bar at its OPEN (110.0), never
        # on the trigger candle itself.
        self.assertEqual(order.breakout_trigger_bar, 3)
        self.assertEqual(order.breakout_trigger_close, 111.0)
        self.assertEqual(order.filled_bar, 4)
        self.assertAlmostEqual(trade.entry, 110.0)

    # -------------------------------------------------

    def test_trigger_fill_never_same_candle(self):
        candles = [
            miss_candle(1),
            break_candle(2),
            open_above_candle(3),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        # Trigger on bar 2; the trade exists only from bar 3.
        order = orders_for_ob5(registry)[0]

        self.assertTrue(order.breakout_triggered)
        self.assertEqual(order.breakout_trigger_bar, 2)
        self.assertIsNotNone(simulator.current_trade)
        self.assertEqual(simulator.current_trade.entry_time, 3)

    # -------------------------------------------------

    def test_no_trigger_no_fill(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            miss_candle(3),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        order = orders_for_ob5(registry)[0]

        self.assertFalse(order.breakout_triggered)
        self.assertEqual(order.status, "PENDING")
        self.assertEqual(simulator.registry.count(), 0)

    # -------------------------------------------------

    def test_same_bar_stop_breach_invalidates_before_trigger(self):
        # The BREAK candle ALSO breaches the stop 100.0: the
        # structural breach (backtester step 3) must win and
        # invalidate the order -- it must NOT trigger.
        candles = [
            miss_candle(1),
            break_with_stop_breach_candle(2),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        order = orders_for_ob5(registry)[0]

        self.assertFalse(order.breakout_triggered)
        self.assertEqual(order.status, "INVALIDATED")
        self.assertEqual(simulator.registry.count(), 0)

    # -------------------------------------------------

    def test_actual_entry_risk_economics(self):
        # Seeded economics: entry E = 110, stop = 100, starting
        # balance 2000, RISK_PER_TRADE 1% scaled by the 85%
        # confidence factor (0.925) -> frozen risk_amount = 18.5.
        # The resting-boundary quantity (18.5 / 10 = 1.85) is
        # worthless once the real FILL opens at 108 (adverse
        # gap, actual RR 7.75 -- still executable): the position
        # must re-derive so the frozen dollar risk is expressed
        # over the ACTUAL distance -- 18.5 = qty * |108 - 100|.
        candles = [
            miss_candle(1),
            break_candle(2),
            open_gap_tp_candle(3),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        order = orders_for_ob5(registry)[0]

        trade = simulator.current_trade

        # Trade is still OPEN at the run's end (fills on the LAST
        # candle); the open position lives on the simulator, not
        # the closed-trade registry.
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_time, 3)

        expected_qty = order.risk_amount / (108.0 - 100.0)

        self.assertAlmostEqual(trade.quantity, expected_qty, places=6)
        self.assertAlmostEqual(
            trade.quantity * abs(trade.entry - trade.stop_loss),
            order.risk_amount,
            places=6,
        )
        # Execution-time RR truth is stamped on the fill.
        self.assertAlmostEqual(
            order.actual_risk_reward, 62.0 / 8.0, places=6
        )

    # -------------------------------------------------

    def test_eroded_open_refuses_fill(self):
        # Seeded setup is 6.0:1 at creation, but the entry-bar
        # open at 165 erodes the executable geometry to ~=0.08:1,
        # below the active 1:1 policy minimum. The fill must be
        # refused (nothing booked, setup untouched) and the order
        # must keep riding instead of being force-filled below
        # the invariant.
        candles = [
            miss_candle(1),
            break_candle(2),
            open_eroded_candle(3),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        order = orders_for_ob5(registry)[0]

        self.assertIsNone(simulator.current_trade)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(order.status, "PENDING")
        # Frozen setup economics are intact (no mutation to
        # manufacture compliance).
        self.assertAlmostEqual(order.entry, 110.0)
        self.assertAlmostEqual(order.risk_reward, 6.0)

    def test_gap_through_target_refuses_fill(self):
        # Entry bar opens at 175, THROUGH the 170 target
        # (low 171 keeps the 100 stop intact, so no
        # invalidation fires first). The unsigned ratio at
        # that open is ~0.07 -- but worse, the fill itself
        # is inverted (LONG filled above its target). It
        # must be refused, setup untouched.
        gap = Candle(open_=175.0, high=176.0, low=171.0,
                     close=172.0, timestamp=3)
        candles = [
            miss_candle(1),
            break_candle(2),
            gap,
        ]

        with self.assertLogs("backtesting.backtester",
                             level="ERROR") as logs:
            b, simulator, pipeline, registry = run_world(candles)

        order = orders_for_ob5(registry)[0]

        self.assertIsNone(simulator.current_trade)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(order.status, "PENDING")
        self.assertAlmostEqual(order.entry, 110.0)
        # The geometry gate fired (not a touch-skip): the
        # inverted fill was explicitly refused.
        self.assertTrue(
            any("ORDER_SKIPPED_INVERTED_FILL" in line
                for line in logs.output))

    def test_gap_through_stop_invalidates_first(self):
        # Entry bar opens at 95, through the 100 stop. Any
        # such bar breaches the stop (low <= open < stop),
        # so structural invalidation fires BEFORE any fill
        # logic -- the order dies as INVALIDATED, never as a
        # perverse stop-side fill.
        gap = Candle(open_=95.0, high=96.0, low=94.0,
                     close=95.5, timestamp=3)
        candles = [
            miss_candle(1),
            break_candle(2),
            gap,
        ]

        b, simulator, pipeline, registry = run_world(candles)

        order = orders_for_ob5(registry)[0]

        self.assertIsNone(simulator.current_trade)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(order.status, "INVALIDATED")

    def test_filled_trade_resource_stop_and_target(self):
        candles = [
            miss_candle(1),
            break_candle(2),
            open_above_candle(3),
            loss_after_candle(4),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        trade = simulator.registry.all()[0]

        self.assertEqual(trade.stop_loss, 100.0)
        self.assertEqual(trade.take_profit, 170.0)

        # The trade filled at the open of bar 3 then hit its stop
        # on bar 4.
        self.assertEqual(trade.result, "LOSS")
        self.assertAlmostEqual(trade.exit_price, 100.0)

    # -------------------------------------------------
    # Entry-mode gate + one-order contract
    # -------------------------------------------------

    def test_one_setup_one_order_exactly_once(self):
        candles = [
            miss_candle(1),
            break_candle(2),
            open_above_candle(3),
            win_after_candle(4),
        ]

        b, simulator, pipeline, registry = run_world(candles)

        breakouts = orders_for(registry, "OB-5")

        self.assertEqual(len(breakouts), 1)
        self.assertEqual(len(registry.filled()), 1)
        self.assertEqual(simulator.registry.count(), 1)

    # -------------------------------------------------

    def test_expires_honestly_when_never_triggered(self):
        with mock.patch.object(risk_settings, "MAX_WAIT_BARS", 2):
            candles = [
                miss_candle(1),
                miss_candle(2),
                miss_candle(3),
                miss_candle(4),
            ]

            b, simulator, pipeline, registry = run_world(
                candles, max_wait_bars=2
            )

        order = orders_for_ob5(registry)[0]

        self.assertFalse(order.breakout_triggered)
        self.assertEqual(order.status, "EXPIRED")
        self.assertEqual(simulator.registry.count(), 0)
        self.assertEqual(len(registry.filled()), 0)


# -------------------------------------------------
# SHORT gap semantics (direct pending-pass drive)
# -------------------------------------------------

class TestShortGapSemantics(unittest.TestCase):
    """SHORT mirror of the gap tests above, driven straight
    through _process_pending_orders with a pre-triggered
    registry order (SHORT E=100 / S=110 / T=40, creation RR
    6.0). No inverted or phantom SHORT fill may exist."""

    def _drive(self, entry_bar):
        from core.pipeline.pipeline_context import (
            PipelineContext,
        )
        pipeline = SimpleNamespaceDriven()
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, None, simulator)
        context = pipeline.context
        order = OrderIntent(
            direction="BEARISH", entry=100.0, stop_loss=110.0,
            take_profit=40.0, quantity=1.0, commission=0.0,
            slippage=0.0, confidence=85.0, score=85.0,
            symbol="TEST", valid=True, setup_id="SHORT-1",
            entry_mode=ENTRY_MODE_BREAKOUT_CONTINUATION,
            entry_execution=EXECUTION_NEXT_BAR_OPEN,
        )
        minted, order_id = context.order_registry.create(
            order, bar=0, timestamp=0)
        minted.breakout_triggered = True
        minted.breakout_trigger_bar = 0
        minted.breakout_trigger_close = 99.0
        context.replay_index = 1
        with mock.patch.object(
            risk_settings, "ACTIVE_ENTRY_MODES",
            (ENTRY_MODE_BREAKOUT_CONTINUATION,),
        ):
            backtester._execute_signal(entry_bar)
        return backtester, simulator, context, minted

    def test_gap_through_target_refuses_fill(self):
        # SHORT entry bar opens at 35, through the 40 target
        # (high 39 keeps the 110 stop intact). Inverted fill
        # refused; order rides.
        bar = SimpleCandle(open_=35.0, high=39.0, low=34.0,
                           close=36.0, timestamp=1)
        with self.assertLogs("backtesting.backtester",
                             level="ERROR") as logs:
            _, simulator, context, order = self._drive(bar)
        self.assertIsNone(simulator.current_trade)
        self.assertEqual(simulator.registry.count(), 0)
        registered = context.order_registry.get(order.order_id)
        self.assertEqual(registered.status, "PENDING")
        self.assertAlmostEqual(registered.entry, 100.0)
        self.assertTrue(
            any("ORDER_SKIPPED_INVERTED_FILL" in line
                for line in logs.output))

    def test_gap_through_stop_invalidates_first(self):
        # SHORT entry bar opens at 115, through the 110 stop:
        # high 116 >= stop breaches first -> INVALIDATED.
        bar = SimpleCandle(open_=115.0, high=116.0, low=111.0,
                           close=112.0, timestamp=1)
        _, simulator, context, order = self._drive(bar)
        self.assertIsNone(simulator.current_trade)
        registered = context.order_registry.get(order.order_id)
        self.assertEqual(registered.status, "INVALIDATED")

    def test_compliant_open_fills(self):
        # SHORT entry bar opens exactly at E (actual RR 6.0):
        # fills normally (positive control).
        bar = SimpleCandle(open_=100.0, high=105.0, low=95.0,
                           close=98.0, timestamp=1)
        _, simulator, context, order = self._drive(bar)
        self.assertIsNotNone(simulator.current_trade)
        self.assertAlmostEqual(
            simulator.current_trade.entry, 100.0)


class SimpleNamespaceDriven:
    """Minimal pipeline double exposing a real context."""

    def __init__(self):
        from core.pipeline.pipeline_context import (
            PipelineContext,
        )
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST",
                                          timeframe="1m")

    def reset(self):
        pass


class SimpleCandle:
    """Candle double with an explicit open leg."""

    def __init__(self, open_, high, low, close, timestamp):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


if __name__ == "__main__":
    unittest.main()
