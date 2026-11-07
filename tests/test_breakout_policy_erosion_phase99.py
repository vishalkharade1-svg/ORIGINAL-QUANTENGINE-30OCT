"""Phase 99: breakout erosion enforces the ACTIVE minimum-R policy (no hard 6R).

The backtester BREAKOUT_CONTINUATION erosion gate must read
trading_policy() for the order's symbol -- global default 1:1..1:20 or an
exact-instrument override -- and never a hardcoded 6R floor.

Uses the NamespaceDriven harness pattern (hand-minted breakout order with
pre-stamped trigger, direct _execute_signal drive). Symbol TEST99 isolates
the instrument-override cases; overrides are always reset (persisted
removal) so no state leaks between tests.
"""
import unittest
from unittest import mock

from config import risk_settings
from core.execution.entry_model import (
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    EXECUTION_NEXT_BAR_OPEN,
)


class SimpleCandle:
    def __init__(self, open_, high, low, close, timestamp):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST99"
        self.timeframe = "1m"


class NamespaceDriven:
    def __init__(self):
        from core.pipeline.pipeline_context import PipelineContext
        from core.market_state import MarketState
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST99", timeframe="1m")

    def reset(self):
        pass


def drive_breakout(*, entry, stop, target, fill_open, fill_high,
                   fill_low, symbol="TEST99"):
    """Mint a triggered breakout order, drive one fill bar, return state."""
    from core.backtesting.trade_simulator import TradeSimulator
    from backtesting.backtester import Backtester
    from core.risk.order_intent import OrderIntent
    pipeline = NamespaceDriven()
    simulator = TradeSimulator()
    backtester = Backtester(pipeline, None, simulator)
    context = pipeline.context
    order = OrderIntent(
        direction="BULLISH", entry=entry, stop_loss=stop,
        take_profit=target, quantity=1.0, commission=0.0,
        slippage=0.0, confidence=85.0, score=85.0,
        symbol=symbol, valid=True, setup_id="ER-1",
        entry_mode=ENTRY_MODE_BREAKOUT_CONTINUATION,
        entry_execution=EXECUTION_NEXT_BAR_OPEN,
    )
    minted, _ = context.order_registry.create(order, bar=0, timestamp=0)
    minted.breakout_triggered = True
    minted.breakout_trigger_bar = 0
    minted.breakout_trigger_close = entry
    context.replay_index = 1
    bar = SimpleCandle(open_=fill_open, high=fill_high, low=fill_low,
                       close=fill_open, timestamp=1)
    with mock.patch.object(
        risk_settings, "ACTIVE_ENTRY_MODES",
        (ENTRY_MODE_BREAKOUT_CONTINUATION,),
    ):
        backtester._execute_signal(bar)
    registered = context.order_registry.get(minted.order_id)
    return simulator, registered


class ErosionPolicyCase(unittest.TestCase):
    OVERRIDE_SYMBOL = "TEST99"

    def tearDown(self):
        from core.risk.trading_policy import trading_policy_manager
        trading_policy_manager().reset_instrument(self.OVERRIDE_SYMBOL)

    def set_min_rr(self, minimum):
        from core.risk.trading_policy import trading_policy_manager
        trading_policy_manager().set_instrument(
            self.OVERRIDE_SYMBOL, {"min_rr": float(minimum)})

    def test_two_r_breakout_fills_under_default_policy(self):
        # Setup 110/100/130; fill-bar open 110 -> actual RR exactly
        # 2.0. Default active minimum is 1R: must FILL (the removed
        # hardcoded 6R floor refused exactly this case).
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=110.0, fill_high=115.0, fill_low=105.0)
        self.assertEqual(order.status, "FILLED")
        self.assertIsNotNone(sim.current_trade)
        self.assertAlmostEqual(sim.current_trade.entry, 110.0)
        self.assertAlmostEqual(order.actual_risk_reward, 2.0)

    def test_below_configured_minimum_refused(self):
        # Same setup; fill-bar open 125 -> actual RR 0.2 < 1R:
        # refused, order keeps riding, no trade, no mutation.
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=125.0, fill_high=128.0, fill_low=124.0)
        self.assertIsNone(sim.current_trade)
        self.assertEqual(order.status, "PENDING")
        self.assertEqual(order.entry, 110.0)

    def test_six_r_enforced_when_explicitly_configured(self):
        # Operator sets min 6R for this instrument: the 2R fill above
        # is now refused...
        self.set_min_rr(6.0)
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=110.0, fill_high=115.0, fill_low=105.0)
        self.assertIsNone(sim.current_trade)
        self.assertEqual(order.status, "PENDING")
        # ...while an exact-6R fill is still accepted.
        sim2, order2 = drive_breakout(
            entry=100.0, stop=90.0, target=160.0,
            fill_open=100.0, fill_high=105.0, fill_low=95.0)
        self.assertEqual(order2.status, "FILLED")
        self.assertIsNotNone(sim2.current_trade)

    def test_favorable_gap_cannot_exceed_configured_maximum_rr(self):
        # The setup is 2R at 110, but a favorable gap to 101 with a stop at
        # 100 creates 29R. The max-R gate must reject it rather than letting
        # the erosion path enforce only the minimum.
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=101.0, fill_high=103.0, fill_low=100.5)
        self.assertIsNone(sim.current_trade)
        self.assertEqual(order.status, "PENDING")
        self.assertEqual(order.entry, 110.0)

    def test_invalid_geometry_refused_regardless_of_r(self):
        # Fill-bar open at/below the stop: the structural stop breach
        # (low <= stop) invalidates BEFORE any fill evaluation, so no
        # trade can book regardless of any R threshold.
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=95.0, fill_high=112.0, fill_low=94.0)
        self.assertIsNone(sim.current_trade)
        self.assertEqual(order.status, "INVALIDATED")

    def test_fill_at_target_refused_by_geometry(self):
        # Fill-bar open exactly at target (no stop breach): strict
        # geometry refuses the fill and the order rides PENDING.
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=130.0, fill_high=132.0, fill_low=128.0)
        self.assertIsNone(sim.current_trade)
        self.assertEqual(order.status, "PENDING")

    def test_no_settings_floor_in_backtester_fill_path(self):
        # Structural pin: the frozen research constant must not
        # govern any backtester fill/refusal path anymore.
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "backtesting" /
                "backtester.py").read_text(encoding="utf-8")
        self.assertNotIn("MIN_RISK_REWARD", text)
        self.assertNotIn("6R", text)
        self.assertIn("trading_policy(", text)


if __name__ == "__main__":
    unittest.main()
