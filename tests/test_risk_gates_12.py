"""
====================================================

QuantEngine

Phase 12 -- risk gate regression tests.

Proves the mandatory gates on the canonical paths
(stdlib only, no network, no real pipeline):

  RiskEngine creation:
    1. inverted LONG stop rejected
    2. inverted SHORT stop rejected
    3. inverted targets rejected
    4. zero/non-finite risk rejected
    5. R:R < 6 rejected (boundary 6.0 accepted)
    6. kill switch blocks creation
    7. daily loss limit blocks at and beyond the allowance
    8. weekly/monthly limits block
    9. non-finite PnL blocks fail-closed
    10. window rollover re-enables creation
    11. fresh account passes through unchanged
  Backtester fills:
    12. sub-6:1 injected legacy order never fills
    13. inverted-stop injected order never fills
    14. kill switch blocks legacy fills
    15. kill switch blocks pending fills (diagnostics roll)
    16. MAX_OPEN_POSITIONS: no second fill while open
  Paper:
    17. kill switch blocks paper fills

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account import Account, roll_state_pnl_windows
from core.risk.order_intent import OrderIntent
from core.risk.risk_engine import (
    RiskEngine,
    kill_switch_active,
    loss_limit_blocked,
)
from core.setup.setup_candidate import SetupCandidate


def signal(direction="BULLISH", entry=100.0, stop=90.0,
           tp=160.0, confidence=85.0, score=85.0):
    return SetupCandidate(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        risk_reward=(
            abs(tp - entry) / abs(entry - stop)
            if entry != stop else 0.0
        ),
        confidence=confidence,
        score=score,
        setup_id="S-12",
    )


def fresh_state(balance=2000.0):
    account = Account(starting_balance=balance)
    return account.state


def analyze(signal, state):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.execution_signal = signal
    context.account = state
    RiskEngine().analyze(context)
    return context.order


class TestRiskEngineGeometry12(unittest.TestCase):

    def test_inverted_long_stop_rejected(self):
        self.assertIsNone(analyze(
            signal("BULLISH", 100.0, 110.0, 160.0),
            fresh_state()))

    def test_inverted_short_stop_rejected(self):
        self.assertIsNone(analyze(
            signal("BEARISH", 100.0, 90.0, 40.0),
            fresh_state()))

    def test_inverted_long_target_rejected(self):
        self.assertIsNone(analyze(
            signal("BULLISH", 100.0, 90.0, 80.0),
            fresh_state()))

    def test_inverted_short_target_rejected(self):
        self.assertIsNone(analyze(
            signal("BEARISH", 100.0, 110.0, 120.0),
            fresh_state()))

    def test_zero_risk_rejected(self):
        self.assertIsNone(analyze(
            signal("BULLISH", 100.0, 100.0, 160.0),
            fresh_state()))

    def test_non_finite_rejected(self):
        nan = float("nan")
        self.assertIsNone(analyze(
            signal("BULLISH", nan, 90.0, 160.0),
            fresh_state()))
        self.assertIsNone(analyze(
            signal("BULLISH", 100.0, 90.0, nan),
            fresh_state()))

    def test_below_minimum_rr_rejected(self):
        self.assertIsNone(analyze(
            signal("BULLISH", 100.0, 90.0, 105.0),
            fresh_state()))

    def test_boundary_rr_accepted(self):
        order = analyze(
            signal("BULLISH", 100.0, 90.0, 160.0),
            fresh_state())
        self.assertIsNotNone(order)
        self.assertTrue(order.valid)

    def test_kill_switch_blocks_creation(self):
        state = fresh_state()
        state.kill_switch = True
        self.assertTrue(kill_switch_active(state))
        self.assertIsNone(analyze(
            signal(), state))

    def test_trading_disabled_blocks_creation(self):
        state = fresh_state()
        state.trading_enabled = False
        self.assertIsNone(analyze(
            signal(), state))


class TestLossLimits12(unittest.TestCase):

    def test_fresh_account_passes(self):
        self.assertIsNone(loss_limit_blocked(fresh_state()))
        order = analyze(signal(), fresh_state())
        self.assertIsNotNone(order)

    def test_daily_limit_blocks_beyond_allowance(self):
        state = fresh_state(balance=2000.0)
        state.daily_pnl = -39.99
        self.assertIsNone(loss_limit_blocked(state))
        state.daily_pnl = -40.0
        self.assertEqual(
            loss_limit_blocked(state), "DAILY_LOSS_LIMIT")
        state.daily_pnl = -400.0
        self.assertEqual(
            loss_limit_blocked(state), "DAILY_LOSS_LIMIT")
        # Creation stops while the window is blown.
        self.assertIsNone(analyze(signal(), state))

    def test_weekly_and_monthly_limits_block(self):
        state = fresh_state(balance=2000.0)
        state.weekly_pnl = -100.0  # 5% of 2000
        self.assertEqual(
            loss_limit_blocked(state), "WEEKLY_LOSS_LIMIT")
        state.weekly_pnl = 0.0
        state.monthly_pnl = -200.0  # 10% of 2000
        self.assertEqual(
            loss_limit_blocked(state), "MONTHLY_LOSS_LIMIT")

    def test_non_finite_pnl_blocks_fail_closed(self):
        state = fresh_state()
        state.daily_pnl = float("nan")
        self.assertEqual(
            loss_limit_blocked(state), "DAILY_LOSS_NON_FINITE")

    def test_window_rollover_reenables(self):
        state = fresh_state(balance=2000.0)
        # Seed the window key first (first sighting never
        # fabricates a boundary), then blow the window.
        roll_state_pnl_windows(state, 1788912000)  # 2026-09-09
        state.daily_pnl = -500.0
        self.assertIsNotNone(loss_limit_blocked(state))
        # Next UTC day rolls the window (deterministic from
        # candle timestamps, no wall clock).
        roll_state_pnl_windows(state, 1788912000 + 86400)
        self.assertEqual(state.daily_pnl, 0.0)
        self.assertIsNone(loss_limit_blocked(state))
        self.assertIsNotNone(analyze(signal(), state))

    def test_roll_seeds_without_resetting(self):
        state = fresh_state()
        state.daily_pnl = -10.0
        roll_state_pnl_windows(state, 1788912000)
        # First sighting seeds the key; the live window keeps
        # its PnL (no fabricated boundary on missing history).
        self.assertEqual(state.daily_pnl, -10.0)
        self.assertTrue(state.pnl_day_key)
        roll_state_pnl_windows(state, 1788912000 + 86400)
        self.assertEqual(state.daily_pnl, 0.0)

    def test_missing_timestamp_rolls_nothing(self):
        state = fresh_state()
        state.daily_pnl = -10.0
        roll_state_pnl_windows(state, None)
        roll_state_pnl_windows(state, "not-a-time")
        self.assertEqual(state.daily_pnl, -10.0)
        self.assertEqual(state.pnl_day_key, "")


class Candle:

    def __init__(self, high, low, close, timestamp):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


class FakeEventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


class FakePipeline:

    def __init__(self, script):
        self.script = script
        self._idx = 0
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST",
                                          timeframe="1m")
        self._idx = 0

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        order, sig = self.script.get(self._idx, (None, None))
        self.context.order = order
        self.context.execution_signal = sig
        self._idx += 1


def legacy_order(entry=100.0, stop=98.5, tp=160.0,
                 quantity=1.0):
    return OrderIntent(
        direction="BULLISH", entry=entry, stop_loss=stop,
        take_profit=tp, quantity=quantity, commission=0.0,
        slippage=0.0, confidence=85.0, score=85.0,
        symbol="TEST", valid=True, setup_id="LEG-1",
    )


SAFE = dict(high=105.0, low=99.0, close=102.0)
EXIT_WIN = dict(high=165.0, low=101.0, close=164.0)


def run_backtest(candles, script):
    from core.backtesting.trade_simulator import TradeSimulator
    from backtesting.backtester import Backtester
    pipeline = FakePipeline(script)
    simulator = TradeSimulator()
    backtester = Backtester(pipeline, FakeEventBus(pipeline),
                            simulator)
    backtester.run(candles)
    return backtester, simulator


class TestBacktesterFillGates12(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(
            risk_settings, "ACTIVE_ENTRY_MODES", ("LIMIT_RETEST",))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_below_minimum_rr_injected_order_never_fills(self):
        candles = [Candle(**SAFE, timestamp=0),
                   Candle(**EXIT_WIN, timestamp=1)]
        _, simulator = run_backtest(
            candles,
            {0: (legacy_order(stop=90.0, tp=105.0), None)})
        self.assertEqual(simulator.registry.count(), 0)
        self.assertIsNone(simulator.current_trade)

    def test_inverted_stop_injected_order_never_fills(self):
        candles = [Candle(**SAFE, timestamp=0),
                   Candle(**EXIT_WIN, timestamp=1)]
        _, simulator = run_backtest(
            candles,
            {0: (legacy_order(stop=110.0, tp=160.0), None)})
        self.assertEqual(simulator.registry.count(), 0)
        self.assertIsNone(simulator.current_trade)

    def test_kill_switch_blocks_legacy_fills(self):
        # The restart-persistent env override is the kill path
        # that survives Backtester.run()'s account reset (an
        # in-memory flag set before run() would be replaced by
        # the reset -- recovery requires explicit operator
        # action either way).
        import os
        candles = [Candle(**SAFE, timestamp=0),
                   Candle(**EXIT_WIN, timestamp=1)]
        pipeline = FakePipeline(
            {0: (legacy_order(), None)})
        from core.backtesting.trade_simulator import TradeSimulator
        from backtesting.backtester import Backtester
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, FakeEventBus(pipeline),
                                simulator)
        with mock.patch.dict(
                os.environ, {"QE_KILL_SWITCH": "1"}):
            backtester.run(candles)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertIsNone(simulator.current_trade)

    def test_kill_switch_blocks_pending_fills(self):
        # Registry-managed order, driven candle by candle:
        # bar 0 creates (ineligible creation candle), bar 1
        # is eligible but the kill switch refuses the fill
        # while diagnostics still roll, bar 2 fills after the
        # switch clears.
        from core.backtesting.trade_simulator import TradeSimulator
        from backtesting.backtester import Backtester
        pipeline = FakePipeline({})
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, FakeEventBus(pipeline),
                                simulator)
        context = pipeline.context
        minted, order_id = context.order_registry.create(
            legacy_order(), bar=0, timestamp=0)

        context.replay_index = 0
        backtester._execute_signal(Candle(**SAFE, timestamp=0))

        backtester.account.state.kill_switch = True
        context.replay_index = 1
        backtester._execute_signal(Candle(**SAFE, timestamp=1))

        self.assertEqual(simulator.registry.count(), 0)
        self.assertIsNone(simulator.current_trade)
        registered = context.order_registry.get(order_id)
        self.assertEqual(registered.status, "PENDING")
        # Diagnostics rolled while the fill was refused.
        self.assertGreaterEqual(registered.bars_pending, 1)

        backtester.account.state.kill_switch = False
        context.replay_index = 2
        backtester._execute_signal(Candle(**SAFE, timestamp=2))
        self.assertIsNotNone(simulator.current_trade)

    def test_max_open_positions_single_slot(self):
        # MAX_OPEN_POSITIONS = 1 is enforced structurally by
        # the single-position simulator slot: a competing
        # order while a position is open is ignored.
        self.assertEqual(risk_settings.MAX_OPEN_POSITIONS, 1)
        candles = [Candle(**SAFE, timestamp=0),
                   Candle(**SAFE, timestamp=1),
                   Candle(**EXIT_WIN, timestamp=2)]
        script = {i: (legacy_order(tp=130.0), None) for i in range(3)}
        _, simulator = run_backtest(candles, script)
        self.assertEqual(simulator.registry.count(), 1)
        trade = simulator.registry.all()[0]
        self.assertEqual(trade.entry_time, 0)
        self.assertEqual(trade.exit_time, 2)


class TestPaperKillSwitch12(unittest.TestCase):

    def test_kill_switch_blocks_paper_fills(self):
        from core.paper_trading.paper_trading_engine import (
            PaperTradingEngine,
        )
        pipeline = FakePipeline({0: (legacy_order(), None)})
        engine = PaperTradingEngine(pipeline, event_bus=None)
        engine.account.state.kill_switch = True
        engine.run_candle(Candle(**SAFE, timestamp=1))
        self.assertIsNone(engine.simulator.current_trade)
        self.assertEqual(engine.simulator.registry.count(), 0)


if __name__ == "__main__":
    unittest.main()
