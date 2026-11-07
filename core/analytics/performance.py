"""
====================================================

QuantEngine

Performance Analytics

Computes the portfolio performance report over the SHARED
TradeRegistry + Account state that every execution mode
(Backtest, Paper, Live Broker) books into. The input objects
are the exact objects those engines wrote -- no duplication,
no reconciliation.

Metrics produced:

    - trade statistics: total/wins/losses/breakeven, win rate,
      gross profit/loss, profit factor, expectancy,
      average win/loss, payoff ratio
    - risk-adjusted: trade-based Sharpe and Sortino,
      trade-return volatility, max drawdown (equity-curve)
    - directional: counts and win rates for longs and shorts
    - behavior: consecutive win/loss streaks, avg bars held,
      best/worst trade
    - the trade-based equity curve (closed trades sorted by
      exit) with peak equity

All metrics are computed from the closed trades only; open
trades are excluded so the report is stable per book.

Definitions (phase 9P-b):

    completed trade   = status == "CLOSED" (in the registry)
    net P&L           = Trade.pnl (gross minus commission, slippage,
                        and signed funding, as booked by the simulator)
    winning trade     = net P&L > 0
    losing trade      = net P&L < 0
    breakeven trade   = net P&L == 0 (NEITHER a win nor a loss)
    gross profit      = sum of positive net P&L
    gross loss        = absolute sum of negative net P&L
    profit factor     = gross profit / gross loss
                        (inf when gross profit > 0 and no gross
                        loss; 0.0 when no gross profit)
    expectancy        = mean completed-trade net P&L
                        (net profit / total, breakevens included
                        in the denominator)

Breakeven trades are counted in `total` (and thus the
expectancy divisor) but excluded from the win/loss counts,
gross profit / gross loss, and win/loss streaks.

====================================================
"""

from dataclasses import dataclass, field

from core.backtesting.trade_registry import TradeRegistry


@dataclass(slots=True)
class PerformanceReport:
    """
    Immutable snapshot of one performance computation.
    """

    starting_balance: float = 0.0

    final_balance: float = 0.0

    net_profit: float = 0.0

    total_trades: int = 0

    wins: int = 0

    losses: int = 0

    # Breakeven closed trades (net P&L == 0.0) -- neither a win
    # nor a loss (phase 9P-b). Always non-negative; total_trades
    # == wins + losses + breakeven.
    breakeven: int = 0

    win_rate: float = 0.0

    gross_profit: float = 0.0

    gross_loss: float = 0.0

    profit_factor: float = 0.0

    expectancy: float = 0.0

    avg_win: float = 0.0

    avg_loss: float = 0.0

    payoff_ratio: float = 0.0

    avg_pnl_percent: float = 0.0

    avg_win_percent: float = 0.0

    avg_loss_percent: float = 0.0

    avg_bars_held: float = 0.0

    max_consecutive_wins: int = 0

    max_consecutive_losses: int = 0

    best_trade: float = 0.0

    worst_trade: float = 0.0

    sharpe: float = 0.0

    sortino: float = 0.0

    returns_std: float = 0.0

    max_drawdown: float = 0.0

    max_drawdown_percent: float = 0.0

    peak_equity: float = 0.0

    final_equity: float = 0.0

    longs: int = 0

    shorts: int = 0

    long_win_rate: float = 0.0

    short_win_rate: float = 0.0

    # Gate C: Explicit ambiguous reporting (even if zero)
    ambiguous_trades: int = 0

    ambiguous_rate: float = 0.0

    sl_first_trades: int = 0

    tp_first_trades: int = 0

    # Phase 12 economic honesty: modeled costs actually
    # booked across the closed trades (sum of commission +
    # slippage) and the resulting cost-basis label. A report
    # whose PnL was computed under zero-cost settings must
    # never be readable as executable profitability.
    total_modeled_costs: float = 0.0

    cost_basis: str = ""

    equity_curve: list = field(default_factory=list)


