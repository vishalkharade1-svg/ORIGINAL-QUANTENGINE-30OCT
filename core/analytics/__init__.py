"""
====================================================

QuantEngine

Performance Analytics Package

====================================================

Consumes the SHARED TradeRegistry + Account that every mode
(Backtest, Paper, Live Broker) books into and produces the
portfolio performance report:

    - trade statistics (wins/losses/win rate/profit factor)
    - risk-adjusted returns (Sharpe / Sortino, drawdown)
    - directional breakdown (longs vs shorts)
    - the trade-based equity curve

Perfectly forward-looking: the same Trade objects and Account
state the analytics read are the exact objects the other
engines wrote, so no reconciliation is needed.
"""

from core.analytics.performance import (
    PerformanceAnalytics,
    PerformanceReport,
)

__all__ = [
    "PerformanceAnalytics",
    "PerformanceReport",
]