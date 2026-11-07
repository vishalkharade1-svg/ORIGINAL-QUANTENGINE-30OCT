"""
====================================================

QuantEngine

Performance Dashboard

A pure display layer over the SHARED PerformanceReport the
analytics layer produces (STATUS 94). Nothing is recomputed
here -- the report and the trade sequence are the single
source of truth, so the console block, the ASCII equity
curve and the CSV export can never disagree with the metrics
any other mode prints. No new state objects.

    1. render(report)                 -- aligned stat block.
    2. render_equity_curve(report)    -- ASCII log-line chart
       of the trade-based equity curve with peak/trough scale.
    3. render_trades(report, trades)  -- recent trades table
       (read-only, respects the analytics closed-only view).
    4. export_csv(trades, path)       -- deterministic CSV of
       the closed trade list; returns the CSV text, or the
       written path when one is given.

Stdlib only (csv + the analytics report it formats).

====================================================
"""

import csv

from core.analytics.performance import PerformanceReport


WATERFILL = "▁▂▃▄▅▆▇█"


def _closed(trades):
    from core.backtesting.trade_registry import TradeRegistry

    if isinstance(trades, TradeRegistry):
        raw = trades.all()
    else:
        raw = list(trades or [])

    return [
        t for t in raw
        if getattr(t, "status", "") == "CLOSED"
    ]


def _sorted_closed(trades):
    closed = _closed(trades)
    return sorted(
        closed,
        key=lambda t: (t.exit_time, t.entry_time, t.entry),
    )


