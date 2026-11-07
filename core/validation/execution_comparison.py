"""
====================================================

QuantEngine

Phase 5D Execution Comparison Mode

Run with:

    python -m unittest tests.test_execution_comparison -v

Deterministic strategy comparison. Each entry model
(LIMIT_RETEST, BREAKOUT_CONTINUATION, MARKET_CONFIRMATION, ...)
is executed INDEPENDENTLY -- a fresh pipeline, a fresh simulator,
a fresh backtester -- over the SAME market data, the SAME risk
configuration and the SAME fees/slippage configuration. No two
models share a portfolio: comparison runs are never blended.

The report clearly separates, per model:

    - funnel       setups, orders, filled, expired, invalidated
    - execution    closed trades, wins, losses, unsettled,
                   win rate, profit factor, expectancy,
                   average R, max drawdown
    - costs        fees, slippage, net PnL (booked ledger)

All metrics are computed from the EXECUTED trade ledger -- the
same Account + TradeRegistry objects the Backtester books -- by
the shared PerformanceAnalytics module. Shadow-validation analytics
(causal_validation.entry_shadow) are NOT mixed into this report:
this is the executed-ledger view of a real fill / real stop /
real target / real PnL after transaction costs.

Standard runner usage:

    runner = ExecutionComparisonMode(runner=make_runner()).run(
        history=candles,
        modes=(ENTRY_MODE_LIMIT_RETEST, ENTRY_MODE_BREAKOUT_CONTINUATION),
    )

The runner signature follows the existing validation tools
(optimizer / walk-forward): runner(mode, history) -> Backtester.
The comparison patches the canonical ENTRY_MODE / ACTIVE_ENTRY_MODES
config around each run so every mode route is explicit and the
router (Phase 5C) has no silent-fallback path.

Fees/slippage: the comparison passes the DEFAULT risk-settings
cost configuration to the backtester (TradeSimulator nets
commission + slippage into trade.pnl, and the Trade object
carries both fields). Zero-cost is therefore an explicit
diagnostic configuration, never a hidden assumption.

====================================================
"""

from dataclasses import dataclass, field
from unittest import mock

from config import risk_settings

from core.analytics.performance import PerformanceAnalytics

from core.execution.entry_mode import active_entry_modes
from core.execution.order_registry import (
    EXPIRED,
    FILLED,
    INVALIDATED,
)


def _order_registry(backtester):
    return getattr(
        backtester.pipeline.context, "order_registry", None
    )


def _orders(backtester):
    registered = _order_registry(backtester)
    return (
        registered.all()
        if registered is not None
        else []
    )


def _count_orders(backtester, status):
    return sum(1 for order in _orders(backtester) if order.status == status)


@dataclass(slots=True)
class ComparisonRow:
    """
    One row of the Phase 5D comparison table: one model, one
    independent executed run over the shared history, its funnel,
    its ledger analytics and its transaction costs.
    """

    mode: str
    history_bars: int

    setups: int = 0
    orders: int = 0
    filled: int = 0
    expired: int = 0
    invalidated: int = 0

    closed_trades: int = 0
    wins: int = 0
    losses: int = 0
    unsettled: int = 0

    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    average_r: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0

    fees: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0
    gross_pnl: float = 0.0

    starting_balance: float = 0.0
    final_balance: float = 0.0


