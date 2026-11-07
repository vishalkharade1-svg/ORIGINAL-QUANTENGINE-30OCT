"""
====================================================

QuantEngine

Research Lab -- metrics (Phase 9B)

Deterministic metrics computed over a sequence of
CounterfactualOutcomes / SimulatedTrades. These follow the same
formulas the production PerformanceAnalytics uses (WIN := pnl>=0,
profit factor := gross profit / gross loss, expectancy := avg pnl,
max drawdown over an ordered equity curve) but are computed over
COUNTERFACTUAL trades only -- they never touch the production
ledger or TradeRegistry.
====================================================
"""

from statistics import median


def _iter_outcomes(items):
    for it in items:
        yield it


def metrics(outcomes_or_trades):
    """Compute the metric bundle for a set of COUNTERFACTUAL
    outcomes. Returns a plain dict (JSON-compatible)."""
    settled = [o for o in _iter_outcomes(outcomes_or_trades)
               if o.result in ("WIN", "LOSS")]
    wins = [o for o in settled if o.pnl >= 0]
    losses = [o for o in settled if o.pnl < 0]

    total = len(settled)
    gross_profit = sum(o.pnl for o in wins)
    gross_loss = abs(sum(o.pnl for o in losses))
    net = sum(o.pnl for o in settled)

    ordered = sorted(settled, key=lambda o: (o.exit_bar, o.decision_bar))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for o in ordered:
        equity += o.pnl
        if equity > peak:
            peak = equity
        else:
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

    rs = [o.r for o in settled]
    total_r = sum(rs)
    avg_r = (total_r / total) if total else 0.0
    med_r = median(rs) if rs else 0.0

    entry_bars = [o.bars_to_entry for o in outcomes_or_trades
                  if o.filled and o.bars_to_entry is not None]
    hold_bars = [o.bars_in_trade for o in outcomes_or_trades
                 if o.filled and o.bars_in_trade > 0]

    return {
        "opportunities_evaluated": len(list(_iter_outcomes(outcomes_or_trades))),
        "settled": total,
        "wins": len(wins),
        "losses": len(losses),
        "unsettled": len(list(_iter_outcomes(outcomes_or_trades))) - total,
        "win_rate": (len(wins) / total * 100.0) if total else 0.0,
        "profit_factor": (gross_profit / gross_loss) if gross_loss else (float("inf") if gross_profit > 0 else 0.0),
        "expectancy": (net / total) if total else 0.0,
        "net_pnl": net,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "max_drawdown": max_dd,
        "total_R": total_r,
        "avg_R": avg_r,
        "median_R": med_r,
        "avg_bars_to_entry": (sum(entry_bars) / len(entry_bars)) if entry_bars else 0.0,
        "avg_holding_bars": (sum(hold_bars) / len(hold_bars)) if hold_bars else 0.0,
        "settled_count": total,
    }
