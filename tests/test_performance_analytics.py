"""
====================================================

QuantEngine

Performance Analytics Contract Tests

Run with:

    python -m unittest tests.test_performance_analytics -v

Proves the analytics layer over the shared TradeRegistry +
Account:

    1. Empty / open-only inputs produce a zeroed report.
    2. Exact trade metrics on a deterministic win/loss mix.
    3. The trade-based equity curve follows exit order and
       matches the booked net P&L.
    4. Peak-equity drawdown is measured on the curve.
    5. Consecutive win/loss streaks from the closed series.
    6. Directional breakdown (longs vs shorts).
    7. Trade-based Sharpe / Sortino on a small series.
    8. Only-wins profit factor -> +inf; gross-loss-only -> 0.
    9. The report reconciles with a truly-booked Account
       (net_profit == realized_pnl, final_equity == balance).
   10. metrics() dict and summary() console forms.

Stdlib only -- no network, no pipeline.

====================================================
"""

import unittest

from core.backtesting.trade import Trade
from core.backtesting.trade_registry import TradeRegistry

from core.risk.account import Account

from core.analytics.performance import (
    PerformanceAnalytics,
)


def make_trade(
    pnl,
    direction="BULLISH",
    entry=100.0,
    exit_time=0,
    entry_time=0,
    bars_held=1,
    pnl_percent=None,
):
    if pnl_percent is None:
        pnl_percent = (pnl / entry) * 100 if entry else 0.0
    return Trade(
        direction=direction,
        entry=entry,
        quantity=1.0,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_price=entry + pnl,
        pnl=pnl,
        pnl_percent=pnl_percent,
        bars_held=bars_held,
        status="CLOSED",
        result="WIN" if pnl >= 0 else "LOSS",
    )


def open_trade(pnl=0.0, exit_time=0):
    trade = make_trade(pnl, exit_time=exit_time)
    trade.status = "OPEN"
    trade.result = ""
    return trade


def account_from(pnls, trades):
    account = Account(starting_balance=2000.0)
    for trade in trades:
        if trade.pnl >= 0:
            account.book_profit(trade.pnl)
        else:
            account.book_loss(-trade.pnl)
    return account


