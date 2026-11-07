"""
====================================================

QuantEngine

Position Manager Tests

Run with:

    python -m unittest tests.test_position_manager -v

Proves the live PositionManager -- deliberately the INVERSE of
the archived legacy one (which owned its own Position + SL/TP
state). The live manager is pure order refinement + a read-only
snapshot reader: it keeps NO position state of its own.

    1. Quantity rounding to QUANTITY_PRECISION decimals.
    2. Notional capping at MAX_ALLOCATION_PER_TRADE (quantity
       scaled back), and the LEVERAGE * equity cap via
       manage_into.
    3. Dust drop: quantity below MIN_QUANTITY invalidates the
       order (quantity -> 0).
    4. Purity: the input OrderIntent is NEVER mutated; manage
       is idempotent.
    5. Audit reasons describe every adjustment applied.
    6. Non-dataclass order shapes (paper slippage wrapper) are
       refined through a pure proxy -- originals untouched,
       full field passthrough.
    7. SetupCandidate-style fallback (no quantity/entry) passes
       through unchanged.
    8. Unrealized PnL + snapshot are exact reads over a shared
       Trade (bull + bear).
    9. Integration through the canonical flow: a Backtester and
       a PaperTradingEngine (slippage wrapper path included)
       both book the refined quantity; dust orders open nothing.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent
from core.backtesting.trade import Trade
from core.backtesting.trade_simulator import TradeSimulator

from core.risk.position_manager import PositionManager

from backtesting.backtester import Backtester

from core.paper_trading.paper_trading_engine import (
    PaperTradingEngine,
)


MAX_ALLOC = 500.0


# Phase 12: stop 0.95 keeps the gated legacy path green
# (0.30 / 0.05 = 6.0:1 exactly -- the inclusive boundary);
# quantity-refinement mechanics below are unchanged.
def order(
    entry=100.0,
    quantity=1.0,
    valid=True,
):
    return OrderIntent(
        direction="BULLISH",
        entry=entry,
        stop_loss=entry * 0.95,
        take_profit=entry * 1.30,
        quantity=quantity,
        position_value=entry * quantity,
        symbol="TEST",
        valid=valid,
        risk_amount=1.0,
    )


class PlainOrder:
    """Non-dataclass order-like object (paper wrapper shape)."""

    def __init__(self, entry, quantity, direction="BULLISH"):
        self.entry = entry
        self.quantity = quantity
        self.direction = direction
        self.stop_loss = 95.0
        self.take_profit = 110.0


class BeautifulCandleProperties:
    pass


class Candle:

    def __init__(self, high, low, close, timestamp, symbol="TEST"):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = symbol
        self.timeframe = "1m"


SAFE = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)


class FakePipeline:

    def __init__(self, intent):
        self.intent = intent
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.context.order = self.intent
        self.context.execution_signal = None


class FakeEventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


class TestPositionManager(unittest.TestCase):

    maxDiff = None

    def test_rounds_quantity(self):
        manager = PositionManager()
        self.assertEqual(
            manager.round_quantity(1.234567891),
            1.23456789,
        )

    def test_notional_cap_scales_quantity(self):
        manager = PositionManager()
        corrected, reasons = manager.audit(
            order(entry=1000.0, quantity=10.0)
        )

        self.assertAlmostEqual(corrected.quantity, 0.5, places=8)
        self.assertAlmostEqual(corrected.position_value, 500.0, places=6)
        self.assertTrue(corrected.valid)
        self.assertTrue(any("capped" in r for r in reasons))
        self.assertAlmostEqual(corrected.entry, 1000.0, places=6)

    def test_leverage_cap_with_equity(self):
        manager = PositionManager(max_allocation=1e9, leverage=10.0)
        corrected, _ = manager.audit(
            order(entry=1000.0, quantity=20.0),
            equity=1000.0,
        )

        # leverage 10 * equity 1000 = 10,000 notional -> qty 10
        self.assertAlmostEqual(corrected.quantity, 10.0, places=8)

        managed = manager.manage_into(
            order(entry=1000.0, quantity=20.0),
            equity=1000.0,
        )

        self.assertAlmostEqual(managed.quantity, 10.0, places=8)

    def test_dust_invalidates_order(self):
        manager = PositionManager()
        corrected, reasons = manager.audit(
            order(quantity=1e-9)
        )

        self.assertEqual(corrected.quantity, 0.0)
        self.assertFalse(corrected.valid)
        self.assertTrue(any("dust" in r for r in reasons))
        self.assertIn("below minimum", corrected.reason)

    def test_manage_is_pure_and_idempotent(self):
        manager = PositionManager()
        original = order(entry=1000.0, quantity=10.0)

        corrected = manager.manage(original)

        # original untouched
        self.assertEqual(original.quantity, 10.0)
        self.assertTrue(original.valid)

        # idempotent
        again = manager.manage(corrected)
        self.assertEqual(again.quantity, corrected.quantity)
        self.assertEqual(again.position_value, corrected.position_value)

    def test_no_adjustment_when_already_clean(self):
        manager = PositionManager()
        corrected, reasons = manager.audit(order())

        self.assertEqual(corrected.quantity, 1.0)
        self.assertTrue(corrected.valid)
        self.assertEqual(reasons, [])

    def test_plain_order_refined_through_proxy(self):
        manager = PositionManager()
        plain = PlainOrder(entry=1000.0, quantity=10.0)

        corrected = manager.manage(plain)

        self.assertAlmostEqual(corrected.quantity, 0.5, places=8)
        self.assertAlmostEqual(corrected.position_value, 500.0, places=6)
        self.assertEqual(corrected.stop_loss, 95.0)
        self.assertEqual(corrected.take_profit, 110.0)
        self.assertEqual(corrected.direction, "BULLISH")
        # original untouched
        self.assertEqual(plain.quantity, 10.0)

    def test_setup_candidate_shape_passes_through(self):
        manager = PositionManager()

        class SetupCandidate:
            entry = 100.0
            stop_loss = 95.0
            take_profit = 110.0
            direction = "BULLISH"

        candidate = SetupCandidate()

        self.assertIs(manager.manage(candidate), candidate)

    def test_unrealized_bull_and_bear(self):
        manager = PositionManager()

        bull = Trade(
            direction="BULLISH",
            entry=100.0,
            quantity=2.0,
        )
        self.assertAlmostEqual(
            manager.unrealized(bull, 105.0), 10.0, places=6
        )
        self.assertAlmostEqual(
            manager.unrealized(bull, 95.0), -10.0, places=6
        )

        bear = Trade(
            direction="BEARISH",
            entry=100.0,
            quantity=2.0,
        )
        self.assertAlmostEqual(
            manager.unrealized(bear, 105.0), -10.0, places=6
        )
        self.assertAlmostEqual(
            manager.unrealized(bear, 95.0), 10.0, places=6
        )

    def test_snapshot_view(self):
        manager = PositionManager()
        trade = Trade(
            direction="BULLISH",
            entry=100.0,
            quantity=2.0,
            symbol="TEST",
        )

        snap = manager.snapshot(trade, 105.0)

        self.assertEqual(snap["symbol"], "TEST")
        self.assertAlmostEqual(snap["position_value"], 200.0, places=6)
        self.assertAlmostEqual(snap["unrealized_pnl"], 10.0, places=6)
        self.assertAlmostEqual(
            snap["unrealized_percent"], 5.0, places=6
        )
        self.assertEqual(snap["state"], "WIN")
        self.assertEqual(snap["direction"], "BULLISH")

        flat = manager.snapshot(trade, 100.0)
        self.assertEqual(flat["state"], "FLAT")


class TestIntegration(unittest.TestCase):

    def test_backtester_books_refined_quantity(self):
        # entry 100 -> cap threshold MAX_ALLOC/entry = 5.0
        pipeline = FakePipeline(order(entry=100.0, quantity=10.0))
        engine = Backtester(
            pipeline,
            FakeEventBus(pipeline),
            TradeSimulator(),
        )
        engine.run([SAFE])

        trade = engine.simulator.current_trade
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.quantity, 5.0, places=8)

    def test_dust_order_opens_nothing(self):
        pipeline = FakePipeline(order(quantity=1e-9))
        engine = Backtester(
            pipeline,
            FakeEventBus(pipeline),
            TradeSimulator(),
        )
        engine.run([SAFE])

        self.assertIsNone(engine.simulator.current_trade)
        self.assertEqual(len(engine.trades.all()), 0)

    def test_paper_slippage_wrapper_still_refined(self):
        # The paper engine wraps the intent in the slippage
        # adapter when fill_slippage_bps > 0; the refined
        # quantity still reaches the trade through the proxy.
        pipeline = FakePipeline(order(entry=100.0, quantity=10.0))
        engine = PaperTradingEngine(
            pipeline,
            event_bus=None,
            fill_slippage_bps=10.0,
        )
        engine.run_candle(SAFE)

        trade = engine.current_trade
        self.assertIsNotNone(trade)
        # notional 1000 > 500 -> quantity capped to 500/100.1
        # (the cap is keyed to the slipped fill entry)
        self.assertAlmostEqual(
            trade.quantity, 500.0 / 100.1, places=6
        )
        self.assertAlmostEqual(
            trade.quantity * trade.entry, 500.0, places=3
        )
        self.assertAlmostEqual(trade.entry, 100.1, places=6)

    def test_clean_order_unchanged_through_flow(self):
        pipeline = FakePipeline(order())
        engine = Backtester(
            pipeline,
            FakeEventBus(pipeline),
            TradeSimulator(),
        )
        engine.run([SAFE])

        trade = engine.simulator.current_trade
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.quantity, 1.0, places=8)


if __name__ == "__main__":
    unittest.main()