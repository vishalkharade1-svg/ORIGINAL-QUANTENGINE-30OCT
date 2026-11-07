"""
Phase 9Q-4 + 9Q-5 — Canonical financial accounting + WIN/LOSS/BREAKEVEN.

Tests required:
- gross/net separation
- position return vs portfolio return distinction
- pnl_percent correctness
- WIN/LOSS/BREAKEVEN classification with exact zero, tiny, fee-only
- Account booking with breakeven
"""

import unittest
from dataclasses import dataclass

from core.backtesting.accounting import (
    classify_pnl,
    directional_geometry_ok,
    gross_pnl,
    is_breakeven,
    is_loss,
    is_win,
    net_pnl,
    notional,
    order_rr,
    portfolio_return_percent,
    position_return_percent,
    realized_r,
)
from core.backtesting.trade import Trade
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.account import Account


@dataclass
class FakeSetup:
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    quantity: float
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


class TestCanonicalAccounting(unittest.TestCase):

    def test_notional(self):
        self.assertAlmostEqual(notional(100, 2), 200.0)
        self.assertAlmostEqual(notional(0, 5), 0.0)

    def test_gross_pnl_long(self):
        # Long: (exit - entry)*qty
        self.assertAlmostEqual(gross_pnl("BULLISH", 100, 110, 2), 20.0)
        self.assertAlmostEqual(gross_pnl("BULLISH", 100, 90, 2), -20.0)

    def test_gross_pnl_short(self):
        self.assertAlmostEqual(gross_pnl("BEARISH", 100, 90, 2), 20.0)
        self.assertAlmostEqual(gross_pnl("BEARISH", 100, 110, 2), -20.0)

    def test_net_pnl(self):
        self.assertAlmostEqual(net_pnl(20, 1, 1), 18.0)
        self.assertAlmostEqual(net_pnl(-20, 1, 1), -22.0)
        self.assertAlmostEqual(net_pnl(0, 0, 0), 0.0)

    def test_position_return_percent(self):
        # pnl 10 on notional 200 = 5%
        self.assertAlmostEqual(position_return_percent(10, 100, 2), 5.0)
        self.assertAlmostEqual(position_return_percent(0, 100, 2), 0.0)
        self.assertAlmostEqual(position_return_percent(10, 0, 2), 0.0)

    def test_portfolio_return_percent(self):
        self.assertAlmostEqual(portfolio_return_percent(10, 200), 5.0)
        self.assertAlmostEqual(portfolio_return_percent(0, 200), 0.0)
        self.assertAlmostEqual(portfolio_return_percent(10, 0), 0.0)

    def test_realized_r(self):
        self.assertAlmostEqual(realized_r(20, 10), 2.0)
        self.assertAlmostEqual(realized_r(0, 10), 0.0)
        self.assertAlmostEqual(realized_r(10, 0), 0.0)

    def test_classify_pnl_exact(self):
        self.assertEqual(classify_pnl(10), "WIN")
        self.assertEqual(classify_pnl(-10), "LOSS")
        self.assertEqual(classify_pnl(0), "BREAKEVEN")
        self.assertTrue(is_win(10))
        self.assertTrue(is_loss(-10))
        self.assertTrue(is_breakeven(0))

    def test_classify_tiny(self):
        self.assertEqual(classify_pnl(0.0001), "WIN")
        self.assertEqual(classify_pnl(-0.0001), "LOSS")
        self.assertEqual(classify_pnl(1e-12), "WIN")

    def test_fee_only_loss(self):
        # Gross 0, commission 1 => net -1 => LOSS (fee-only)
        gross = 0.0
        net = net_pnl(gross, commission=1.0, slippage=0.0)
        self.assertEqual(classify_pnl(net), "LOSS")

    def test_gross_fee_separation_authoritative(self):
        # Net must be authoritative, gross separate
        setup = FakeSetup(direction="BULLISH", entry=100, stop_loss=90, take_profit=120, quantity=2, commission=0, slippage=0)
        sim = TradeSimulator()
        trade = sim.open_trade(setup, timestamp=1000)
        # Force commission/slippage at trade level (PositionManager may strip setup fields)
        trade.commission = 2.0
        trade.slippage = 1.0
        # Simulate close at take profit: gross (120-100)*2=40, net 40-2-1=37
        candle = Candle(timestamp=2000, open=100, high=125, low=99, close=120)
        sim.update(candle)
        closed = sim.registry.all()[0]
        self.assertAlmostEqual(closed.pnl, 37.0)
        self.assertAlmostEqual(closed.pnl_percent, 37.0 / (100*2) * 100)  # position return 18.5%
        # Ensure not the old buggy pnl/entry
        wrong = 37.0 / 100 * 100  # 37%
        self.assertNotAlmostEqual(closed.pnl_percent, wrong)

    def test_position_vs_portfolio_return_distinction(self):
        # pnl 20, notional 200, equity_before 2000
        # position return 10%, portfolio return 1%
        pnl = 20
        self.assertAlmostEqual(position_return_percent(pnl, 100, 2), 10.0)
        self.assertAlmostEqual(portfolio_return_percent(pnl, 2000), 1.0)
        self.assertNotEqual(position_return_percent(pnl, 100, 2), portfolio_return_percent(pnl, 2000))


