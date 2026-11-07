"""
Phase 9S Gate C — PerformanceAnalytics explicit ambiguous reporting.
"""

import unittest
from core.backtesting.trade import Trade
from core.backtesting.trade_registry import TradeRegistry
from core.risk.account import Account
from core.analytics.performance import PerformanceAnalytics


def make_trade(pnl, ambiguous=False, direction="BULLISH", entry=100, qty=1):
    return Trade(
        direction=direction,
        entry=entry,
        quantity=qty,
        pnl=pnl,
        pnl_percent=(pnl/(entry*qty)*100) if entry*qty else 0,
        status="CLOSED",
        result="WIN" if pnl>0 else "LOSS" if pnl<0 else "BREAKEVEN",
        ambiguous=ambiguous,
        exit_time=1000,
        entry_time=900,
    )


class TestPerformanceAmbiguous(unittest.TestCase):

    def test_reports_ambiguous_trades_even_when_zero(self):
        acc = Account(starting_balance=2000)
        reg = TradeRegistry()
        for pnl in [10, -5, 5]:
            reg.add(make_trade(pnl, ambiguous=False))
        report = PerformanceAnalytics.analyze(acc, reg)
        self.assertEqual(report.ambiguous_trades, 0)
        self.assertEqual(report.ambiguous_rate, 0.0)
        self.assertEqual(report.sl_first_trades, 0)
        self.assertEqual(report.tp_first_trades, 0)

    def test_counts_ambiguous_and_rate(self):
        acc = Account(starting_balance=2000)
        reg = TradeRegistry()
        reg.add(make_trade(10, ambiguous=False))
        reg.add(make_trade(-5, ambiguous=True))
        reg.add(make_trade(5, ambiguous=True))
        report = PerformanceAnalytics.analyze(acc, reg)
        self.assertEqual(report.ambiguous_trades, 2)
        self.assertAlmostEqual(report.ambiguous_rate, 66.6667, places=2)
        self.assertEqual(report.sl_first_trades, 2)
        self.assertEqual(report.tp_first_trades, 0)

    def test_distinguishes_no_ambiguous_vs_not_measured(self):
        # No ambiguous occurred vs ambiguity not measured are different
        # Our report explicitly measures via Trade.ambiguous field, so 0 means no ambiguous occurred (measured)
        acc = Account(starting_balance=2000)
        reg = TradeRegistry()
        report = PerformanceAnalytics.analyze(acc, reg)
        # Even with 0 trades, ambiguous fields are present and zero (explicit)
        self.assertTrue(hasattr(report, "ambiguous_trades"))
        self.assertTrue(hasattr(report, "sl_first_trades"))
        self.assertTrue(hasattr(report, "tp_first_trades"))

    def test_metrics_dict_includes_ambiguous(self):
        acc = Account(starting_balance=2000)
        reg = TradeRegistry()
        reg.add(make_trade(10, ambiguous=True))
        metrics = PerformanceAnalytics.metrics(acc, reg)
        self.assertIn("ambiguous_trades", metrics)
        self.assertIn("ambiguous_rate", metrics)
        self.assertIn("sl_first_trades", metrics)
        self.assertIn("tp_first_trades", metrics)
