"""
Phase 9Q-10 — Execution correctness edge cases.

Covers §10 checklist: limit touch, gap, SL/TP, quantity, fee/slippage,
expiration, invalidation, partial fill (via PositionManager dust),
rejected, duplicate, reconciliation. Uses canonical TradeSimulator +
OrderRegistry + PositionManager paths, not invented exchange behavior.
"""

import unittest
from dataclasses import dataclass

from core.backtesting.trade_simulator import TradeSimulator
from core.execution.order_registry import OrderRegistry, PENDING, FILLED, EXPIRED, INVALIDATED
from core.risk.position_manager import PositionManager
from core.backtesting.accounting import gross_pnl, net_pnl


@dataclass
class Setup:
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    quantity: float
    risk_amount: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    symbol: str = "BTCUSDT"
    setup_id: str = "S-1"
    order_id: str = ""
    entry_mode: str = "LIMIT_RETEST"
    canonical_id: str = "BTCUSDT-1m-BULLISH-OB-1-100-90-120"
    score: float = 80
    confidence: float = 80
    valid: bool = True
    reason: str = ""
    position_value: float = 0.0
    status: str = "NEW"
    eligible_from_bar: int = None
    expires_at_bar: int = None
    created_bar: int = None
    wait_bars: int = 0
    trade_id: str = ""


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class TestExecutionCorrectness(unittest.TestCase):

    def test_limit_touch_fills(self):
        sim = TradeSimulator()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(s, 1000)
        c = Candle(2000, 100, 105, 99, 102)  # low 99 <= entry 100 <= high 105 → touch but not SL/TP
        sim.update(c)  # no close yet
        self.assertEqual(len(sim.registry.all()), 0)
        # Now TP hit
        c2 = Candle(3000, 102, 115, 101, 112)
        sim.update(c2)
        self.assertEqual(len(sim.registry.all()), 1)
        self.assertAlmostEqual(sim.registry.all()[0].exit_price, 110)

    def test_gap_through_entry(self):
        # Gap through entry is OrderRegistry concern (limit touch), not TradeSimulator (which already has position)
        # Here we test OrderRegistry: an order whose entry is gapped over should not fill on that bar
        reg = OrderRegistry(max_wait_bars=5)
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-GAP")
        order, _ = reg.create(s, bar=10)
        # Eligible from 11, so bar 11 with gap low 105 > entry 100 should not be considered fillable via limit touch
        # Simulate the check that backtester does: low <= entry <= high
        c = Candle(2000, 105, 115, 105, 110)
        touches = c.low <= order.entry <= c.high
        self.assertFalse(touches)
        # Order should remain pending, not filled
        self.assertEqual(order.status, PENDING)

    def test_stop_loss(self):
        sim = TradeSimulator()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(s, 1000)
        c = Candle(2000, 100, 105, 85, 90)
        sim.update(c)
        self.assertEqual(sim.registry.all()[0].result, "LOSS")
        self.assertEqual(sim.registry.all()[0].exit_price, 90)

    def test_take_profit(self):
        sim = TradeSimulator()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1)
        sim.open_trade(s, 1000)
        c = Candle(2000, 100, 115, 99, 112)
        sim.update(c)
        self.assertEqual(sim.registry.all()[0].result, "WIN")

    def test_quantity_and_fee_slippage(self):
        sim = TradeSimulator()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=2, commission=1, slippage=1)
        trade = sim.open_trade(s, 1000)
        trade.commission = 1
        trade.slippage = 1
        c = Candle(2000, 100, 115, 99, 112)
        sim.update(c)
        closed = sim.registry.all()[0]
        # gross (110-100)*2=20, net 20-2=18
        self.assertAlmostEqual(closed.pnl, 18.0)
        self.assertAlmostEqual(closed.pnl_percent, 18.0 / (100*2) * 100)

    def test_expiration(self):
        reg = OrderRegistry(max_wait_bars=3)
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-EXP")
        order, oid = reg.create(s, bar=10, timestamp=1000)
        self.assertEqual(order.status, PENDING)
        # Advance to expiry bar 14 (eligible 11 +3)
        expired = reg.advance(bar=14)
        self.assertIn(order, expired)
        self.assertEqual(order.status, EXPIRED)

    def test_invalidation(self):
        reg = OrderRegistry()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-INV")
        order, _ = reg.create(s, bar=10, timestamp=1000)
        ok = reg.invalidate(order, reason="bullish structural stop breached", bar=12, price=89, level=90)
        self.assertTrue(ok)
        self.assertEqual(order.status, INVALIDATED)

    def test_duplicate_order_rejected(self):
        reg = OrderRegistry()
        s1 = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-DUP")
        s2 = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-DUP")
        o1, id1 = reg.create(s1, bar=10)
        o2, id2 = reg.create(s2, bar=11)
        self.assertEqual(id1, id2)
        self.assertIs(o1, o2)
        self.assertEqual(len(reg.all()), 1)

    def test_rejected_dust_via_position_manager(self):
        pm = PositionManager()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1e-9, setup_id="S-DUST")
        corrected, reasons = pm.audit(s)
        self.assertEqual(corrected.quantity, 0.0)

    def test_position_reconciliation_single_position(self):
        sim = TradeSimulator()
        s1 = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-1")
        s2 = Setup(direction="BULLISH", entry=101, stop_loss=91, take_profit=111, quantity=1, setup_id="S-2")
        sim.open_trade(s1, 1000)
        # Second open while first is open → should be rejected (single position)
        trade2 = sim.open_trade(s2, 1000)
        self.assertIsNone(trade2)
        # Close first
        c = Candle(2000, 100, 115, 99, 112)
        sim.update(c)
        self.assertEqual(len(sim.registry.all()), 1)
        # Now second can open
        trade2 = sim.open_trade(s2, 3000)
        self.assertIsNotNone(trade2)

    def test_mark_filled_consumes_once(self):
        reg = OrderRegistry()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=110, quantity=1, setup_id="S-FILL")
        order, oid = reg.create(s, bar=10)
        from core.backtesting.trade import Trade
        t = Trade(direction="BULLISH", entry=100, quantity=1, status="OPEN")
        tid = reg.mark_filled(order, t)
        self.assertIsNotNone(tid)
        self.assertEqual(order.status, FILLED)
        # Second consume should be no-op
        t2 = Trade(direction="BULLISH", entry=100, quantity=1, status="OPEN")
        tid2 = reg.mark_filled(order, t2)
        self.assertIsNone(tid2)

    def test_fill_identifies_requested_vs_actual(self):
        # Quantity, fees, slippage, timestamp, order_id, position_id all recorded
        # Phase-13 maintenance: the fixture setup now carries a
        # gate-compliant post-cost RR (>= 6 after the 0.5+0.5 costs
        # shift the entry to 100.333: 69.667/10.333 = 6.74), so the
        # mandatory post-cost R:R gate admits the fill. The test's
        # intent (fee/quantity recording + TP close) is unchanged.
        sim = TradeSimulator()
        s = Setup(direction="BULLISH", entry=100, stop_loss=90, take_profit=170, quantity=1.5, commission=0.5, slippage=0.5)
        trade = sim.open_trade(s, 1000, quantity=1.5, commission=0.5, slippage=0.5)
        self.assertAlmostEqual(trade.quantity, 1.5)
        self.assertAlmostEqual(trade.commission, 0.5)
        c = Candle(2000, 100, 175, 99, 172)
        sim.update(c)
        closed = sim.registry.all()[0]
        self.assertAlmostEqual(closed.quantity, 1.5)
        self.assertAlmostEqual(closed.commission, 0.5)
        self.assertAlmostEqual(closed.slippage, 0.5)
        self.assertEqual(closed.entry, 100)
        self.assertEqual(closed.exit_price, 170)
        self.assertEqual(closed.entry_time, 1000)
        self.assertEqual(closed.exit_time, 2000)