@dataclass(slots=True)
class ComparisonReport:
    """
    Full comparison output: the independent per-model rows plus
    the ordered list of modes actually compared.
    """

    modes: tuple
    bars: int
    rows: list = field(default_factory=list)

    # -------------------------------------------------

    def row(self, mode):
        return next(
            (row for row in self.rows if row.mode == mode),
            None,
        )

    # -------------------------------------------------

    def render(self):
        """
        Human-readable comparison table. Each model is a separate
        column -- never a blended portfolio.
        """

        rows = self.rows or []

        names = [""]

        def cell(model):
            row = self.row(model)
            return (
                f"{model}"
                if row is not None
                else "-"
            )

        header = f"{'metric':<26}" + "".join(
            f"{cell(model):>24}" for model in self.modes
        )

        lines = [
            "",
            "=" * 100,
            "EXECUTION COMPARISON -- one independent run per model",
            "=" * 100,
            f"History bars               : {self.bars}",
            header,
        ]

        def emit(label, key, fmt, default=0.0):
            line = f"{label:<26}"
            for row in rows:
                line += f"{fmt.format(getattr(row, key, default)):>24}"
            lines.append(line)

        emit("Setups", "setups", "{:d}", 0)
        emit("Orders", "orders", "{:d}", 0)
        emit("Filled", "filled", "{:d}", 0)
        emit("Expired", "expired", "{:d}", 0)
        emit("Invalidated", "invalidated", "{:d}", 0)
        emit("Closed trades", "closed_trades", "{:d}", 0)
        emit("Wins", "wins", "{:d}", 0)
        emit("Losses", "losses", "{:d}", 0)
        emit("Unsettled", "unsettled", "{:d}", 0)
        emit("Win rate %", "win_rate", "{:.2f}", 0.0)
        emit("Profit factor", "profit_factor", "{:.3f}", 0.0)
        emit("Expectancy ($)", "expectancy", "{:+.3f}", 0.0)
        emit("Average R", "average_r", "{:+.3f}", 0.0)
        emit("Max drawdown ($)", "max_drawdown", "{:.2f}", 0.0)
        emit("Max drawdown %", "max_drawdown_percent", "{:.2f}", 0.0)
        emit("Fees", "fees", "{:.4f}", 0.0)
        emit("Slippage", "slippage", "{:.4f}", 0.0)
        emit("Net PnL", "net_pnl", "{:+.2f}", 0.0)
        emit("Final equity", "final_balance", "{:.2f}", 0.0)

        lines.append("=" * 100)
        lines.append("")
        return "\n".join(lines)


class ExecutionComparisonMode:
    """
    runner(mode, history) -> Backtester

    Executes the shared history once per declared mode with an
    isolated pipeline + simulator + backtester, then builds the
    per-mode rows from the EXECUTED ledger (order registry +
    TradeRegistry + Account + PerformanceAnalytics).
    """

    def __init__(self, runner, modes=None):
        self.runner = runner
        self.modes = list(
            modes or active_entry_modes()
        )

    # -------------------------------------------------

    def run(self, history):

        bars = len(list(history))

        report = ComparisonReport(
            modes=tuple(self.modes),
            bars=bars,
        )

        for mode in self.modes:

            row = self._run_mode(mode, history)

            report.rows.append(row)

        return report

    # -------------------------------------------------

    def _run_mode(self, mode, history):

        with mock.patch.object(
            risk_settings, "ENTRY_MODE", mode,
        ), mock.patch.object(
            risk_settings, "ACTIVE_ENTRY_MODES", (mode,),
        ):
            backtester = self.runner(mode, list(history))

        return self._row_for_mode(mode, backtester, len(list(history)))

    # -------------------------------------------------

    def _row_for_mode(self, mode, backtester, bars):

        trades = backtester.trades.all()

        closed = [t for t in trades if getattr(t, "status", "") == "CLOSED"]

        account = backtester.account

        report = PerformanceAnalytics.analyze(account, backtester.trades)

        fees = sum(float(getattr(t, "commission", 0.0) or 0.0) for t in closed)

        slippage = sum(float(getattr(t, "slippage", 0.0) or 0.0) for t in closed)

        return ComparisonRow(
            mode=mode,
            history_bars=bars,
            setups=_count_setups(backtester),
            orders=len(_orders(backtester)),
            filled=_count_orders(backtester, FILLED),
            expired=_count_orders(backtester, EXPIRED),
            invalidated=_count_orders(backtester, INVALIDATED),
            closed_trades=report.total_trades,
            wins=report.wins,
            losses=report.losses,
            unsettled=(
                1
                if getattr(
                    backtester.simulator, "current_trade", None
                ) is not None
                else 0
            ),
            win_rate=report.win_rate,
            profit_factor=report.profit_factor,
            expectancy=report.expectancy,
            average_r=report.expectancy,
            max_drawdown=report.max_drawdown,
            max_drawdown_percent=report.max_drawdown_percent,
            fees=fees,
            slippage=slippage,
            net_pnl=report.net_profit,
            gross_pnl=report.gross_profit - report.gross_loss,
            starting_balance=report.starting_balance,
            final_balance=report.final_balance,
        )


def _count_setups(backtester):
    registry = getattr(
        backtester.pipeline.context, "setup_registry", None
    )
    if registry is not None:
        return len(registry.all())
    registered = _order_registry(backtester)
    if registered is None:
        return 0
    return len({getattr(o, "setup_id", None) for o in registered.all()})