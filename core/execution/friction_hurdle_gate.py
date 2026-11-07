"""
====================================================
QuantEngine - Friction Hurdle Gate
Phase 171 Execution Edge Protection Track

Filters trade setups based on friction-to-reward hurdles,
ensuring scalps and micro-lot trades are rejected when
exchange commissions/GST consume excessive expected profit.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

from core.execution.maker_execution_model import (
    calculate_round_trip,
    ExecutionStyle,
    DEFAULT_GST_RATE,
)


@dataclass(frozen=True)
class HurdleVerdict:
    allowed: bool
    rejection_reason: str | None
    execution_style: ExecutionStyle
    entry_price: Decimal
    target_price: Decimal
    stop_price: Decimal
    target_points: Decimal
    risk_points: Decimal
    gross_target_usd: Decimal
    round_trip_fee_usd: Decimal
    net_target_usd: Decimal
    fee_to_target_pct: Decimal
    post_fee_rr: Decimal
    breakeven_points: Decimal

    @property
    def passed(self) -> bool:
        return self.allowed

    @property
    def fee_ratio_pct(self) -> Decimal:
        return self.fee_to_target_pct

    @property
    def breakeven_multiple(self) -> Decimal:
        if self.breakeven_points > Decimal("0"):
            return (self.target_points / self.breakeven_points).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0")

    @property
    def rule1_fee_ratio_pass(self) -> bool:
        return self.fee_to_target_pct <= Decimal("40.0")

    @property
    def rule2_target_multiple_pass(self) -> bool:
        return self.breakeven_multiple >= Decimal("2.0")

    @property
    def rule3_post_fee_rr_pass(self) -> bool:
        return self.post_fee_rr >= Decimal("1.25")


FrictionHurdleResult = HurdleVerdict


def _parse_finite_decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        d = Decimal(str(val))
        if d.is_nan() or d.is_infinite():
            return None
        return d
    except Exception:
        return None


class FrictionHurdleGate:
    """Evaluates proposed trade setups against non-bypassable friction hurdles."""

    @staticmethod
    def evaluate(
        entry_price: Decimal | float | str | None = None,
        target_price: Decimal | float | str | None = None,
        stop_price: Decimal | float | str | None = None,
        quantity: Decimal | float | str = Decimal("1"),
        contract_multiplier: Decimal | float | str = Decimal("0.001"),
        execution_style: ExecutionStyle = ExecutionStyle.TAKER,
        max_fee_ratio_pct: Decimal | float | str = Decimal("40.0"),
        min_post_fee_rr: Decimal | float | str = Decimal("1.25"),
        min_breakeven_margin_multiple: Decimal | float | str = Decimal("2.0"),
        gross_target_points: Decimal | float | str | None = None,
        stop_loss_points: Decimal | float | str | None = None,
        round_trip_fee_points: Decimal | float | str | None = None,
    ) -> HurdleVerdict:
        return evaluate_friction_hurdle(
            entry_price=entry_price,
            target_price=target_price,
            stop_price=stop_price,
            quantity=quantity,
            contract_multiplier=contract_multiplier,
            execution_style=execution_style,
            max_fee_ratio_pct=max_fee_ratio_pct,
            min_post_fee_rr=min_post_fee_rr,
            min_breakeven_margin_multiple=min_breakeven_margin_multiple,
            gross_target_points=gross_target_points,
            stop_loss_points=stop_loss_points,
            round_trip_fee_points=round_trip_fee_points,
        )


def evaluate_friction_hurdle(
    entry_price: Decimal | float | str | None = None,
    target_price: Decimal | float | str | None = None,
    stop_price: Decimal | float | str | None = None,
    quantity: Decimal | float | str = Decimal("1"),
    contract_multiplier: Decimal | float | str = Decimal("0.001"),
    execution_style: ExecutionStyle = ExecutionStyle.TAKER,
    max_fee_ratio_pct: Decimal | float | str = Decimal("40.0"),
    min_post_fee_rr: Decimal | float | str = Decimal("1.25"),
    min_breakeven_margin_multiple: Decimal | float | str = Decimal("2.0"),
    gross_target_points: Decimal | float | str | None = None,
    stop_loss_points: Decimal | float | str | None = None,
    round_trip_fee_points: Decimal | float | str | None = None,
) -> HurdleVerdict:
    """Evaluate whether a proposed trade setup overcomes the execution friction hurdle."""
    # Fail-closed helper
    def _fail_closed(reason: str, ep: Decimal = Decimal("0"), tp: Decimal = Decimal("0"), sp: Decimal = Decimal("0")) -> HurdleVerdict:
        return HurdleVerdict(
            allowed=False,
            rejection_reason=reason,
            execution_style=execution_style,
            entry_price=ep,
            target_price=tp,
            stop_price=sp,
            target_points=Decimal("0"),
            risk_points=Decimal("0"),
            gross_target_usd=Decimal("0"),
            round_trip_fee_usd=Decimal("0"),
            net_target_usd=Decimal("0"),
            fee_to_target_pct=Decimal("100"),
            post_fee_rr=Decimal("0"),
            breakeven_points=Decimal("0"),
        )

    # Alternate signature: explicit points
    if gross_target_points is not None and round_trip_fee_points is not None:
        target_pts = _parse_finite_decimal(gross_target_points)
        fee_pts = _parse_finite_decimal(round_trip_fee_points)
        risk_pts = _parse_finite_decimal(stop_loss_points if stop_loss_points is not None else "0")
        cm = _parse_finite_decimal(contract_multiplier)

        if target_pts is None or fee_pts is None or risk_pts is None or cm is None:
            return _fail_closed("Friction hurdle failed: non-finite or invalid points/multiplier input")
        if target_pts <= Decimal("0"):
            return _fail_closed("Friction hurdle failed: non-positive gross target points")
        if fee_pts < Decimal("0"):
            return _fail_closed("Friction hurdle failed: negative round-trip fee points")
        if risk_pts < Decimal("0"):
            return _fail_closed("Friction hurdle failed: negative stop loss points")

        max_fee_pct = _parse_finite_decimal(max_fee_ratio_pct) or Decimal("40.0")
        min_margin = _parse_finite_decimal(min_breakeven_margin_multiple) or Decimal("2.0")
        min_rr = _parse_finite_decimal(min_post_fee_rr) or Decimal("1.25")

        fee_to_target_pct = (
            (fee_pts / target_pts) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        be_pts = fee_pts
        be_mult = (
            target_pts / be_pts
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if be_pts > Decimal("0") else Decimal("0")
        net_pts = target_pts - fee_pts
        total_risk_pts = risk_pts + fee_pts
        post_fee_rr = (
            net_pts / total_risk_pts
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total_risk_pts > Decimal("0") else Decimal("0")

        allowed = True
        reason = None
        if fee_to_target_pct > max_fee_pct:
            allowed = False
            reason = f"Friction hurdle failed: fee ratio {fee_to_target_pct}% exceeding max allowed {max_fee_pct}%"
        elif be_mult < min_margin:
            allowed = False
            reason = f"Friction hurdle failed: target multiple {be_mult}x below required {min_margin}x"
        elif post_fee_rr < min_rr:
            allowed = False
            reason = f"Friction hurdle failed: post-fee R:R {post_fee_rr} below required {min_rr}"

        return HurdleVerdict(
            allowed=allowed,
            rejection_reason=reason,
            execution_style=execution_style,
            entry_price=Decimal("0"),
            target_price=target_pts,
            stop_price=risk_pts,
            target_points=target_pts,
            risk_points=risk_pts,
            gross_target_usd=target_pts * cm,
            round_trip_fee_usd=fee_pts * cm,
            net_target_usd=net_pts * cm,
            fee_to_target_pct=fee_to_target_pct,
            post_fee_rr=post_fee_rr,
            breakeven_points=be_pts,
        )

    # Standard signature: price levels
    ep = _parse_finite_decimal(entry_price)
    tp = _parse_finite_decimal(target_price)
    sp = _parse_finite_decimal(stop_price)
    qty = _parse_finite_decimal(quantity)
    cm = _parse_finite_decimal(contract_multiplier)
    max_fee_pct = _parse_finite_decimal(max_fee_ratio_pct)
    min_rr = _parse_finite_decimal(min_post_fee_rr)
    min_margin = _parse_finite_decimal(min_breakeven_margin_multiple)

    if (
        ep is None or tp is None or sp is None or qty is None or cm is None
        or max_fee_pct is None or min_rr is None or min_margin is None
    ):
        return _fail_closed("Friction hurdle failed: missing, malformed, or non-finite inputs")

    if ep <= Decimal("0") or tp <= Decimal("0") or sp <= Decimal("0"):
        return _fail_closed("Friction hurdle failed: non-positive price level", ep=ep or Decimal("0"), tp=tp or Decimal("0"), sp=sp or Decimal("0"))

    if qty <= Decimal("0") or cm <= Decimal("0"):
        return _fail_closed("Friction hurdle failed: non-positive quantity or contract multiplier", ep=ep, tp=tp, sp=sp)

    target_pts = abs(tp - ep)
    risk_pts = abs(ep - sp)

    if target_pts <= Decimal("0") or risk_pts <= Decimal("0"):
        return _fail_closed("Invalid target or stop price (zero distance)", ep=ep, tp=tp, sp=sp)

    # Calculate round-trip fees on entry and target exit
    rt = calculate_round_trip(ep, tp, qty, cm, execution_style)
    gross_target = abs(rt.gross_pnl)
    total_fees = rt.total_fees
    net_target = gross_target - total_fees

    fee_to_target_pct = (total_fees / gross_target * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Post-fee risk includes stop-out loss + entry fee + stop exit fee
    # For conservative estimation, stop loss fee is approximately equal to entry fee
    total_risk_usd = (risk_pts * cm * qty) + total_fees
    post_fee_rr = (net_target / total_risk_usd).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    breakeven_pts = rt.breakeven_points

    # Gate 1: Fee to target ratio
    if fee_to_target_pct > max_fee_pct:
        reason = (
            f"Friction hurdle failed: round-trip fees ({total_fees:.4f} USD) consume "
            f"{fee_to_target_pct:.1f}% of gross target ({gross_target:.4f} USD), "
            f"exceeding max allowed {max_fee_pct:.1f}%"
        )
        return HurdleVerdict(
            allowed=False,
            rejection_reason=reason,
            execution_style=execution_style,
            entry_price=ep,
            target_price=tp,
            stop_price=sp,
            target_points=target_pts,
            risk_points=risk_pts,
            gross_target_usd=gross_target,
            round_trip_fee_usd=total_fees,
            net_target_usd=net_target,
            fee_to_target_pct=fee_to_target_pct,
            post_fee_rr=post_fee_rr,
            breakeven_points=breakeven_pts,
        )

    # Gate 2: Breakeven margin multiple
    if target_pts < (breakeven_pts * min_margin):
        reason = (
            f"Friction hurdle failed: target {target_pts:.2f} pts is less than "
            f"{min_margin:.1f}x breakeven hurdle ({breakeven_pts:.2f} pts)"
        )
        return HurdleVerdict(
            allowed=False,
            rejection_reason=reason,
            execution_style=execution_style,
            entry_price=ep,
            target_price=tp,
            stop_price=sp,
            target_points=target_pts,
            risk_points=risk_pts,
            gross_target_usd=gross_target,
            round_trip_fee_usd=total_fees,
            net_target_usd=net_target,
            fee_to_target_pct=fee_to_target_pct,
            post_fee_rr=post_fee_rr,
            breakeven_points=breakeven_pts,
        )

    # Gate 3: Post-fee R:R hurdle
    if post_fee_rr < min_rr:
        reason = (
            f"Friction hurdle failed: post-fee R:R {post_fee_rr:.2f} is below "
            f"minimum requirement {min_rr:.2f}"
        )
        return HurdleVerdict(
            allowed=False,
            rejection_reason=reason,
            execution_style=execution_style,
            entry_price=ep,
            target_price=tp,
            stop_price=sp,
            target_points=target_pts,
            risk_points=risk_pts,
            gross_target_usd=gross_target,
            round_trip_fee_usd=total_fees,
            net_target_usd=net_target,
            fee_to_target_pct=fee_to_target_pct,
            post_fee_rr=post_fee_rr,
            breakeven_points=breakeven_pts,
        )

    return HurdleVerdict(
        allowed=True,
        rejection_reason=None,
        execution_style=execution_style,
        entry_price=ep,
        target_price=tp,
        stop_price=sp,
        target_points=target_pts,
        risk_points=risk_pts,
        gross_target_usd=gross_target,
        round_trip_fee_usd=total_fees,
        net_target_usd=net_target,
        fee_to_target_pct=fee_to_target_pct,
        post_fee_rr=post_fee_rr,
        breakeven_points=breakeven_pts,
    )
