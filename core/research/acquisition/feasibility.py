"""
====================================================

QuantEngine -- Phase 17 OOS sample-size feasibility.

Research-only, deterministic, stdlib-only. Recomputes
the fresh-data requirement from MEASURED funnel rates
(supplied by the caller, never fitted here) using the
frozen Phase-16 sample_math, then budgets the available
fresh span into adequate OOS periods.

Closed verdict vocabulary (gate words only):
  OOS_FEASIBLE / OOS_BLOCKED.

No hypothesis selection, no ranking, no parameter
search, no strategy logic -- arithmetic plus a gate.
====================================================
"""

from __future__ import annotations

from core.research.readiness.sample_math import (
    expected_fills,
    oos_span_bars,
    required_bars,
)

# Frozen 9M OOS protocol values (read-only reference;
# owned by core/research/oos/constants.py, never copied
# as new thresholds).
OOS_PERIODS = 6
DISCOVERY_FRACTION = 0.5
MIN_TRADES_PER_PERIOD = 10
MIN_TOTAL_TRADES = 60

FEASIBILITY_VERDICTS = ("OOS_FEASIBLE", "OOS_BLOCKED")


def recalculate_requirements(order_rate, fill_rate,
                             per_period_trades=MIN_TRADES_PER_PERIOD,
                             n_periods=OOS_PERIODS,
                             discovery_fraction=DISCOVERY_FRACTION):
    """Fresh-data requirement from measured funnel rates.

    Returns the theoretical minimum span plus the
    realistic-acquisition statement. Rates measured on N=2
    fills are point estimates: the theoretical span is a
    LOWER BOUND, unbounded above -- reported, not margined
    away with an invented safety factor.
    """
    per_period_bars = required_bars(
        per_period_trades, order_rate, fill_rate)
    oos_span = per_period_bars * int(n_periods)
    total_span = oos_span_bars(
        per_period_bars, int(n_periods), discovery_fraction)
    expected_per_period = expected_fills(
        per_period_bars, order_rate, fill_rate)
    return {
        "order_rate": float(order_rate),
        "fill_rate": float(fill_rate),
        "per_period_trades": int(per_period_trades),
        "n_periods": int(n_periods),
        "discovery_fraction": float(discovery_fraction),
        "per_period_bars": per_period_bars,
        "oos_span_bars": oos_span,
        "total_span_bars": total_span,
        "expected_fills_per_period": expected_per_period,
        "formula": "bars=trades/(order_rate*fill_rate); "
                   "oos=per_period*periods; "
                   "total=oos/(1-discovery_fraction)",
        "realistic_requirement": (
            "AT LEAST %(total).0f bars (lower bound; rate "
            "uncertainty from N=2 fills is unbounded above)"
            % {"total": total_span}),
    }


def budget_periods(available_bars, per_period_bars,
                   n_periods=OOS_PERIODS):
    """How many adequate OOS periods fit in the fresh span."""
    available_bars = float(available_bars)
    per_period_bars = float(per_period_bars)
    if per_period_bars <= 0.0:
        raise ValueError("per_period_bars must be positive")
    adequate = int(available_bars // per_period_bars)
    verdict = ("OOS_FEASIBLE" if adequate >= int(n_periods)
               else "OOS_BLOCKED")
    return {
        "available_bars": available_bars,
        "per_period_bars": per_period_bars,
        "adequate_periods": adequate,
        "required_periods": int(n_periods),
        "verdict": verdict,
    }
