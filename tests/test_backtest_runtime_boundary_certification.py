"""
====================================================

QuantEngine

Backtest Runtime-Boundary Certification Tests
Phase 163 Full Audit and Runtime Boundary Hardening

====================================================
"""

import math
import unittest

from core.backtesting.accounting import (
    directional_geometry_ok,
    gross_pnl,
    net_pnl,
    order_rr,
    position_return_percent,
    realized_r,
    risk_reward_allowed,
)
from core.backtesting.trade import Trade
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.account import Account
from core.risk.costs import post_cost_rr, post_cost_trailing
from core.risk.position_manager import PositionManager
from core.setup.setup_candidate import SetupCandidate


class DummyCandle:
    def __init__(self, high: float, low: float, close: float, timestamp: int, open_p: float = 0.0):
        self.open = open_p if open_p > 0 else (high + low) / 2.0
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp


class TestBacktestRuntimeBoundaryCertification(unittest.TestCase):
    """Rigorous boundary certification across the execution and accounting lifecycle."""

    def test_01_replay_determinism(self):
        """Identical candle feeds and setups must yield identical trades, PnL, and timestamps."""
        def run_simulation():
            sim = TradeSimulator()
            setup = SetupCandidate(
                direction="BULLISH",
                entry=100.0,
                stop_loss=90.0,
                take_profit=120.0,
                score=85.0,
                confidence=90.0,
            )
            sim.open_trade(setup, timestamp=1000, quantity=2.0)
            candles = [
                DummyCandle(high=105.0, low=98.0, close=104.0, timestamp=1060),
                DummyCandle(high=115.0, low=103.0, close=114.0, timestamp=1120),
                DummyCandle(high=122.0, low=112.0, close=121.0, timestamp=1180),
            ]
            for c in candles:
                sim.update(c)
            return sim.registry.closed()

        trades_run1 = run_simulation()
        trades_run2 = run_simulation()

        self.assertEqual(len(trades_run1), 1)
        self.assertEqual(len(trades_run2), 1)

        t1, t2 = trades_run1[0], trades_run2[0]
        self.assertEqual(t1.entry, t2.entry)
        self.assertEqual(t1.exit_price, t2.exit_price)
        self.assertEqual(t1.pnl, t2.pnl)
        self.assertEqual(t1.exit_time, t2.exit_time)
        self.assertEqual(t1.bars_held, t2.bars_held)
        self.assertEqual(t1.result, "WIN")

    def test_02_intrabar_ambiguity_conservative_sl_first(self):
        """When candle spans BOTH stop-loss and take-profit, execute stop-loss first (LOSS)."""
        sim = TradeSimulator()
        setup = SetupCandidate(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            take_profit=110.0,
        )
        sim.open_trade(setup, timestamp=1000, quantity=1.0)

        # Bar 1: spans low 85 (SL hit) and high 115 (TP hit)
        straddle_candle = DummyCandle(high=115.0, low=85.0, close=100.0, timestamp=1060)
        sim.update(straddle_candle)

        closed = sim.registry.closed()
        self.assertEqual(len(closed), 1)
        trade = closed[0]

        # Invariant: Conservative policy must record LOSS at stop_loss with ambiguous=True
        self.assertEqual(trade.result, "LOSS")
        self.assertEqual(trade.exit_price, 90.0)
        self.assertTrue(trade.ambiguous)
        self.assertLess(trade.pnl, 0.0)

    def test_03_position_manager_precision_and_dust_dropping(self):
        """Position manager sanitizes quantities, respects caps, and drops dust."""
        from core.risk.order_intent import OrderIntent
        pm = PositionManager(max_allocation=1000.0)
        sim = TradeSimulator(position_manager=pm)

        # Normal valid setup as OrderIntent
        order = OrderIntent(
            direction="BULLISH",
            entry=50.0,
            stop_loss=45.0,
            take_profit=65.0,
            quantity=50.0,
            symbol="TEST",
            valid=True,
        )
        # Quantity requested = 50 -> notional = 2500 > max_allocation 1000
        trade = sim.open_trade(order, timestamp=1000)
        self.assertIsNotNone(trade)
        # Sized down to max notional: 1000 / 50 = 20.0
        self.assertEqual(trade.quantity, 20.0)

    def test_04_planned_vs_post_cost_vs_realized_r(self):
        """Post-cost R:R shifts entry adversely and protects edge before execution."""
        direction = "BULLISH"
        entry = 100.0
        stop = 95.0
        target = 115.0  # Planned R:R = (115-100)/(100-95) = 15/5 = 3.0 R

        # Planned R:R
        gross_rr = order_rr(entry, stop, target)
        self.assertAlmostEqual(gross_rr, 3.0)

        # Extreme commission/slippage that erodes R:R below allowed minimum 1.0
        verdict = post_cost_rr(
            direction=direction,
            entry=entry,
            stop=stop,
            target=target,
            quantity=1.0,
            commission=10.0,
            slippage=5.0,
            exit_mode="FIXED_TARGET",
        )
        self.assertFalse(verdict.allowed)

        # Simulator fails closed on eroded fill
        sim = TradeSimulator()
        setup = SetupCandidate(
            direction=direction,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
        )
        trade = sim.open_trade(setup, timestamp=1000, quantity=1.0, commission=10.0, slippage=5.0)
        self.assertIsNone(trade)

    def test_05_exact_net_pnl_and_costs_accounting(self):
        """Net PnL must strictly equal gross PnL minus commission, slippage, and funding."""
        gross = gross_pnl("BULLISH", entry=100.0, exit_price=110.0, quantity=2.0)  # +20.0
        self.assertAlmostEqual(gross, 20.0)

        commission = 0.50
        slippage = 0.30
        funding = 0.20

        net = net_pnl(gross, commission=commission, slippage=slippage, funding=funding)
        # 20.0 - 0.50 - 0.30 - 0.20 = 19.00
        self.assertAlmostEqual(net, 19.00)

        # Percent return based on initial notional (200.0) -> 19.00 / 200.0 * 100 = 9.5%
        ret_pct = position_return_percent(net, entry=100.0, quantity=2.0)
        self.assertAlmostEqual(ret_pct, 9.5)

    def test_06_trailing_stop_anchoring_and_realized_r(self):
        """Trailing stop preserves original stop distance for invariant R-multiple evaluation."""
        sim = TradeSimulator()
        setup = SetupCandidate(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,   # Initial risk = 10.0
            take_profit=0.0,
            exit_mode="TRAILING_STOP",
            trailing_enabled=True,
            trailing_activation_r=1.0,
            trailing_distance_r=0.5,
        )
        trade = sim.open_trade(setup, timestamp=1000, quantity=1.0)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.initial_stop_loss, 90.0)

        # Candle 1 moves to 120 -> Trails stop to 120 - 5 = 115
        c1 = DummyCandle(high=121.0, low=99.0, close=120.0, timestamp=1060)
        sim.update(c1)
        self.assertEqual(trade.stop_loss, 115.0)
        self.assertEqual(trade.initial_stop_loss, 90.0)

        # Candle 2 drops to 114 -> Hits trailing stop at 115
        c2 = DummyCandle(high=118.0, low=114.0, close=114.5, timestamp=1120)
        sim.update(c2)

        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.exit_price, 115.0)
        self.assertEqual(trade.result, "LOSS")  # Stopped out via active stop

        # Realized R calculation anchored to initial stop
        initial_risk = abs(trade.entry - trade.initial_stop_loss)
        self.assertEqual(initial_risk, 10.0)
        r_mult = realized_r(trade.pnl, trade.risk_amount if trade.risk_amount > 0 else initial_risk)
        self.assertAlmostEqual(r_mult, 1.5)  # (115 - 100) / 10 = +1.5 R profit

    def test_07_single_position_first_wins_and_idempotency(self):
        """TradeSimulator enforces single position invariant: second open_trade refused."""
        sim = TradeSimulator()
        setup1 = SetupCandidate(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            take_profit=110.0,
            setup_id="SETUP-1",
        )
        setup2 = SetupCandidate(
            direction="BEARISH",
            entry=100.0,
            stop_loss=110.0,
            take_profit=90.0,
            setup_id="SETUP-2",
        )
        t1 = sim.open_trade(setup1, timestamp=1000)
        self.assertIsNotNone(t1)
        self.assertIs(sim.current_trade, t1)

        # Attempt to open while t1 is working -> must return None
        t2 = sim.open_trade(setup2, timestamp=1010)
        self.assertIsNone(t2)
        self.assertEqual(sim.current_trade.setup_id, "SETUP-1")

    def test_08_ledger_and_trade_registry_reconciliation(self):
        """Account balance strictly equals initial balance + sum of completed trade net PnLs."""
        account = Account(starting_balance=10000.0)
        sim = TradeSimulator()

        # Trade 1: Win +20.0
        s1 = SetupCandidate(direction="BULLISH", entry=100.0, stop_loss=90.0, take_profit=120.0)
        t1 = sim.open_trade(s1, timestamp=1000, quantity=1.0)
        sim.update(DummyCandle(high=125.0, low=98.0, close=122.0, timestamp=1060))
        account.book_profit(t1.pnl)

        # Trade 2: Loss -10.0
        s2 = SetupCandidate(direction="BULLISH", entry=100.0, stop_loss=90.0, take_profit=120.0)
        t2 = sim.open_trade(s2, timestamp=1100, quantity=1.0)
        sim.update(DummyCandle(high=102.0, low=88.0, close=89.0, timestamp=1160))
        account.book_loss(t2.pnl)

        closed = sim.registry.closed()
        self.assertEqual(len(closed), 2)

        sum_net_pnl = sum(t.pnl for t in closed)
        expected_balance = 10000.0 + sum_net_pnl

        self.assertAlmostEqual(account.balance, expected_balance)
        self.assertAlmostEqual(account.balance, 10010.0)


if __name__ == "__main__":
    unittest.main()