class TestBreakevenClassification(unittest.TestCase):

    def test_account_breakeven_not_win(self):
        acc = Account(starting_balance=2000)
        # Book breakeven
        acc.book_breakeven()
        self.assertEqual(acc.state.total_trades, 1)
        self.assertEqual(acc.state.breakeven_trades, 1)
        self.assertEqual(acc.state.winning_trades, 0)
        self.assertEqual(acc.state.losing_trades, 0)
        self.assertEqual(acc.state.consecutive_wins, 0)
        self.assertEqual(acc.state.consecutive_losses, 0)

    def test_account_win_loss_breakeven_streaks(self):
        acc = Account(starting_balance=2000)
        acc.book_profit(10)  # win
        self.assertEqual(acc.state.consecutive_wins, 1)
        self.assertEqual(acc.state.consecutive_losses, 0)
        acc.book_breakeven()  # resets both
        self.assertEqual(acc.state.consecutive_wins, 0)
        self.assertEqual(acc.state.consecutive_losses, 0)
        acc.book_loss(10)  # loss
        self.assertEqual(acc.state.consecutive_losses, 1)
        acc.book_breakeven()
        self.assertEqual(acc.state.consecutive_losses, 0)

    def test_backtester_breakeven_via_simulator(self):
        # Phase193B: the simulator refuses degenerate geometry at open
        # (Trade.validate: BULLISH take_profit must be strictly above
        # entry), so this invariant is now proven on a VALID 2.0R setup
        # that exits at the observed entry price -> gross 0.0, net 0.0
        # (zero-cost legacy path) -> canonical BREAKEVEN classification.
        setup = FakeSetup(direction="BULLISH", entry=100, stop_loss=95, take_profit=115, quantity=1)
        sim = TradeSimulator()
        trade = sim.open_trade(setup, timestamp=1000)
        self.assertIsNotNone(trade)
        # Signal-exit escape hatch: close at the observed market price
        # (entry) -> gross 0.0; both commission and slippage default to
        # 0.0 on this path, so net == gross == 0.0.
        self.assertTrue(sim.request_exit(timestamp=2000, exit_price=100, reason="SIGNAL_EXIT"))
        self.assertEqual(len(sim.registry.all()), 1)
        closed = sim.registry.all()[0]
        self.assertEqual(closed.exit_price, 100.0)
        self.assertEqual(closed.pnl, 0.0)
        self.assertEqual(classify_pnl(closed.pnl), "BREAKEVEN")
        # Now book via Account
        acc = Account(starting_balance=2000)
        kind = classify_pnl(closed.pnl)
        if kind == "WIN":
            acc.book_profit(closed.pnl)
        elif kind == "LOSS":
            acc.book_loss(-closed.pnl)
        else:
            acc.book_breakeven()
        self.assertEqual(acc.state.breakeven_trades, 1)
        self.assertEqual(acc.state.winning_trades, 0)

    def test_performance_breakeven_excluded_from_wins(self):
        from core.analytics.performance import PerformanceAnalytics
        from core.backtesting.trade_registry import TradeRegistry
        acc = Account(starting_balance=2000)
        reg = TradeRegistry()
        for pnl in [10, -5, 0, 10, 0]:
            t = Trade(direction="BULLISH", entry=100, quantity=1, pnl=pnl, status="CLOSED", exit_time=1000)
            t.pnl_percent = position_return_percent(pnl, 100, 1)
            reg.add(t)
        report = PerformanceAnalytics.analyze(acc, reg)
        self.assertEqual(report.total_trades, 5)
        self.assertEqual(report.wins, 2)
        self.assertEqual(report.losses, 1)
        self.assertEqual(report.breakeven, 2)
        self.assertEqual(report.wins + report.losses + report.breakeven, report.total_trades)


class TestDirectionalGeometry12(unittest.TestCase):
    """Phase 12: LONG needs stop < entry < target, SHORT
    needs target < entry < stop. abs() RR math cannot see
    these defects, so every gate consults geometry first."""

    def test_long_valid(self):
        self.assertTrue(
            directional_geometry_ok("BULLISH", 100.0, 90.0, 160.0))

    def test_short_valid(self):
        self.assertTrue(
            directional_geometry_ok("BEARISH", 100.0, 110.0, 40.0))

    def test_long_inverted_stop_rejected(self):
        self.assertFalse(
            directional_geometry_ok("BULLISH", 100.0, 110.0, 160.0))

    def test_short_inverted_stop_rejected(self):
        self.assertFalse(
            directional_geometry_ok("BEARISH", 100.0, 90.0, 40.0))

    def test_long_inverted_target_rejected(self):
        self.assertFalse(
            directional_geometry_ok("BULLISH", 100.0, 90.0, 80.0))

    def test_short_inverted_target_rejected(self):
        self.assertFalse(
            directional_geometry_ok("BEARISH", 100.0, 110.0, 120.0))

    def test_zero_risk_rejected(self):
        self.assertFalse(
            directional_geometry_ok("BULLISH", 100.0, 100.0, 160.0))

    def test_non_finite_rejected(self):
        nan = float("nan")
        inf = float("inf")
        self.assertFalse(
            directional_geometry_ok("BULLISH", nan, 90.0, 160.0))
        self.assertFalse(
            directional_geometry_ok("BULLISH", 100.0, 90.0, inf))
        self.assertFalse(
            directional_geometry_ok("BEARISH", 100.0, 110.0, nan))
        self.assertFalse(
            directional_geometry_ok("SIDEWAYS", 100.0, 90.0, 160.0))

    def test_order_rr_values(self):
        self.assertAlmostEqual(
            order_rr(100.0, 90.0, 160.0), 6.0, places=9)
        self.assertAlmostEqual(
            order_rr(100.0, 110.0, 40.0), 6.0, places=9)
        self.assertIsNone(order_rr(100.0, 100.0, 160.0))
        self.assertIsNone(
            order_rr(float("nan"), 90.0, 160.0))
        self.assertIsNone(
            order_rr(100.0, 90.0, float("inf")))
