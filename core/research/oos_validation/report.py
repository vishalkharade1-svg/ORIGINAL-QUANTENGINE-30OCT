"""
====================================================
QuantEngine -- Phase 18 OOS aggregation + gates.

Research-only, deterministic, stdlib-only. Pure
functions over per-period funnel dicts produced by
execution.run_frozen_oos. No strategy logic, no
threshold invention: all gates reuse the frozen 9M
protocol constants by read-only reference.

Closed vocabularies only. Insufficient evidence is
INCONCLUSIVE/UNAVAILABLE, never a silent pass; one
good period is never robustness.
====================================================
"""

from __future__ import annotations


def classify_period(funnel):
    """Classify one executed OOS period.

    0 bars/orders/fills evidence -> UNAVAILABLE (no eligible
    evidence) when orders == 0, else INCONCLUSIVE (evidence
    below the frozen 10-trade settling gate). Settled
    classification (PROMISING/VALIDATED/REJECTED) requires
    >= 10 completed trades and is decided by net economics;
    with < 10 trades the period can never be settled.
    """
    orders = int(funnel.get("orders", 0) or 0)
    fills = int(funnel.get("completed_trades", 0) or 0)
    if orders == 0 and fills == 0:
        return ("UNAVAILABLE", "no orders or fills in period")
    if fills < 10:
        return ("INCONCLUSIVE", "below 10-trade settling gate")
    gross = float(funnel.get("gross_pnl", 0.0) or 0.0)
    wins = int(funnel.get("wins", 0) or 0)
    losses = int(funnel.get("losses", 0) or 0)
    if gross > 0 and wins > losses:
        return ("PROMISING", "settled positive but single-period")
    if gross <= 0:
        return ("REJECTED", "settled non-positive net")
    return ("INCONCLUSIVE", "settled ambiguous")


def aggregate_results(per_period):
    """Aggregate executed per-period funnels (periods preserved)."""
    total_bars = sum(int(p.get("bars", 0) or 0) for p in per_period)
    total_orders = sum(int(p.get("orders", 0) or 0) for p in per_period)
    total_fills = sum(int(p.get("completed_trades", 0) or 0) for p in per_period)
    wins = sum(int(p.get("wins", 0) or 0) for p in per_period)
    losses = sum(int(p.get("losses", 0) or 0) for p in per_period)
    gross = sum(float(p.get("gross_pnl", 0.0) or 0.0) for p in per_period)
    statuses = [p.get("status", "INCONCLUSIVE") for p in per_period]
    survived = sum(1 for s in statuses if s in ("PROMISING", "VALIDATED"))
    rejected = sum(1 for s in statuses if s == "REJECTED")
    inconclusive = sum(1 for s in statuses if s == "INCONCLUSIVE")
    unavailable = sum(1 for s in statuses if s == "UNAVAILABLE")
    tested = len(per_period)
    return {
        "total_periods": tested,
        "tested_periods": tested,
        "survived": survived,
        "rejected": rejected,
        "inconclusive": inconclusive,
        "unavailable": unavailable,
        "survival_ratio": (survived / tested) if tested else 0.0,
        "total_bars": total_bars,
        "total_orders": total_orders,
        "total_fills": total_fills,
        "total_completed_trades": total_fills,
        "wins": wins,
        "losses": losses,
        "gross_pnl": gross,
    }


def decide_final(agg, min_total_trades=60, min_surviving=5):
    """Final Phase-18 decision from aggregate evidence.

    OOS_BLOCKED when the sample cannot support validation
    (< min_total_trades completed); otherwise the frozen 9M
    survival ladder applies. Never promotes on aggregate P/L
    alone.
    """
    total = int(agg.get("total_completed_trades", 0) or 0)
    survived = int(agg.get("survived", 0) or 0)
    tested = int(agg.get("tested_periods", 0) or 0)
    if total < int(min_total_trades):
        return ("OOS_BLOCKED", "only %d completed trades (< %d)" % (
            total, int(min_total_trades)))
    if survived >= int(min_surviving) and tested >= 6:
        return ("VALIDATED_RESEARCH_ONLY", "frozen survival gate met")
    if survived > 0:
        return ("PROMISING", "partial survival without robustness")
    return ("REJECTED", "sufficient sample without survival")
