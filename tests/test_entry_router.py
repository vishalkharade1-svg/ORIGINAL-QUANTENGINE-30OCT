"""
====================================================

QuantEngine

Phase 5C Entry Model Router Tests

Run with:

    python -m unittest tests.test_entry_router -v

Proves the canonical Entry Model Router contract introduced in
Phase 5C:

    1. select_entry_mode() honors an explicitly carried
       entry_mode on a setup and otherwise routes the configured
       ENTRY_MODE -- the router NEVER substitutes another mode.
    2. 'AUTO' and undeclared modes RAISE (EntryModeRouterError)
       instead of silently degrading: there is no silent mode
       change between what research evaluates and what
       production executes.
    3. End-to-end ledger contract through the REAL four-engine
       pipeline: the entry_mode stamped on the order, the
       entry_execution channel, and the trade ledger ALL agree
       with the routed model -- an executed BREAKOUT run and an
       executed LIMIT_RETEST run never produce a LIMIT-filled
       order labelled BREAKOUT or vice versa.
    4. The active-mode gate parks a routed-but-inactive model
       (measurement) while the active model fills: shadow runs
       never leak into the executed ledger.

Stdlib only -- no network; the world is the canonical seeded
order-block + liquidity fixture from test_execution_lifecycle.

====================================================
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from config import risk_settings

from core.market_state import MarketState

from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.execution.execution_engine import ExecutionEngine
from core.risk.risk_engine import RiskEngine

import core.execution.entry_mode as entry_mode

from core.execution.entry_model import (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
)

import core.execution.entry_model as entry_model

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
    return Candle(open_=108.5, high=113.0, low=109.0,
                  close=111.0, timestamp=ts)


def open_above_candle(ts):
    # Phase 12: opens AT E = 110.0 (actual RR exactly 6.0)
    # so the NEXT_BAR_OPEN fill survives execution-time
    # revalidation.
    return Candle(open_=110.0, high=115.0, low=110.0,
                  close=113.0, timestamp=ts)


def loss_after_candle(ts):
    return Candle(open_=108.0, high=112.0, low=99.5,
                  close=101.0, timestamp=ts)


def limit_touch_candle(ts):
    # Rests on the seeded entry boundary E = 110.0 (low 110.0,
    # high above), never breaches the stop 100.0.
    return Candle(open_=109.5, high=112.0, low=110.0,
                  close=111.0, timestamp=ts)


def drift_after_candle(ts):
    return Candle(open_=111.0, high=118.0, low=110.5,
                  close=115.0, timestamp=ts)


def limit_loss_after_candle(ts):
    # Closes the LIMIT trade (filled at 110.0, stop 100.0) on its
    # stop: proves the executed ledger with a closed trade.
    return Candle(open_=109.5, high=112.0, low=99.5,
                  close=101.0, timestamp=ts)


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


def run_world(candles, entry_mode_=None, active_modes=None,
              max_wait_bars=None):
    """
    Replay candles through the canonical four-engine pipeline
    plus the real Backtester adapter. Returns
    (backtester, simulator, pipeline, registry).
    """
    mode = entry_mode_ or ENTRY_MODE_BREAKOUT_CONTINUATION
    active = active_modes or (mode,)
    with mock.patch.object(
        risk_settings, "MAX_WAIT_BARS",
        max_wait_bars or risk_settings.MAX_WAIT_BARS,
    ), mock.patch.object(
        risk_settings, "ENTRY_MODE", mode,
    ), mock.patch.object(
        risk_settings, "ACTIVE_ENTRY_MODES", active,
    ):
        pipeline = WorldPipeline()
        event_bus = EventBus(pipeline)
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)
        backtester.run(candles)
        return backtester, simulator, pipeline, pipeline.context.order_registry


# -------------------------------------------------
# Router unit contract
# -------------------------------------------------

class TestEntryModelRouter(unittest.TestCase):

    # -------------------------------------------------

    def test_carried_mode_wins_over_config(self):
        # A setup that was explicitly routed to BREAKOUT carries
        # that mode and keeps it, even though config says LIMIT
        # (runs always stamp the carried mode; the router must not
        # overwrite it with the config default).
        setup = SimpleNamespace(
            entry_mode=ENTRY_MODE_BREAKOUT_CONTINUATION
        )

        with mock.patch.object(
            risk_settings, "ENTRY_MODE", ENTRY_MODE_LIMIT_RETEST,
        ):
            self.assertEqual(
                entry_mode.select_entry_mode(setup),
                ENTRY_MODE_BREAKOUT_CONTINUATION,
            )

    # -------------------------------------------------

    def test_no_carried_mode_routes_configured_mode(self):
        setup = SimpleNamespace(entry_mode="")

        with mock.patch.object(
            risk_settings, "ENTRY_MODE", ENTRY_MODE_BREAKOUT_CONTINUATION,
        ):
            self.assertEqual(
                entry_mode.select_entry_mode(setup),
                ENTRY_MODE_BREAKOUT_CONTINUATION,
            )

    # -------------------------------------------------

    def test_auto_raises_loudly_never_silent_limit(self):
        # The failure mode Phase 5C forbids: config "AUTO" must
        # NEVER silently become LIMIT_RETEST in a production run.
        with mock.patch.object(
            risk_settings, "ENTRY_MODE", "AUTO",
        ):
            with self.assertRaises(entry_mode.EntryModeRouterError):
                entry_mode.select_entry_mode(SimpleNamespace(entry_mode=""))

        setup = SimpleNamespace(entry_mode="AUTO")

        with self.assertRaises(entry_mode.EntryModeRouterError):
            entry_mode.select_entry_mode(setup)

    # -------------------------------------------------

    def test_undeclared_mode_raises_loudly(self):
        setup = SimpleNamespace(entry_mode="MOONBOT")

        with self.assertRaises(entry_mode.EntryModeRouterError):
            entry_mode.select_entry_mode(setup)

    # -------------------------------------------------

    def test_declared_vocabulary_is_single_source(self):
        # entry_model (canonical) and entry_feasibility (re-export)
        # must agree with the gate the router validates against.
        declared = set(entry_mode.ENTRY_MODES)
        for key in (
            "ENTRY_MODE_LIMIT_RETEST",
            "ENTRY_MODE_MARKET_CONFIRMATION",
            "ENTRY_MODE_BREAKOUT_CONTINUATION",
            "ENTRY_MODE_FVG_RETRACE",
            "ENTRY_MODE_DISPLACEMENT_RETEST",
        ):
            self.assertIn(getattr(entry_model, key), declared)


# -------------------------------------------------
# Real-pipeline ledger contract
# -------------------------------------------------

class TestRealPipelineRouting(unittest.TestCase):

    # -------------------------------------------------

    def test_executed_breakout_ledger_matches_routed_mode(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
            loss_after_candle(5),
        ]

        b, simulator, pipeline, registry = run_world(
            candles, entry_mode_=ENTRY_MODE_BREAKOUT_CONTINUATION
        )

        order = orders_for_ob5(registry)[0]
        trade = simulator.registry.all()[0]

        self.assertEqual(order.entry_mode, ENTRY_MODE_BREAKOUT_CONTINUATION)
        self.assertEqual(order.entry_execution, "NEXT_BAR_OPEN")
        self.assertTrue(order.breakout_triggered)
        self.assertEqual(trade.entry_mode, ENTRY_MODE_BREAKOUT_CONTINUATION)
        # Phase 12: the entry bar opens AT E, so the fill
        # lands on 110.0 (actual RR exactly 6.0) and the
        # stop-out LOSS mechanics are unchanged.
        self.assertEqual(trade.entry, 110.0)
        self.assertEqual(trade.result, "LOSS")

    # -------------------------------------------------

    def test_executed_limit_ledger_matches_routed_mode(self):
        candles = [
            miss_candle(1),
            limit_touch_candle(2),
            drift_after_candle(3),
            limit_loss_after_candle(4),
        ]

        b, simulator, pipeline, registry = run_world(
            candles, entry_mode_=ENTRY_MODE_LIMIT_RETEST
        )

        order = orders_for_ob5(registry)[0]
        trade = simulator.registry.all()[0]

        self.assertEqual(order.entry_mode, ENTRY_MODE_LIMIT_RETEST)
        self.assertEqual(order.entry_execution, "LIMIT")
        self.assertFalse(order.breakout_triggered)
        self.assertEqual(trade.entry_mode, ENTRY_MODE_LIMIT_RETEST)
        self.assertEqual(trade.entry, 110.0)
        self.assertEqual(trade.result, "LOSS")

    # -------------------------------------------------

    def test_inactive_routed_model_parks_and_active_fills(self):
        candles = [
            miss_candle(1),
            limit_touch_candle(2),
            break_candle(3),
            limit_loss_after_candle(4),
        ]

        b, simulator, pipeline, registry = run_world(
            candles,
            entry_mode_=ENTRY_MODE_LIMIT_RETEST,
            active_modes=(ENTRY_MODE_LIMIT_RETEST,),
        )

        self.assertEqual(simulator.registry.count(), 1)
        trade = simulator.registry.all()[0]
        self.assertEqual(trade.entry_mode, ENTRY_MODE_LIMIT_RETEST)
        self.assertEqual(trade.entry, 110.0)


if __name__ == "__main__":
    unittest.main()