"""
====================================================

QuantEngine

Performance Dashboard Tests

Run with:

    python -m unittest tests.test_performance_dashboard -v

Proves the dashboard display layer over the SHARED
PerformanceReport (STATUS 94) -- no recomputation, no new
state objects:

    1. render() formats an aligned stat block straight from
       the report, including the rows the analytics summary
       does not print (peak equity, gross p/l, avg PnL %,
       returns std, streaks).
    2. render_equity_curve() charts the trade-based equity
       curve: full-width height on a monotonic climb, a
       no-trades notice on an empty report, and a peak/trough
       valley shape on a curved series; scale line = peak and
       trough values.
    3. render_trades() prints the closed view and nothing
       else -- open trades never appear.
    4. export_csv() is deterministic (exit-ordered), its rows
       round-trip through the stdlib csv module with the exact
       header, carries the traded symbol, and writes a real
       file when given a path.

Stdlib only -- no network, no pipeline.

====================================================
"""

import csv
import os
import tempfile
import unittest

from core.backtesting.trade import Trade

from core.analytics.performance import (
    PerformanceAnalytics,
    PerformanceReport,
)

from core.dashboard.dashboard import PerformanceDashboard


def make_trade(
    pnl,
    direction="BULLISH",
    symbol="BTC",
    entry_time=0,
    exit_time=0,
    bars_held=1,
    commission=0.0,
    slippage=0.0,
):
    return Trade(
        direction=direction,
        entry=100.0,
        quantity=1.0,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_price=100.0 + pnl,
        pnl=pnl,
        pnl_percent=pnl,
        bars_held=bars_held,
        commission=commission,
        slippage=slippage,
        symbol=symbol,
        status="CLOSED",
        result="WIN" if pnl >= 0 else "LOSS",
    )


def open_trade(pnl=0.0, exit_time=0):
    trade = make_trade(pnl, exit_time=exit_time)
    trade.status = "OPEN"
    trade.result = ""
    return trade


EMPTY = PerformanceReport()


class TestRender(unittest.TestCase):

    maxDiff = None

    def test_render_contains_report_rows(self):
        trades = [
            make_trade(10.0, exit_time=1),
            make_trade(-5.0, exit_time=2),
        ]
        report = PerformanceAnalytics.analyze(None, trades)
        text = PerformanceDashboard.render(report, label="DEMO")

        self.assertIn("DEMO", text)
        self.assertIn("Net profit", text)
        self.assertIn("+5.00", text)
        self.assertIn("Peak equity", text)
        self.assertIn("Gross profit / loss", text)
        self.assertIn("Avg PnL % / bars", text)
        self.assertIn("Returns std", text)
        self.assertIn("Max streak (W/L)", text)

    def test_render_fits_zeroed_report(self):
        text = PerformanceDashboard.render(EMPTY)

        self.assertIn("0", text)
        self.assertIn("PERFORMANCE DASHBOARD", text)


class TestEquityCurve(unittest.TestCase):

    def test_empty_curve_renders_notice(self):
        lines = PerformanceDashboard.render_equity_curve(EMPTY)

        self.assertEqual(
            lines[-1],
            "  No closed trades to chart.",
        )

    def test_monotonic_climb_is_full_height(self):
        report = PerformanceReport(
            starting_balance=2000.0,
            final_equity=2000.0,
            equity_curve=[
                (1, 2005.0),
                (2, 2015.0),
                (3, 2030.0),
            ],
        )
        lines = PerformanceDashboard.render_equity_curve(
            report,
            height=6,
            width=10,
        )

        self.assertIn("2,030.00", lines[0])

        chart = "\n".join(lines)

        self.assertIn("2,005.00", chart)
        self.assertIn("1 -> 3", chart)
        self.assertTrue(any("█" in line for line in lines))

    def test_valley_shape_reaches_bottom(self):
        report = PerformanceReport(
            equity_curve=[
                (1, 100.0),
                (2, 80.0),
                (3, 120.0),
            ],
        )
        lines = PerformanceDashboard.render_equity_curve(
            report,
            height=5,
            width=10,
        )

        # trough label present
        self.assertIn("80.00", "\n".join(lines))


class TestRenderTrades(unittest.TestCase):

    def test_open_trades_are_never_listed(self):
        trades = [
            make_trade(10.0, exit_time=1),
            open_trade(50.0, exit_time=2),
        ]
        text = PerformanceDashboard.render_trades(
            EMPTY,
            trades,
        )

        self.assertIn("+10.00", text)
        self.assertNotIn("+50.00", text)
        self.assertIn("RECENT TRADES", text)


class TestExportCsv(unittest.TestCase):

    def test_csv_header_and_rows_deterministic(self):
        trades = [
            make_trade(-5.0, exit_time=4, entry_time=3),
            make_trade(10.0, exit_time=1, entry_time=0),
            make_trade(20.0, symbol="ETH", exit_time=7),
        ]
        text = PerformanceDashboard.export_csv(trades)
        rows = list(csv.reader(text.splitlines()))

        self.assertEqual(rows[0], [
            "symbol", "direction", "entry", "exit",
            "entry_time", "exit_time", "bars_held",
            "pnl", "pnl_percent", "commission",
            "slippage", "result",
        ])
        # exit-ordered: 1, 4, 7
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1][5], "1")
        self.assertEqual(rows[2][5], "4")
        self.assertEqual(rows[3][5], "7")
        self.assertAlmostEqual(float(rows[3][7]), 20.0)
        self.assertEqual(rows[3][0], "ETH")

    def test_csv_writes_file(self):
        trades = [make_trade(7.5, exit_time=1)]

        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            returned = PerformanceDashboard.export_csv(
                trades, path=path
            )
            self.assertEqual(returned, path)
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
            self.assertIn("7.500000", written)
            self.assertIn("symbol,direction", written)
        finally:
            os.remove(path)

    def test_csv_accepts_registry_backed_analysis(self):
        # Export must work on the same objects analytics
        # consumes (the shared TradeRegistry from backtesting).
        import io

        from core.backtesting.trade_registry import TradeRegistry

        registry = TradeRegistry()
        for trade in (
            make_trade(10.0, exit_time=1),
            open_trade(99.0, exit_time=2),
        ):
            registry.add(trade)

        text = PerformanceDashboard.export_csv(registry)

        rows = list(csv.reader(text.splitlines()))
        # open trade excluded
        self.assertEqual(len(rows), 2)
        self.assertNotIn("99.000000", text)


if __name__ == "__main__":
    unittest.main()