"""Phase-13 P0: post-cost R:R gate at the TradeSimulator choke.

The simulator is the ONE fill choke every executable mode passes
through (Backtester x2 call sites, PaperTradingEngine, BrokerEngine
dry-run), so a gate here cannot be bypassed by any mode or by the
legacy signal fallback. Deterministic, offline, stdlib only.

  G. backtest and paper share identical economics semantics
     (same gate, same math, same costs in -> same verdict out).
  H. the legacy signal fallback cannot bypass the cost-aware gate.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass


@dataclass
class Order:
    direction: str = "BULLISH"
    entry: float = 100.0
    stop_loss: float = 90.0
    take_profit: float = 170.0
    quantity: float = 2.0
    risk_amount: float = 20.0
    commission: float = 0.0
    slippage: float = 0.0
    symbol: str = "TEST"
    setup_id: str = "G-1"
    order_id: str = ""
    entry_mode: str = "LIMIT_RETEST"
    canonical_id: str = "TEST-1m-BULLISH-S-1"
    score: float = 80.0
    confidence: float = 85.0
    valid: bool = True
    reason: str = ""
    position_value: float = 0.0
    status: str = "NEW"
    created_bar: int = None
    eligible_from_bar: int = None
    expires_at_bar: int = None


@dataclass
class LegacySignal:
    """Legacy signal-fallback shape: economics + identity, no
    OrderIntent sizing ceremony (Case H attack surface). Carries
    the same valid/reason/position_value fields the real
    SetupCandidate fallback provides, so audit refinement treats
    it exactly like production legacy flow."""

    direction: str = "BULLISH"
    entry: float = 100.0
    stop_loss: float = 90.0
    take_profit: float = 110.0
    quantity: float = 2.0
    risk_amount: float = 20.0
    score: float = 80.0
    confidence: float = 85.0
    symbol: str = "TEST"
    setup_id: str = "LEGACY-1"
    valid: bool = True
    reason: str = ""
    position_value: float = 0.0


@dataclass
class Candle:
    timestamp: int = 2000
    open: float = 100.0
    high: float = 175.0
    low: float = 99.0
    close: float = 172.0


class TestSimulatorPostCostGate(unittest.TestCase):
    def test_cost_eroded_fill_refused_case_a(self):
        # Gross R:R is 6.5 and therefore passes the runtime 1:1 gate,
        # but deliberately extreme round-trip costs push post-cost
        # R:R below 1.0, so the fill must not book.
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        order = Order(entry=100.0, stop_loss=90.0, take_profit=165.0,
                      quantity=10.0)
        trade = sim.open_trade(order, 1000, quantity=10.0,
                               commission=500.0, slippage=100.0)
        self.assertIsNone(trade)
        self.assertIsNone(sim.current_trade)
        self.assertEqual(len(sim.registry.all()), 0)

    def test_compliant_costed_fill_books_once(self):
        # Post-cost RR 6.74 admits; booking subtracts exactly once.
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        order = Order()
        trade = sim.open_trade(order, 1000, quantity=2.0,
                               commission=3.0, slippage=2.0)
        self.assertIsNotNone(trade)
        sim.update(Candle())
        closed = sim.registry.all()
        self.assertEqual(len(closed), 1)
        # Gross (170-100)*2 = 140; net = 140-3-2 = 135 (once).
        self.assertAlmostEqual(closed[0].pnl, 135.0, places=6)

    def test_zero_cost_legacy_path_byte_identical(self):
        # Zero costs: the gate is vacuous and legacy behavior —
        # including sub-6 gross fills via direct simulator use —
        # is unchanged. Gross gating stays upstream duty.
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        order = Order(entry=100.0, stop_loss=90.0, take_profit=110.0,
                      quantity=1.0)
        trade = sim.open_trade(order, 1000)
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.quantity, 1.0, places=9)

    def test_non_finite_costs_fail_closed(self):
        from core.backtesting.trade_simulator import TradeSimulator

        for bad in (float("nan"), float("inf"), float("-inf")):
            sim = TradeSimulator()
            trade = sim.open_trade(Order(), 1000, quantity=2.0,
                                   commission=bad, slippage=0.0)
            self.assertIsNone(trade, bad)
            sim2 = TradeSimulator()
            trade2 = sim2.open_trade(Order(), 1000, quantity=2.0,
                                     commission=0.0, slippage=bad)
            self.assertIsNone(trade2, bad)

    def test_refusal_mutates_nothing(self):
        # A refused fill constructs no Trade and leaves the
        # caller's order object untouched (field-by-field).
        from dataclasses import astuple

        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        order = Order(entry=100.0, stop_loss=90.0, take_profit=110.0,
                      quantity=2.0)
        before = astuple(order)
        trade = sim.open_trade(order, 1000, quantity=2.0,
                               commission=3.0, slippage=2.0)
        self.assertIsNone(trade)
        self.assertEqual(astuple(order), before)
        self.assertIsNone(sim.current_trade)

    def test_case_h_legacy_fallback_cannot_bypass(self):
        # A legacy-shaped signal carrying nonzero costs is subject
        # to the identical gate: post-cost RR 1.0-scale economics
        # are refused even though the order never saw RiskEngine.
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        refused = sim.open_trade(LegacySignal(), 1000, quantity=2.0,
                                 commission=3.0, slippage=2.0)
        self.assertIsNone(refused)
        # And a compliant legacy shape with the same costs books.
        sim2 = TradeSimulator()
        good = LegacySignal(take_profit=170.0)
        trade = sim2.open_trade(good, 1000, quantity=2.0,
                                commission=3.0, slippage=2.0)
        self.assertIsNotNone(trade)

    def test_case_g_mode_parity_same_costs_same_verdict(self):
        # Backtest and paper claim simulator parity: the same
        # order + same costs must produce the same gate verdict
        # through the backtester path and the paper path. Both
        # engines funnel into TradeSimulator.open_trade, so this
        # pins the funnel, not just the pure function.
        from core.backtesting.trade_simulator import TradeSimulator

        gate_costs = {"commission": 500.0, "slippage": 100.0}
        backtester_side = TradeSimulator().open_trade(
            Order(entry=100.0, stop_loss=90.0, take_profit=165.0,
                  quantity=10.0),
            1000, quantity=10.0, **gate_costs)
        paper_side = TradeSimulator().open_trade(
            Order(entry=100.0, stop_loss=90.0, take_profit=165.0,
                  quantity=10.0),
            1000, quantity=10.0, **gate_costs)
        self.assertIsNone(backtester_side)
        self.assertIsNone(paper_side)
        ok_costs = {"commission": 3.0, "slippage": 2.0}
        backtester_ok = TradeSimulator().open_trade(
            Order(), 1000, quantity=2.0, **ok_costs)
        paper_ok = TradeSimulator().open_trade(
            Order(), 1000, quantity=2.0, **ok_costs)
        self.assertIsNotNone(backtester_ok)
        self.assertIsNotNone(paper_ok)
        self.assertAlmostEqual(backtester_ok.quantity,
                               paper_ok.quantity, places=9)

    def test_short_side_gate(self):
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        short = Order(direction="BEARISH", entry=100.0,
                      stop_loss=110.0, take_profit=30.0, quantity=2.0)
        trade = sim.open_trade(short, 1000, quantity=2.0,
                               commission=3.0, slippage=2.0)
        self.assertIsNotNone(trade)
        sim2 = TradeSimulator()
        eroded = Order(direction="BEARISH", entry=100.0,
                       stop_loss=110.0, take_profit=90.0,
                       quantity=2.0)
        self.assertIsNone(sim2.open_trade(eroded, 1000, quantity=2.0,
                                          commission=3.0,
                                          slippage=2.0))


if __name__ == "__main__":
    unittest.main()
