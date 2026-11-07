"""
====================================================

QuantEngine -- Phase 16 evidence-readiness math.

Pure, deterministic sample-size feasibility functions for
OOS planning. Research-only: no strategy logic, no
thresholds, no execution, no I/O, no randomness.

All rates are inputs (measured elsewhere, never fitted
here). Fill-rate and opportunity-rate estimates carry
their own sample-size caveat: they are point estimates
from tiny samples unless stated otherwise.
====================================================
"""

from __future__ import annotations


def expected_orders(bars: float, orders_per_bar: float) -> float:
    """Expected minted orders for a bar span at an observed rate."""
    return float(bars) * float(orders_per_bar)


def expected_fills(bars: float, orders_per_bar: float,
                   fill_rate: float) -> float:
    """Expected fills = bars * order-rate * fill-rate."""
    return float(bars) * float(orders_per_bar) * float(fill_rate)


def required_bars(fills_needed: float, orders_per_bar: float,
                  fill_rate: float) -> float:
    """Bars needed for `fills_needed` fills at observed rates.

    Raises ValueError on non-positive rates (division by a
    zero/negative rate would fabricate feasibility).
    """
    orders_per_bar = float(orders_per_bar)
    fill_rate = float(fill_rate)
    if orders_per_bar <= 0.0 or fill_rate <= 0.0:
        raise ValueError(
            "rates must be positive: orders_per_bar=%r "
            "fill_rate=%r" % (orders_per_bar, fill_rate))
    return float(fills_needed) / (orders_per_bar * fill_rate)


def oos_span_bars(per_period_bars: float, n_periods: int,
                  discovery_fraction: float = 0.5) -> float:
    """Total span for N OOS periods plus discovery headroom.

    The frozen 9M protocol validates over the trailing half
    with discovery on the leading half, hence ~2x the OOS
    span. Raises ValueError on invalid inputs.
    """
    per_period_bars = float(per_period_bars)
    n_periods = int(n_periods)
    discovery_fraction = float(discovery_fraction)
    if per_period_bars <= 0.0 or n_periods <= 0:
        raise ValueError("need positive per-period bars/periods")
    if not 0.0 <= discovery_fraction < 1.0:
        raise ValueError("discovery_fraction must be in [0, 1)")
    oos_span = per_period_bars * n_periods
    if discovery_fraction <= 0.0:
        return oos_span
    return oos_span / (1.0 - discovery_fraction)


def sample_ladder(n_trades: int, per_period_min: int,
                  total_min: int) -> str:
    """Closed sample-adequacy vocabulary (deterministic).

    Thresholds are CALLER-supplied (frozen protocol values),
    never invented here.
    """
    n = int(n_trades)
    if n < int(per_period_min):
        return "INSUFFICIENT_SAMPLE"
    if n < int(total_min):
        return "INCONCLUSIVE"
    return "SUFFICIENT_FOR_ROBUSTNESS_REVIEW"