class PerformanceAnalytics:
    """
    Pure function-style analytics: analyze(account, trades)
    returns a PerformanceReport. Accepts either an Account /
    AccountState for the balance source and either a
    TradeRegistry / sequence of Trade objects.
    """

    @classmethod
    def analyze(cls, account, trades):
        """
        Parameters
        ----------
        account:
            Account or AccountState (`.state.balance`, etc.) --
            only the starting/final balance are read.
        trades:
            TradeRegistry or any sequence of Trade objects.
        """

        registry = (
            trades
            if isinstance(trades, TradeRegistry)
            else TradeRegistry()
        )

        if not isinstance(trades, TradeRegistry):
            for trade in trades:
                registry.add(trade)

        closed = [
            trade
            for trade in registry.all()
            if trade.status == "CLOSED"
        ]

        ordered = sorted(
            closed,
            key=lambda t: (t.exit_time, t.entry_time, t.entry),
        )

        starting = float(
            getattr(
                getattr(account, "state", account),
                "starting_balance",
                0.0,
            )
        )

        final_balance = float(
            getattr(
                getattr(account, "state", account),
                "balance",
                starting,
            )
        )

        # ----------
        # Equity curve + drawdown
        # ----------

        curve = []
        peak = starting
        equity = starting
        max_dd = 0.0
        max_dd_percent = 0.0

        for trade in ordered:
            equity += trade.pnl
            curve.append(
                (trade.exit_time, equity)
            )
            if equity > peak:
                peak = equity
            else:
                dd = peak - equity
                if dd > max_dd:
                    max_dd = dd
                    if peak > 0:
                        max_dd_percent = (dd / peak) * 100

        final_equity = (
            equity
            if ordered
            else starting
        )

        peak_equity = max(peak, final_equity)

        # ----------
        # Wins / losses
        #
        # Breakeven trades (pnl == 0) are classified as NEITHER a
        # win nor a loss (phase 9P-b): they are excluded from the
        # win/loss counts and from gross profit / gross loss, but
        # remain counted in `total`, so expectancy is the mean of
        # ALL completed-trade net P&L (including breakevens) and
        # profit factor uses the strictly-positive / strictly-
        # negative subtotals only.
        # ----------

        wins = [
            t for t in closed
            if (t.pnl > 0)
        ]

        losses = [
            t for t in closed
            if (t.pnl < 0)
        ]

        total = len(closed)

        breakeven = total - len(wins) - len(losses)

        gross_profit = sum(t.pnl for t in wins)

        gross_loss = abs(
            sum(t.pnl for t in losses)
        )

        net_profit = sum(t.pnl for t in closed)

        win_rate = (
            (len(wins) / total * 100)
            if total
            else 0.0
        )

        avg_win = (
            gross_profit / len(wins)
            if wins
            else 0.0
        )

        avg_loss = (
            gross_loss / len(losses)
            if losses
            else 0.0
        )

        profit_factor = (
            float("inf")
            if gross_profit > 0 and gross_loss == 0
            else (
                gross_profit / gross_loss
                if gross_loss > 0
                else 0.0
            )
        )

        expectancy = (
            net_profit / total
            if total
            else 0.0
        )

        payoff_ratio = (
            avg_win / avg_loss
            if avg_loss > 0
            else 0.0
        )

        avg_pnl_percent = (
            sum(t.pnl_percent for t in closed) / total
            if total
            else 0.0
        )

        avg_win_percent = (
            sum(t.pnl_percent for t in wins) / len(wins)
            if wins
            else 0.0
        )

        avg_loss_percent = (
            sum(abs(t.pnl_percent) for t in losses) / len(losses)
            if losses
            else 0.0
        )

        avg_bars_held = (
            sum(t.bars_held for t in closed) / total
            if total
            else 0.0
        )

        best_trade = (
            max(t.pnl for t in closed)
            if closed
            else 0.0
        )

        worst_trade = (
            min(t.pnl for t in closed)
            if closed
            else 0.0
        )

        # ----------
        # Streaks (in exit order)
        #
        # Breakeven trades (pnl == 0) are neither wins nor losses:
        # they separate runs (reset both counters) rather than
        # extending either streak (phase 9P-b).
        # ----------

        current_wins = 0
        current_losses = 0
        max_wins = 0
        max_losses = 0

        for trade in ordered:
            if trade.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif trade.pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0

        # ----------
        # Risk-adjusted returns (per-trade *position return* series)
        # Trade return = pnl / notional (where notional = entry*quantity).
        # This normalizes for position size; dollar PnL would make
        # Sharpe depend on quantity. Not annualized; sqrt(n) scales for
        # trade count. Documented as trade-based Sharpe.
        # ----------

        # Use position return (fraction, not percent) for risk-adjusted
        returns = []
        for t in closed:
            notion = t.entry * t.quantity if t.entry and t.quantity else 0.0
            if notion != 0:
                returns.append(t.pnl / notion)
            else:
                # Fallback to pnl_percent if available, else 0
                try:
                    returns.append(t.pnl_percent / 100.0)
                except Exception:
                    returns.append(0.0)

        # Keep pnls for returns_std compatibility but compute std on returns
        pnls = returns
        returns_std = _std(returns)

        sharpe = (
            (_mean(returns) / returns_std * (len(returns) ** 0.5))
            if returns_std > 0
            else 0.0
        )

        downside = [
            min(0.0, r)
            for r in returns
        ]

        downside_std = _std(downside)

        sortino = (
            (_mean(returns) / downside_std * (len(returns) ** 0.5))
            if downside_std > 0
            else 0.0
        )

        # ----------
        # Directional breakdown
        # ----------

        longs = [
            t for t in closed
            if t.direction.upper() == "BULLISH"
        ]

        shorts = [
            t for t in closed
            if t.direction.upper() == "BEARISH"
        ]

        long_win_rate = (
            (
                len([t for t in longs if t.pnl > 0])
                / len(longs) * 100
            )
            if longs
            else 0.0
        )

        short_win_rate = (
            (
                len([t for t in shorts if t.pnl > 0])
                / len(shorts) * 100
            )
            if shorts
            else 0.0
        )

        # Gate C: Explicit ambiguous reporting (even if zero)
        # Distinguishes: no ambiguous occurred vs not measured vs inside Trade only
        ambiguous_trades = len([t for t in closed if getattr(t, "ambiguous", False)])
        ambiguous_rate = (ambiguous_trades / total * 100) if total else 0.0
        # Conservative policy: SL-first. TP-first would be ambiguous+WIN, but we record SL-first as LOSS ambiguous
        # For reporting, sl_first = ambiguous (since conservative is SL-first), tp_first = 0 (would be optimistic)
        sl_first_trades = ambiguous_trades  # all ambiguous resolved as SL-first per INTRABAR_POLICY
        tp_first_trades = 0  # optimistic not used, but explicit

        # Phase 12 economic honesty: label what the PnL
        # actually prices in. Zero modeled costs means gross
        # theoretical (not executable); anything above means
        # friction-adjusted under the configured cost model
        # (still not OOS, still not a live claim).
        total_modeled_costs = sum(
            float(getattr(t, "commission", 0.0) or 0.0)
            + float(getattr(t, "slippage", 0.0) or 0.0)
            + float(getattr(t, "funding", 0.0) or 0.0)
            for t in closed
        )

        cost_basis = (
            "gross theoretical (zero modeled costs -- not "
            "executable, not OOS)"
            if total_modeled_costs <= 0
            else "friction-adjusted (modeled costs booked: "
            "%.2f -- still not OOS, not a live claim)"
            % total_modeled_costs
        )

        return PerformanceReport(
            starting_balance=starting,
            final_balance=final_balance,
            net_profit=net_profit,
            total_trades=total,
            wins=len(wins),
            losses=len(losses),
            breakeven=breakeven,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_win=avg_win,
            avg_loss=avg_loss,
            payoff_ratio=payoff_ratio,
            avg_pnl_percent=avg_pnl_percent,
            avg_win_percent=avg_win_percent,
            avg_loss_percent=avg_loss_percent,
            avg_bars_held=avg_bars_held,
            max_consecutive_wins=max_wins,
            max_consecutive_losses=max_losses,
            best_trade=best_trade,
            worst_trade=worst_trade,
            sharpe=sharpe,
            sortino=sortino,
            returns_std=returns_std,
            max_drawdown=max_dd,
            max_drawdown_percent=max_dd_percent,
            peak_equity=peak_equity,
            final_equity=final_equity,
            longs=len(longs),
            shorts=len(shorts),
            long_win_rate=long_win_rate,
            short_win_rate=short_win_rate,
            ambiguous_trades=ambiguous_trades,
            ambiguous_rate=ambiguous_rate,
            sl_first_trades=sl_first_trades,
            tp_first_trades=tp_first_trades,
            total_modeled_costs=total_modeled_costs,
            cost_basis=cost_basis,
            equity_curve=curve,
        )

    # --------------------------------------------------

    @classmethod
    def metrics(cls, account, trades):
        """Dictionary form of the report (JSON-friendly)."""

        report = cls.analyze(account, trades)

        return {
            "starting_balance": report.starting_balance,
            "final_balance": report.final_balance,
            "net_profit": report.net_profit,
            "total_trades": report.total_trades,
            "wins": report.wins,
            "losses": report.losses,
            "breakeven": report.breakeven,
            "win_rate": report.win_rate,
            "gross_profit": report.gross_profit,
            "gross_loss": report.gross_loss,
            "profit_factor": report.profit_factor,
            "expectancy": report.expectancy,
            "avg_win": report.avg_win,
            "avg_loss": report.avg_loss,
            "payoff_ratio": report.payoff_ratio,
            "avg_pnl_percent": report.avg_pnl_percent,
            "avg_bars_held": report.avg_bars_held,
            "max_consecutive_wins": report.max_consecutive_wins,
            "max_consecutive_losses": report.max_consecutive_losses,
            "best_trade": report.best_trade,
            "worst_trade": report.worst_trade,
            "sharpe": report.sharpe,
            "sortino": report.sortino,
            "returns_std": report.returns_std,
            "max_drawdown": report.max_drawdown,
            "max_drawdown_percent": report.max_drawdown_percent,
            "peak_equity": report.peak_equity,
            "final_equity": report.final_equity,
            "longs": report.longs,
            "shorts": report.shorts,
            "long_win_rate": report.long_win_rate,
            "short_win_rate": report.short_win_rate,
            "ambiguous_trades": report.ambiguous_trades,
            "ambiguous_rate": report.ambiguous_rate,
            "sl_first_trades": report.sl_first_trades,
            "tp_first_trades": report.tp_first_trades,
            "total_modeled_costs": report.total_modeled_costs,
            "cost_basis": report.cost_basis,
        }

    # --------------------------------------------------

    @classmethod
    def summary(cls, account, trades, label="PERFORMANCE"):
        """Human-readable console block."""

        report = cls.analyze(account, trades)

        lines = [
            "",
            "=" * 60,
            f"{label}",
            "=" * 60,
            f"Starting balance : {report.starting_balance:,.2f}",
            f"Final equity     : {report.final_equity:,.2f}",
            f"Net profit       : {report.net_profit:+,.2f}",
            f"Total trades     : {report.total_trades}",
            f"Wins / Losses    : {report.wins} / {report.losses} "
            f"(breakeven {report.breakeven})",
            f"Win rate         : {report.win_rate:.2f}%",
            f"Profit factor    : {report.profit_factor:.3f}",
            f"Expectancy       : {report.expectancy:+.3f}",
            f"Avg win / loss   : {report.avg_win:.2f} / "
            f"{report.avg_loss:.2f}",
            f"Payoff ratio     : {report.payoff_ratio:.3f}",
            f"Sharpe / Sortino : {report.sharpe:.3f} / "
            f"{report.sortino:.3f}",
            f"Max drawdown     : {report.max_drawdown:,.2f} "
            f"({report.max_drawdown_percent:.2f}%)",
            f"Longs            : {report.longs} "
            f"(win {report.long_win_rate:.1f}%)",
            f"Shorts           : {report.shorts} "
            f"(win {report.short_win_rate:.1f}%)",
            f"Best / Worst     : {report.best_trade:+.2f} / "
            f"{report.worst_trade:+.2f}",
            f"Avg bars held    : {report.avg_bars_held:.2f}",
            f"Cost basis       : {report.cost_basis}",
        ]

        return "\n".join(lines)


def _mean(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values):
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = (
        sum((value - mean) ** 2 for value in values)
        / (len(values) - 1)
    )
    return variance ** 0.5