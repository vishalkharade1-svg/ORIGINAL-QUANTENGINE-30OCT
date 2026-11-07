"""
====================================================

Institutional Account State

====================================================
"""

from dataclasses import dataclass

from core.common.base_state import BaseState


@dataclass(slots=True)
class AccountState(BaseState):

    # -------------------------------------------------
    # Capital
    # -------------------------------------------------

    starting_balance: float = 0.0

    balance: float = 0.0

    equity: float = 0.0

    free_margin: float = 0.0

    used_margin: float = 0.0

    # -------------------------------------------------
    # Profit & Loss
    # -------------------------------------------------

    floating_pnl: float = 0.0

    realized_pnl: float = 0.0

    unrealized_pnl: float = 0.0

    daily_pnl: float = 0.0

    weekly_pnl: float = 0.0

    monthly_pnl: float = 0.0

    # Phase 12 loss-window keys (UTC calendar). The
    # daily/weekly/monthly PnL accumulators above only mean
    # "today / this week / this month" while these keys match
    # the candle timestamp being processed; Account.
    # roll_pnl_windows() resets a stale window before the
    # RiskEngine loss-limit gate reads it. Empty key = window
    # never rolled yet (first candle seeds it, never a reset
    # on missing timestamps).
    pnl_day_key: str = ""

    pnl_week_key: str = ""

    pnl_month_key: str = ""

    # -------------------------------------------------
    # Drawdown
    # -------------------------------------------------

    peak_equity: float = 0.0

    drawdown: float = 0.0

    drawdown_percent: float = 0.0

    max_drawdown: float = 0.0

    # -------------------------------------------------
    # Portfolio Risk
    # -------------------------------------------------

    portfolio_risk: float = 0.0

    exposure: float = 0.0

    open_positions: int = 0

    # -------------------------------------------------
    # Performance Statistics
    # -------------------------------------------------

    total_trades: int = 0

    winning_trades: int = 0

    losing_trades: int = 0

    breakeven_trades: int = 0

    consecutive_wins: int = 0

    consecutive_losses: int = 0

    win_rate: float = 0.0

    # NOTE (phase 9P-b): `profit_factor` and `expectancy` are NOT
    # captured here. The account is a counter-only accumulation
    # (total/winning/losing trades) and does not retain per-trade
    # outcomes, so profit factor and expectancy cannot be derived
    # from `Account` alone. The single canonical calculation for
    # both metrics lives in core.analytics.performance
    # (PerformanceAnalytics / PerformanceReport), which derives
    # them from the completed-trade ledger (core.backtesting.
    # trade_registry, status == "CLOSED", net Trade.pnl). Declaring
    # duplicate fields here would create a second, misleading
    # accounting surface.

    # -------------------------------------------------
    # Trading Controls
    # -------------------------------------------------

    trading_enabled: bool = True

    kill_switch: bool = False

    paper_mode: bool = True

    auto_compounding: bool = True

    profit_protection: bool = True

    # -------------------------------------------------
    # Trading Mode
    # -------------------------------------------------

    trading_mode: str = "NORMAL"