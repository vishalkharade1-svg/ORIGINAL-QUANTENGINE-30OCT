"""
Phase 9Q-11 — Intrabar ambiguity policy.
Conservative SL-first, mark ambiguous.
"""

import unittest
from dataclasses import dataclass

from core.backtesting.trade_simulator import TradeSimulator


@dataclass
class Setup:
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    quantity: float = 1.0
    risk_amount: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    symbol: str = "BTCUSDT"
    setup_id: str = "test"
    order_id: str = "ORDER-1"
    entry_mode: str = "LIMIT_RETEST"
    canonical_id: str = "BTCUSDT-1m-BULLISH-OB-1-100-90-120"
    score: float = 80
    confidence: float = 80
    valid: bool = True
    reason: str = ""
    position_value: float = 0.0


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class TestIntrabarAmbiguity(unittest.TestCase):

    def test_bullish_ambiguous_both_hit_conservative_loss(self):
        sim = TradeSimulator()
        setup = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(setup, 1000)
        # Candle hits both SL (low 85) and TP (high 115) — ambiguous
        candle = Candle(timestamp=2000, open=100, high=115, low=85, close=100)
        sim.update(candle)
        closed = sim.registry.all()[0]
        self.assertEqual(closed.result, "LOSS")
        self.assertTrue(closed.ambiguous)
        self.assertEqual(closed.exit_price, 90)

    def test_bearish_ambiguous_both_hit_conservative_loss(self):
        sim = TradeSimulator()
        setup = Setup(direction="BEARISH", entry=100, stop_loss=110, take_profit=90, quantity=1)
        sim.open_trade(setup, 1000)
        candle = Candle(timestamp=2000, open=100, high=115, low=85, close=100)
        sim.update(candle)
        closed = sim.registry.all()[0]
        self.assertEqual(closed.result, "LOSS")
        self.assertTrue(closed.ambiguous)
        self.assertEqual(closed.exit_price, 110)

    def test_bullish_only_tp_not_ambiguous(self):
        sim = TradeSimulator()
        setup = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(setup, 1000)
        candle = Candle(timestamp=2000, open=100, high=115, low=95, close=110)
        sim.update(candle)
        closed = sim.registry.all()[0]
        self.assertEqual(closed.result, "WIN")
        self.assertFalse(closed.ambiguous)
        self.assertEqual(closed.exit_price, 110)

    def test_bullish_only_sl_not_ambiguous(self):
        sim = TradeSimulator()
        setup = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(setup, 1000)
        candle = Candle(timestamp=2000, open=100, high=105, low=85, close=90)
        sim.update(candle)
        closed = sim.registry.all()[0]
        self.assertEqual(closed.result, "LOSS")
        self.assertFalse(closed.ambiguous)

    def test_no_hit_no_close(self):
        sim = TradeSimulator()
        setup = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(setup, 1000)
        candle = Candle(timestamp=2000, open=100, high=105, low=95, close=102)
        sim.update(candle)
        self.assertEqual(len(sim.registry.all()), 0)
        self.assertIsNotNone(sim.current_trade)
        self.assertFalse(sim.current_trade.ambiguous)

    def test_ambiguous_flag_persisted_in_registry(self):
        sim = TradeSimulator()
        setup = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(setup, 1000)
        candle = Candle(timestamp=2000, open=100, high=115, low=85, close=100)
        sim.update(candle)
        closed = sim.registry.all()[0]
        # Registry should preserve ambiguous
        from core.backtesting.trade_registry import TradeRegistry
        reg2 = TradeRegistry()
        reg2.add(closed)
        self.assertTrue(reg2.all()[0].ambiguous)