class PerformanceDashboard:

    # --------------------------------------------------

    @classmethod
    def render(
        cls,
        report,
        label="PERFORMANCE DASHBOARD",
    ):
        """Aligned stat block from a PerformanceReport."""

        head = [
            "",
            "=" * 60,
            f"{label}",
            "=" * 60,
        ]

        rows = [
            ("Starting balance", f"{report.starting_balance:,.2f}"),
            ("Final equity", f"{report.final_equity:,.2f}"),
            ("Peak equity", f"{report.peak_equity:,.2f}"),
            ("Net profit", f"{report.net_profit:+,.2f}"),
            ("Total trades", f"{report.total_trades}"),
            ("Wins / Losses", f"{report.wins} / {report.losses}"),
            ("Win rate", f"{report.win_rate:.2f}%"),
            ("Gross profit / loss", (
                f"{report.gross_profit:+,.2f} / "
                f"{report.gross_loss:,.2f}"
            )),
            ("Profit factor", f"{report.profit_factor:.3f}"),
            ("Expectancy", f"{report.expectancy:+.3f}"),
            ("Avg win / loss", (
                f"{report.avg_win:.2f} / {report.avg_loss:.2f}"
            )),
            ("Payoff ratio", f"{report.payoff_ratio:.3f}"),
            ("Avg PnL % / bars", (
                f"{report.avg_pnl_percent:.2f}% / "
                f"{report.avg_bars_held:.2f}"
            )),
            ("Sharpe / Sortino", (
                f"{report.sharpe:.3f} / {report.sortino:.3f}"
            )),
            ("Returns std", f"{report.returns_std:.3f}"),
            ("Max drawdown", (
                f"{report.max_drawdown:,.2f} "
                f"({report.max_drawdown_percent:.2f}%)"
            )),
            ("Max streak (W/L)", (
                f"{report.max_consecutive_wins} / "
                f"{report.max_consecutive_losses}"
            )),
            ("Longs", (
                f"{report.longs} (win {report.long_win_rate:.1f}%)"
            )),
            ("Shorts", (
                f"{report.shorts} (win {report.short_win_rate:.1f}%)"
            )),
            ("Best / Worst", (
                f"{report.best_trade:+.2f} / "
                f"{report.worst_trade:+.2f}"
            )),
        ]

        width = max(
            len(k) for k, _ in rows
        )

        body = [
            f" {k:<{width}} : {v}"
            for k, v in rows
        ]

        return "\n".join(head + body)

    # --------------------------------------------------

    @classmethod
    def render_equity_curve(
        cls,
        report,
        height=12,
        width=60,
    ):
        """ASCII log-line chart of the trade-based equity curve.

        Returns a list of string lines (empty when the report
        holds no closed trades).
        """

        curve = list(report.equity_curve or [])

        if not curve:
            return [
                "",
                "--------------------------------------------",
                "EQUITY CURVE",
                "--------------------------------------------",
                "  No closed trades to chart.",
            ]

        if height < 2:
            height = 2

        if width < 2:
            width = 2

        values = [eq for _, eq in curve]

        low = min(values)
        high = max(values)

        span = high - low

        columns = []

        if len(curve) > width:

            step = len(curve) / width

            for i in range(width):

                idx = min(int(i * step), len(curve) - 1)
                columns.append(values[idx])

        else:

            columns = values

        lines = [
            f"  {high:>12,.2f}  top",
        ]

        for row in range(height - 1, -1, -1):

            band = low + (high - low) * (
                row / (height - 1) if height > 1 else 0.0
            )

            cells = []

            for eq in columns:

                bars = (
                    int((eq - low) / span * (height - 1)) + 1
                    if span > 0
                    else height
                )

                filled = (row < bars)

                cells.append(
                    WATERFILL[
                        min(
                            7,
                            int(
                                (eq - low) / span * 7
                            )
                            if span > 0
                            else 7,
                        )
                    ] if filled else " "
                )

            lines.append("  {:<12}  {}".format("", "".join(cells)))

        lines.append(f"  {low:>12,.2f}  bottom")

        end_pos = (
            int((len(curve) - 1) * (width - 1) / (len(curve) - 1))
            if len(curve) > 1
            else 0
        )

        first_ts = curve[0][0]
        last_ts = curve[-1][0]

        edge = "  " + " " * 12 + "  "

        timeline = [
            edge + str(first_ts) + " -> " + str(last_ts),
            edge + " " * end_pos + str(last_ts),
        ]

        lines.extend(timeline)

        return lines

    # --------------------------------------------------

    @classmethod
    def render_trades(
        cls,
        report,
        trades,
        limit=20,
    ):
        """Recent-trades table over the closed view."""

        ordered = _sorted_closed(trades)

        if not ordered:
            return "\nNO CLOSED TRADES TO LIST"

        newest = list(reversed(ordered))[:limit]

        header = (
            f"{'SYM':>6} {'DIR':>8} {'ENTRY':>10} "
            f"{'EXIT':>10} {'T0':>6} {'T1':>6} "
            f"{'BARS':>4} {'PNL':>9} {'RESULT':>6}"
        )

        canvas = "\n".join(
            [
                header,
                "-" * len(header),
            ]
            + [
                (
                    f"{t.symbol or '':>6} "
                    f"{t.direction.upper():>8} "
                    f"{t.entry:>10,.2f} "
                    f"{t.exit_price:>10,.2f} "
                    f"{t.entry_time:>6} "
                    f"{t.exit_time:>6} "
                    f"{t.bars_held:>4} "
                    f"{t.pnl:>+9.2f} "
                    f"{t.result:>6}"
                )
                for t in newest
            ]
        )

        return "\n".join([
            "",
            ("=" * 60),
            "RECENT TRADES",
            ("=" * 60),
            canvas,
        ])

    # --------------------------------------------------

    @classmethod
    def export_csv(
        cls,
        trades,
        path=None,
    ):
        """Deterministic CSV of the closed trade list.

        Columns: symbol, direction, entry, exit, entry_time,
        exit_time, bars_held, pnl, pnl_percent, commission,
        slippage, result. Returns the CSV text, or the written
        path when one is provided.
        """

        ordered = _sorted_closed(trades)

        header = [
            "symbol",
            "direction",
            "entry",
            "exit",
            "entry_time",
            "exit_time",
            "bars_held",
            "pnl",
            "pnl_percent",
            "commission",
            "slippage",
            "result",
        ]

        rows = [
            [
                t.symbol or "",
                t.direction,
                f"{t.entry:.6f}",
                f"{t.exit_price:.6f}",
                t.entry_time,
                t.exit_time,
                t.bars_held,
                f"{t.pnl:.6f}",
                f"{t.pnl_percent:.6f}",
                f"{t.commission:.6f}",
                f"{t.slippage:.6f}",
                t.result,
            ]
            for t in ordered
        ]

        import io

        buffer = io.StringIO()

        writer = csv.writer(buffer, lineterminator="\n")

        writer.writerow(header)

        writer.writerows(rows)

        text = buffer.getvalue()

        if path is None:
            return text

        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

        return path