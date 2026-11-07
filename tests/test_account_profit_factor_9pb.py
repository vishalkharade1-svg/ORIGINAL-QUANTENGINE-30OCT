"""
====================================================

QuantEngine

Account Profit Factor / Expectancy Reporting (9P-b)

Run with:

    python -m unittest tests.test_account_profit_factor_9pb -v

Scope

    Proves that profit factor and expectancy are reported
    correctly from the canonical completed-trade ledger and
    that the account-level state exposes no duplicate surface.

    Canonical source: core.backtesting.TradeRegistry closed
    trades (status == "CLOSED"); Trade.pnl is the per-trade
    NET P&L (gross minus commission minus slippage, as booked
    by the simulator).

    Canonical calculation: core.analytics.performance
    (PerformanceAnalytics / PerformanceReport).

    Deterministic edge cases covered:

        1. Mixed wins / losses / breakeven
           [+100, +200, -50, -100, 0] ->
           gross_profit 300, gross_loss 150, profit_factor 2.0,
           total 5, wins 2, losses 2, breakeven 1,
           net_profit 150, expectancy 30.0
        2. All winning   -> profit_factor == inf (no losses)
        3. All losing    -> profit_factor == 0.0 (no gross profit)
        4. Breakeven only -> neither win nor loss; PF 0.0
        5. Empty (no completed trades) -> missing-value 0.0
        6. Negative expectancy preserved
        7. Breakeven excluded from win/loss & gross, but still
           counted in the expectancy divisor
        8. Open positions excluded
        9. Deterministic repeated calculation (idempotent)
       10. Costs honored: gross sums use net Trade.pnl
       11. Account exposes NO duplicate profit_factor/expectancy
           fields (single canonical calculation enforced)

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


def closed_trade(pnl, exit_time=0, entry_time=0, direction="BULLISH"):
    """A CLOSED trade carrying a given NET P&L."""
    return Trade(
        direction=direction,
        entry=100.0,
        quantity=1.0,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_price=100.0 + pnl,
        pnl=pnl,
        pnl_percent=(pnl / 100.0) if pnl else 0.0,
        bars_held=1,
        status="CLOSED",
        result="WIN" if pnl > 0 else ("LOSS" if pnl < 0 else ""),
    )


def open_trade(pnl=0.0, exit_time=0):
    trade = closed_trade(pnl, exit_time=exit_time)
    trade.status = "OPEN"
    trade.result = ""
    return trade


def analyze(pnls):
    """Analyze a list of net-P&L values as closed trades."""
    account = Account(starting_balance=2000.0)
    trades = [
        closed_trade(pnl, exit_time=i)
        for i, pnl in enumerate(pnls)
    ]
    return PerformanceAnalytics.analyze(account, trades)


class TestProfitFactorExpectancy9Pb(unittest.TestCase):

    maxDiff = None

    def test_required_fixture_breakeven_is_neutral(self):
        # The task-specified deterministic fixture: +100 +200
        # -50 -100 0. Breakeven (0) is NEITHER win NOR loss.
        report = analyze([100, 200, -50, -100, 0])

        self.assertEqual(report.total_trades, 5)
        self.assertEqual(report.wins, 2)
        self.assertEqual(report.losses, 2)
        self.assertEqual(report.breakeven, 1)

        self.assertAlmostEqual(report.gross_profit, 300.0, places=6)
        self.assertAlmostEqual(report.gross_loss, 150.0, places=6)
        self.assertAlmostEqual(report.profit_factor, 2.0, places=6)

        # Expectancy does NOT double count: breakeven is in the
        # denominator but contributes 0 to the numerator.
        self.assertAlmostEqual(report.net_profit, 150.0, places=6)
        self.assertAlmostEqual(report.expectancy, 30.0, places=6)
        self.assertAlmostEqual(report.win_rate, 40.0, places=6)

    def test_all_wins_profit_factor_infinity(self):
        report = analyze([5.0, 10.0, 20.0])
        self.assertEqual(report.wins, 3)
        self.assertEqual(report.losses, 0)
        self.assertEqual(report.breakeven, 0)
        self.assertAlmostEqual(report.gross_loss, 0.0, places=6)
        self.assertEqual(report.profit_factor, float("inf"))
        # Documented deterministic representation: inf denotes
        # "unbounded" -- gross profit with zero gross loss.
        self.assertGreater(report.expectancy, 0.0)

    def test_all_losses_profit_factor_zero(self):
        report = analyze([-5.0, -10.0])
        self.assertEqual(report.wins, 0)
        self.assertEqual(report.losses, 2)
        self.assertEqual(report.breakeven, 0)
        self.assertAlmostEqual(report.gross_profit, 0.0, places=6)
        # No gross profit -> profit factor 0.0 (no division).
        self.assertAlmostEqual(report.profit_factor, 0.0, places=6)
        self.assertAlmostEqual(report.expectancy, -7.5, places=6)

    def test_breakeven_only_is_neither_win_nor_loss(self):
        report = analyze([0.0, 0.0, 0.0])
        self.assertEqual(report.total_trades, 3)
        self.assertEqual(report.wins, 0)
        self.assertEqual(report.losses, 0)
        self.assertEqual(report.breakeven, 3)
        self.assertAlmostEqual(report.gross_profit, 0.0, places=6)
        self.assertAlmostEqual(report.gross_loss, 0.0, places=6)
        # No gross profit and no gross loss -> 0.0 (not inf).
        self.assertAlmostEqual(report.profit_factor, 0.0, places=6)
        self.assertAlmostEqual(report.expectancy, 0.0, places=6)
        self.assertAlmostEqual(report.win_rate, 0.0, places=6)

    def test_empty_no_completed_trades(self):
        account = Account(starting_balance=2000.0)
        report = PerformanceAnalytics.analyze(account, TradeRegistry())
        self.assertEqual(report.total_trades, 0)
        self.assertEqual(report.wins, 0)
        self.assertEqual(report.losses, 0)
        self.assertEqual(report.breakeven, 0)
        # Project missing-value convention (0.0, same as win_rate).
        self.assertAlmostEqual(report.profit_factor, 0.0, places=6)
        self.assertAlmostEqual(report.expectancy, 0.0, places=6)

    def test_negative_expectancy_preserved(self):
        report = analyze([10.0, -10.0, -20.0])
        self.assertAlmostEqual(report.net_profit, -20.0, places=6)
        self.assertAlmostEqual(
            report.expectancy,
            -20.0 / 3,
            places=6,
        )
        self.assertAlmostEqual(
            report.profit_factor,
            10.0 / 30.0,
            places=6,
        )

    def test_breakeven_not_counted_as_win(self):
        # If breakeven were misclassified as a win (the pre-9P-b
        # bug), PF and win_rate would be wrong.
        report = analyze([0.0, 5.0])
        self.assertEqual(report.wins, 1)
        self.assertEqual(report.losses, 0)
        self.assertEqual(report.breakeven, 1)
        self.assertEqual(report.profit_factor, float("inf"))
        self.assertAlmostEqual(report.win_rate, 50.0, places=6)

    def test_open_positions_excluded(self):
        account = Account(starting_balance=2000.0)
        registry = TradeRegistry()
        registry.add(open_trade(pnl=100.0, exit_time=1))
        report = PerformanceAnalytics.analyze(account, registry)
        self.assertEqual(report.total_trades, 0)
        self.assertEqual(report.wins, 0)
        self.assertEqual(report.losses, 0)
        self.assertEqual(report.breakeven, 0)
        self.assertAlmostEqual(report.net_profit, 0.0, places=6)

    def test_repeated_calculation_is_deterministic(self):
        pnls = [10.0, -5.0, 20.0, 0.0]
        first = analyze(pnls)
        second = analyze(pnls)
        self.assertEqual(first.profit_factor, second.profit_factor)
        self.assertEqual(first.expectancy, second.expectancy)
        self.assertEqual(first.gross_profit, second.gross_profit)
        self.assertEqual(first.gross_loss, second.gross_loss)

    def test_costs_honored_net_pnl(self):
        # Trade.pnl is the net result already (gross minus
        # commission minus slippage). A trade whose entry/exit
        # spread is +110 but with commission+slippage reducing the
        # net P&L to +90 must contribute +90 to gross profit.
        report = analyze([90.0, -60.0])
        self.assertAlmostEqual(report.gross_profit, 90.0, places=6)
        self.assertAlmostEqual(report.gross_loss, 60.0, places=6)
        self.assertAlmostEqual(report.profit_factor, 1.5, places=6)
        self.assertAlmostEqual(report.expectancy, 15.0, places=6)

    def test_reconciles_with_booked_account(self):
        # The report's profit_factor/expectancy reconcile to the
        # booked (net, commission+slip-adjusted) account P&L.
        pnls = [100.0, -50.0, -100.0, 0.0]
        account = Account(starting_balance=2000.0)
        for pnl in pnls:
            if pnl > 0:
                account.book_profit(pnl)
            elif pnl < 0:
                account.book_loss(-pnl)
            else:
                account.book_profit(0.0)
        report = PerformanceAnalytics.analyze(
            account,
            [closed_trade(p, exit_time=i) for i, p in enumerate(pnls)],
        )
        self.assertAlmostEqual(report.net_profit, -50.0, places=6)
        self.assertAlmostEqual(
            report.net_profit,
            account.state.realized_pnl,
            places=6,
        )
        self.assertEqual(report.total_trades, 4)
        self.assertAlmostEqual(report.expectancy, -12.5, places=6)

    def test_account_state_has_no_duplicate_metrics(self):
        # The single canonical calculation lives in
        # PerformanceAnalytics. The account-level state must NOT
        # expose a second, misleading profit_factor/expectancy.
        account = Account(starting_balance=2000.0)
        self.assertFalse(
            hasattr(account.state, "profit_factor"),
            "AccountState.profit_factor must not exist (dup surface)",
        )
        self.assertFalse(
            hasattr(account.state, "expectancy"),
            "AccountState.expectancy must not exist (dup surface)",
        )
        # The canonical metrics are reachable through the report
        # surface (same object the dashboard consumes).
        report = PerformanceAnalytics.analyze(account, [])
        self.assertTrue(hasattr(report, "profit_factor"))
        self.assertTrue(hasattr(report, "expectancy"))

    def test_metrics_dict_includes_breakeven(self):
        pnls = [10.0, 0.0, -5.0]
        account = Account(starting_balance=2000.0)
        trades = [
            closed_trade(p, exit_time=i)
            for i, p in enumerate(pnls)
        ]
        metrics = PerformanceAnalytics.metrics(account, trades)
        self.assertEqual(metrics["total_trades"], 3)
        self.assertEqual(metrics["wins"], 1)
        self.assertEqual(metrics["losses"], 1)
        self.assertEqual(metrics["breakeven"], 1)
        self.assertAlmostEqual(metrics["profit_factor"], 2.0, places=6)
        self.assertAlmostEqual(
            metrics["expectancy"],
            5.0 / 3,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