class TestPerformanceAnalytics(unittest.TestCase):

    maxDiff = None

    def test_empty_report_is_zeroed(self):

        account = Account(starting_balance=2000.0)

        report = PerformanceAnalytics.analyze(account, TradeRegistry())

        self.assertEqual(report.total_trades, 0)

        self.assertEqual(report.wins, 0)

        self.assertEqual(report.losses, 0)

        self.assertEqual(report.net_profit, 0.0)

        self.assertEqual(report.profit_factor, 0.0)

        self.assertEqual(report.equity_curve, [])

        self.assertEqual(report.final_equity, 2000.0)

    def test_open_trades_are_excluded(self):

        account = Account(starting_balance=2000.0)

        registry = TradeRegistry()

        registry.add(open_trade(pnl=100.0, exit_time=1))

        report = PerformanceAnalytics.analyze(account, registry)

        self.assertEqual(report.total_trades, 0)

        self.assertEqual(report.net_profit, 0.0)

    def test_exact_metrics_on_win_loss_mix(self):

        # WIN +10, LOSS -5, WIN +20 (exit order matters).
        trades = [
            make_trade(10.0, exit_time=1, entry_time=0),
            make_trade(-5.0, exit_time=3, entry_time=2),
            make_trade(20.0, exit_time=5, entry_time=4),
        ]

        account = account_from([10.0, -5.0, 20.0], trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertEqual(report.total_trades, 3)

        self.assertEqual(report.wins, 2)

        self.assertEqual(report.losses, 1)

        self.assertAlmostEqual(report.win_rate, 66.6667, places=3)

        self.assertAlmostEqual(report.gross_profit, 30.0, places=6)

        self.assertAlmostEqual(report.gross_loss, 5.0, places=6)

        self.assertAlmostEqual(report.profit_factor, 6.0, places=6)

        self.assertAlmostEqual(report.net_profit, 25.0, places=6)

        self.assertAlmostEqual(report.expectancy, 25.0 / 3, places=6)

        self.assertAlmostEqual(report.avg_win, 15.0, places=6)

        self.assertAlmostEqual(report.avg_loss, 5.0, places=6)

        self.assertAlmostEqual(report.payoff_ratio, 3.0, places=6)

        self.assertAlmostEqual(report.best_trade, 20.0, places=6)

        self.assertAlmostEqual(report.worst_trade, -5.0, places=6)

        self.assertAlmostEqual(report.avg_bars_held, 1.0, places=6)

        # final equity == starting + sum(pnl)
        self.assertAlmostEqual(report.final_equity, 2025.0, places=6)

    def test_equity_curve_follows_exit_order(self):

        trades = [
            make_trade(-5.0, exit_time=4, entry_time=3),
            make_trade(10.0, exit_time=1, entry_time=0),
            make_trade(20.0, exit_time=7, entry_time=6),
        ]

        account = account_from([-5.0, 10.0, 20.0], trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertEqual(
            report.equity_curve,
            [(1, 2010.0), (4, 2005.0), (7, 2025.0)],
        )

        self.assertAlmostEqual(report.peak_equity, 2025.0, places=6)

    def test_drawdown_measured_on_curve(self):

        # 2000 -> 2050 -> 2030 -> 2100  (peak 2050, trough 2030)
        trades = [
            make_trade(+50.0, exit_time=1),
            make_trade(-20.0, exit_time=2),
            make_trade(+70.0, exit_time=3),
        ]

        account = account_from([50.0, -20.0, 70.0], trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertAlmostEqual(report.max_drawdown, 20.0, places=6)

        self.assertAlmostEqual(
            report.max_drawdown_percent,
            (20.0 / 2050.0) * 100,
            places=6,
        )

        self.assertAlmostEqual(report.peak_equity, 2100.0, places=6)

    def test_consecutive_streaks(self):

        # exit order: W, W, L, W, L, L, L
        pnls = [5.0, 5.0, -5.0, 5.0, -5.0, -5.0, -5.0]

        trades = [
            make_trade(pnl, exit_time=i)
            for i, pnl in enumerate(pnls)
        ]

        account = account_from(pnls, trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertEqual(report.max_consecutive_wins, 2)

        self.assertEqual(report.max_consecutive_losses, 3)

    def test_directional_breakdown(self):

        trades = [
            make_trade(10.0, direction="BULLISH", exit_time=1),
            make_trade(-5.0, direction="BULLISH", exit_time=2),
            make_trade(7.0, direction="BEARISH", exit_time=3),
        ]

        account = Account(starting_balance=2000.0)

        for trade in trades:
            account.book_profit(trade.pnl) if trade.pnl >= 0 \
                else account.book_loss(-trade.pnl)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertEqual(report.longs, 2)

        self.assertEqual(report.shorts, 1)

        self.assertAlmostEqual(report.long_win_rate, 50.0, places=6)

        self.assertAlmostEqual(report.short_win_rate, 100.0, places=6)

    def test_sharpe_and_sortino(self):

        pnls = [10.0, -5.0, 20.0]

        trades = [
            make_trade(pnl, exit_time=i)
            for i, pnl in enumerate(pnls)
        ]

        account = account_from(pnls, trades)

        report = PerformanceAnalytics.analyze(account, trades)

        mean = sum(pnls) / 3

        std = (
            sum((p - mean) ** 2 for p in pnls) / 2
        ) ** 0.5

        self.assertAlmostEqual(
            report.sharpe,
            mean / std * (3 ** 0.5),
            places=6,
        )

        self.assertGreaterEqual(report.sortino, 0.0)

    def test_only_wins_profit_factor_infinity(self):

        trades = [
            make_trade(5.0, exit_time=1),
            make_trade(10.0, exit_time=2),
        ]

        account = account_from([5.0, 10.0], trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertEqual(report.wins, 2)

        self.assertEqual(report.losses, 0)

        self.assertEqual(report.profit_factor, float("inf"))

    def test_reconciles_with_booked_account(self):

        pnls = [10.0, -10.0, 10.0]

        trades = [
            make_trade(10.0, exit_time=1),
            make_trade(-10.0, exit_time=2),
            make_trade(10.0, exit_time=3),
        ]

        account = account_from(pnls, trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertAlmostEqual(report.net_profit, 10.0, places=6)

        self.assertAlmostEqual(
            report.net_profit,
            account.state.realized_pnl,
            places=6,
        )

        self.assertAlmostEqual(
            report.final_equity,
            account.balance,
            places=6,
        )

    def test_metrics_dict_and_summary(self):

        trades = [make_trade(10.0, exit_time=1)]

        account = account_from([10.0], trades)

        metrics = PerformanceAnalytics.metrics(account, trades)

        self.assertEqual(metrics["total_trades"], 1)

        self.assertEqual(metrics["net_profit"], 10.0)

        summary = PerformanceAnalytics.summary(
            account,
            trades,
            label="DEMO",
        )

        self.assertIn("DEMO", summary)

        self.assertIn("Net profit", summary)

    def test_accepts_plain_sequence_of_trades(self):

        trades = [make_trade(10.0, exit_time=1)]

        account = account_from([10.0], trades)

        report = PerformanceAnalytics.analyze(account, trades)

        self.assertEqual(report.total_trades, 1)


class TestCostBasisLabel12(unittest.TestCase):
    """Phase 12 economic honesty: every report states what
    its PnL prices in -- gross theoretical under zero
    modeled costs, friction-adjusted otherwise. Never
    executable, never OOS, never a live claim."""

    def test_zero_costs_labelled_gross_theoretical(self):
        trades = [make_trade(10.0, exit_time=1)]
        account = account_from([10.0], trades)
        report = PerformanceAnalytics.analyze(account, trades)
        self.assertEqual(report.total_modeled_costs, 0.0)
        self.assertIn("gross theoretical", report.cost_basis)
        self.assertIn("not executable", report.cost_basis)
        metrics = PerformanceAnalytics.metrics(account, trades)
        self.assertEqual(metrics["total_modeled_costs"], 0.0)
        self.assertIn("gross theoretical",
                      metrics["cost_basis"])
        summary = PerformanceAnalytics.summary(account, trades)
        self.assertIn("Cost basis", summary)
        self.assertIn("gross theoretical", summary)

    def test_booked_costs_labelled_friction_adjusted(self):
        trade = make_trade(10.0, exit_time=1)
        trade.commission = 2.0
        trade.slippage = 0.5
        trades = [trade]
        account = account_from([10.0], trades)
        report = PerformanceAnalytics.analyze(account, trades)
        self.assertAlmostEqual(report.total_modeled_costs, 2.5)
        self.assertIn("friction-adjusted", report.cost_basis)
        self.assertIn("not a live claim", report.cost_basis)


if __name__ == "__main__":
    unittest.main()