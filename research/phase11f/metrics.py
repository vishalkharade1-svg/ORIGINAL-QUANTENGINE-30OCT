"""Phase 11F-1 research metrics (thin adapter, no second implementation).

All trade/position-return semantics reuse the certified stacks:

  * P&L decomposition: core.backtesting.accounting
    (gross_pnl / net_pnl / realized_r / classify_pnl)
  * Fold/pooled metrics: research.phase11e.common.trade_metrics
    (hand-tested + parity-tested against
    core.analytics.performance.PerformanceAnalytics in 11E)

This module only enforces the 11F-1 metric contract:

  gross_pnl - fees - slippage - funding = net_pnl
  funding = 0 (unmodeled minute-scale perps holds, disclosed)

Sharpe/Sortino use the repository's certified trade/position-return
semantics (pnl/notional, sqrt(n) scaling) via the reused
implementation — never recomputed here.
"""

from __future__ import annotations

from core.backtesting.accounting import (
    classify_pnl,
    gross_pnl,
    net_pnl,
    realized_r,
)
from research.phase11e.common import trade_metrics as _certified_trade_metrics

from research.phase11f.contracts import FUNDING_PER_TRADE

METRIC_CONTRACT_FIELDS = [
    "trades", "wins", "losses", "breakevens", "win_rate",
    "gross_pnl", "fees", "slippage", "funding", "net_pnl",
    "net_consistency_diff", "expectancy", "profit_factor",
    "max_drawdown", "sharpe", "sortino",
    "avg_r", "median_r", "largest_win", "largest_loss",
]


def research_trade_metrics(trades, starting_balance=2000.0):
    """Certified fold metrics + explicit funding leg.

    Input trades carry production-booked components:
      gross, commission, slippage, net (authoritative).
    Output adds funding (= 0, disclosed unmodeled) and asserts
    net_consistency_diff ~ 0 (production books net exactly).
    """
    base = _certified_trade_metrics(trades, starting_balance=starting_balance)
    funding = FUNDING_PER_TRADE * len(trades)
    net_check = base["gross_pnl"] - base["fees"] - base["slippage"] - funding
    out = dict(base)
    out["funding"] = float(funding)
    # Keep the certified consistency check (gross-fees-slippage vs
    # booked nets) and extend it with the funding leg.
    out["net_consistency_diff"] = abs(net_check - sum(t["net"] for t in trades))
    return out


__all__ = [
    "METRIC_CONTRACT_FIELDS",
    "research_trade_metrics",
    "classify_pnl",
    "gross_pnl",
    "net_pnl",
    "realized_r",
]
