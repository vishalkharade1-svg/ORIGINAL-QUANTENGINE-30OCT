"""
====================================================
QuantEngine - Queue Dynamics & Adverse Selection Model
Phase 171/172 Research Track

Models queue position, fill probabilities under Poisson/exponential
trade arrivals, post-only order boundary guards, and adverse selection
penalties for passive liquidity provision.
Separates empirical venue evidence from simulation assumptions.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Dict, Any


@dataclass(frozen=True, slots=True)
class PostOnlyGuardResult:
    allowed: bool
    limit_price: Decimal
    best_bid: Decimal
    best_ask: Decimal
    side: str
    rejection_reason: str | None


@dataclass(frozen=True, slots=True)
class QueueDynamicsMetrics:
    queue_depth_ahead: Decimal
    order_size: Decimal
    arrival_rate_per_sec: Decimal
    horizon_seconds: Decimal
    fill_probability: Decimal  # Kept for backward compatibility with phase 171
    expected_wait_seconds: Decimal
    adverse_selection_bps: Decimal
    adverse_selection_cost_usd: Decimal
    net_maker_benefit_usd: Decimal


@dataclass(frozen=True, slots=True)
class GranularQueueMetrics:
    """Rigorous breakdown of queue metrics required by Phase 172 contract."""
    queue_depth_ahead: Decimal
    order_size: Decimal
    volume_rate_per_sec: Decimal
    horizon_seconds: Decimal
    
    # 1. Probability of any fill (volume reaching our price)
    p_any_fill: Decimal
    
    # 2. Probability of complete fill (volume consuming queue ahead + our size)
    p_complete_fill: Decimal
    
    # 3. Expected time to first fill (seconds)
    expected_time_first_fill_sec: Decimal
    
    # 4. Expected time to complete fill (seconds)
    expected_time_complete_fill_sec: Decimal
    
    # 5. Expected filled quantity (contracts)
    expected_filled_quantity: Decimal
    
    # 6. Cancellation / expiration probability
    p_unfilled_or_expired: Decimal
    
    # 7. Adverse selection cost conditional on fill (USD)
    adverse_selection_cost_usd: Decimal
    
    # 8. Unfilled opportunity cost (USD)
    unfilled_opportunity_cost_usd: Decimal
    
    # Classification: SIMULATION_ASSUMPTION vs EMPIRICAL_OBSERVATION
    evidence_classification: str = "SIMULATION_ASSUMPTION"


def validate_post_only(
    side: str,
    limit_price: Decimal | float | str,
    best_bid: Decimal | float | str,
    best_ask: Decimal | float | str,
) -> PostOnlyGuardResult:
    """Validate that a limit order does not cross the spread (Post-Only guard).
    
    A BUY limit must be strictly less than best_ask (or <= best_bid to join/rest).
    A SELL limit must be strictly greater than best_bid (or >= best_ask to join/rest).
    """
    s = str(side).upper()
    lp = Decimal(str(limit_price))
    bb = Decimal(str(best_bid))
    ba = Decimal(str(best_ask))

    if bb >= ba:
        return PostOnlyGuardResult(
            allowed=False,
            limit_price=lp,
            best_bid=bb,
            best_ask=ba,
            side=s,
            rejection_reason="Inverted or crossed book (best_bid >= best_ask)",
        )

    if s == "BUY":
        if lp >= ba:
            return PostOnlyGuardResult(
                allowed=False,
                limit_price=lp,
                best_bid=bb,
                best_ask=ba,
                side=s,
                rejection_reason=f"BUY limit {lp} crosses best ask {ba} (would execute as taker)",
            )
        return PostOnlyGuardResult(
            allowed=True,
            limit_price=lp,
            best_bid=bb,
            best_ask=ba,
            side=s,
            rejection_reason=None,
        )
    elif s == "SELL":
        if lp <= bb:
            return PostOnlyGuardResult(
                allowed=False,
                limit_price=lp,
                best_bid=bb,
                best_ask=ba,
                side=s,
                rejection_reason=f"SELL limit {lp} crosses best bid {bb} (would execute as taker)",
            )
        return PostOnlyGuardResult(
            allowed=True,
            limit_price=lp,
            best_bid=bb,
            best_ask=ba,
            side=s,
            rejection_reason=None,
        )
    else:
        return PostOnlyGuardResult(
            allowed=False,
            limit_price=lp,
            best_bid=bb,
            best_ask=ba,
            side=s,
            rejection_reason=f"Invalid side {s}",
        )


def evaluate_queue_dynamics(
    queue_depth_ahead: Decimal | float | str,
    order_size: Decimal | float | str,
    volume_rate_per_sec: Decimal | float | str,
    horizon_seconds: Decimal | float | str,
    notional_usd: Decimal | float | str,
    fee_savings_usd: Decimal | float | str,
    adverse_selection_bps: Decimal | float | str = Decimal("2.0"),
) -> QueueDynamicsMetrics:
    """Evaluate queue wait time, fill probability, and net benefit after adverse selection."""
    qd = Decimal(str(queue_depth_ahead))
    os = Decimal(str(order_size))
    vr = Decimal(str(volume_rate_per_sec))
    hz = Decimal(str(horizon_seconds))
    notional = Decimal(str(notional_usd))
    fee_sav = Decimal(str(fee_savings_usd))
    as_bps = Decimal(str(adverse_selection_bps))

    if qd < Decimal("0") or os <= Decimal("0") or hz <= Decimal("0") or notional <= Decimal("0"):
        raise ValueError("Queue depth, size, horizon, and notional must be positive")

    # Expected wait time to consume queue ahead
    if vr > Decimal("0"):
        wait_sec = (qd / vr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_queue = float(qd + os)
        intensity = float(vr * hz) / total_queue if total_queue > 0 else 1.0
        p_fill = Decimal(str(round(1.0 - math.exp(-intensity), 6)))
        if p_fill > Decimal("1.0"):
            p_fill = Decimal("1.0")
    else:
        wait_sec = Decimal("999999.00")
        p_fill = Decimal("0.000000")

    adverse_cost = (notional * as_bps / Decimal("10000")).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )

    net_benefit = ((fee_sav - adverse_cost) * p_fill).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )

    return QueueDynamicsMetrics(
        queue_depth_ahead=qd,
        order_size=os,
        arrival_rate_per_sec=vr,
        horizon_seconds=hz,
        fill_probability=p_fill,
        expected_wait_seconds=wait_sec,
        adverse_selection_bps=as_bps,
        adverse_selection_cost_usd=adverse_cost,
        net_maker_benefit_usd=net_benefit,
    )


def evaluate_granular_queue_behavior(
    queue_depth_ahead: Decimal | float | str,
    order_size: Decimal | float | str,
    volume_rate_per_sec: Decimal | float | str,
    horizon_seconds: Decimal | float | str,
    notional_usd: Decimal | float | str,
    expected_target_profit_usd: Decimal | float | str,
    adverse_selection_bps: Decimal | float | str = Decimal("2.0"),
    is_empirical: bool = False,
) -> GranularQueueMetrics:
    """
    Rigorously separate:
    1. Probability of any fill
    2. Probability of complete fill
    3. Expected time to first fill
    4. Expected time to complete fill
    5. Expected filled quantity
    6. Cancellation / expiration probability
    7. Adverse selection conditional on a fill
    8. Opportunity cost of an unfilled order
    """
    qd = Decimal(str(queue_depth_ahead))
    os = Decimal(str(order_size))
    vr = Decimal(str(volume_rate_per_sec))
    hz = Decimal(str(horizon_seconds))
    notional = Decimal(str(notional_usd))
    target_prof = Decimal(str(expected_target_profit_usd))
    as_bps = Decimal(str(adverse_selection_bps))

    if any(d.is_nan() or d.is_infinite() for d in [qd, os, vr, hz, notional, target_prof, as_bps]):
        raise ValueError("Inputs must be finite")

    if qd < Decimal("0") or os <= Decimal("0") or hz <= Decimal("0") or notional <= Decimal("0") or vr < Decimal("0") or target_prof < Decimal("0"):
        raise ValueError("Inputs must be non-negative and positive where required")

    expected_total_volume = float(vr * hz)
    
    # 1. P(any fill): volume reaching our position (consuming qd)
    if float(qd) > 0:
        intensity_first = expected_total_volume / float(qd)
        p_any = Decimal(str(round(1.0 - math.exp(-intensity_first), 6)))
        time_first_sec = (qd / vr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if vr > 0 else Decimal("999999.00")
    else:
        p_any = Decimal("1.000000")
        time_first_sec = Decimal("0.00")

    # 2. P(complete fill): volume consuming qd + os
    total_queue = float(qd + os)
    intensity_complete = expected_total_volume / total_queue if total_queue > 0 else 1.0
    p_complete = Decimal(str(round(1.0 - math.exp(-intensity_complete), 6)))
    if p_complete > Decimal("1.0"):
        p_complete = Decimal("1.0")
    
    time_complete_sec = ((qd + os) / vr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if vr > 0 else Decimal("999999.00")

    # 5. Expected filled quantity
    # Linear interpolation between any fill and complete fill:
    # E[Q] = os * p_complete + (os / 2) * (p_any - p_complete)
    exp_qty = (os * p_complete + (os / Decimal("2")) * (p_any - p_complete)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 6. Cancellation / expiration probability
    p_unfilled = Decimal("1.000000") - p_complete

    # 7. Adverse selection cost
    adverse_cost = (notional * as_bps / Decimal("10000")).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )

    # 8. Unfilled opportunity cost: if order expires unfilled, missed target profit
    opp_cost = (target_prof * p_unfilled).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )

    classification = "EMPIRICAL_OBSERVATION" if is_empirical else "SIMULATION_ASSUMPTION"

    return GranularQueueMetrics(
        queue_depth_ahead=qd,
        order_size=os,
        volume_rate_per_sec=vr,
        horizon_seconds=hz,
        p_any_fill=p_any,
        p_complete_fill=p_complete,
        expected_time_first_fill_sec=time_first_sec,
        expected_time_complete_fill_sec=time_complete_sec,
        expected_filled_quantity=exp_qty,
        p_unfilled_or_expired=p_unfilled,
        adverse_selection_cost_usd=adverse_cost,
        unfilled_opportunity_cost_usd=opp_cost,
        evidence_classification=classification,
    )
