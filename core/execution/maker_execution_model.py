"""
====================================================
QuantEngine - Maker Execution Model & Friction Engine
Phase 171/172 Execution Research Track

Models passive limit (maker) execution economics,
asymmetric leg execution (maker entry + taker exit),
partial fills, instrument constraints (tick size, lot step),
fee decomposition (base fee + GST), break-even spread
capture hurdles, and rebate tiers against venue evidence.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING
from enum import Enum
from typing import Dict, Any, List


class ExecutionStyle(str, Enum):
    TAKER = "TAKER"
    MAKER = "MAKER"
    REBATE_VIP = "REBATE_VIP"


# Delta India Standard Fee Rates (authoritatively verified from Phase 168/169 records)
# GST Rate in India is standard 18% on broker commission
DEFAULT_GST_RATE = Decimal("0.18")

# Standard Taker: 0.05% (0.0005) base fee
TAKER_BASE_RATE = Decimal("0.0005")

# Standard Maker: 0.02% (0.0002) base fee
MAKER_BASE_RATE = Decimal("0.0002")

# VIP / Liquidity Provider Tier: -0.01% (-0.0001) rebate
REBATE_BASE_RATE = Decimal("-0.0001")


@dataclass(frozen=True, slots=True)
class FeeScheduleProvenance:
    venue: str = "Delta Exchange India"
    verification_source: str = "Authenticated Phase 168/169 testnet captures (research/captures/phase168_delta_reconciled/)"
    brokerage_commission_taker_bps: Decimal = Decimal("5.00")
    brokerage_commission_maker_bps: Decimal = Decimal("2.00")
    gst_rate_pct: Decimal = Decimal("18.00")
    effective_taker_rate_bps: Decimal = Decimal("5.90")
    effective_maker_rate_bps: Decimal = Decimal("2.36")
    settlement_currency: str = "USD"
    verified_contract: str = "BTCUSD (multiplier=0.001, tick=0.10, step=1)"
    assumptions: List[str] = field(default_factory=lambda: [
        "Verified contract BTCUSD Product ID 84 tick_size=0.10 from authoritative MCP payload",
        "Rebate VIP tier (-1.0 bps) is a simulation scenario; standard account is Maker (2.36 bps effective)",
        "GST is 18% on brokerage fee only, zero GST applied to rebates or funding",
        "Funding charges apply only when position is held across 8-hour settlement intervals",
    ])


@dataclass(frozen=True, slots=True)
class FeeDecomposition:
    style: ExecutionStyle
    notional: Decimal
    base_rate: Decimal
    base_fee: Decimal
    gst_rate: Decimal
    gst: Decimal
    total_fee: Decimal
    effective_rate_bps: Decimal


@dataclass(frozen=True, slots=True)
class RoundTripEconomics:
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    contract_multiplier: Decimal
    style: ExecutionStyle
    gross_pnl: Decimal
    leg1_fee: FeeDecomposition
    leg2_fee: FeeDecomposition
    total_fees: Decimal
    net_pnl: Decimal
    breakeven_points: Decimal
    fee_to_gross_ratio: Decimal | None


@dataclass(frozen=True, slots=True)
class AsymmetricRoundTripEconomics:
    entry_style: ExecutionStyle
    exit_style: ExecutionStyle
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    contract_multiplier: Decimal
    settlement_currency: str
    gross_pnl: Decimal
    leg1_fee: FeeDecomposition
    leg2_fee: FeeDecomposition
    funding_fee: Decimal
    borrow_fee: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    breakeven_points: Decimal
    fee_to_gross_ratio: Decimal | None

    @property
    def entry_fee(self) -> FeeDecomposition:
        return self.leg1_fee

    @property
    def exit_fee(self) -> FeeDecomposition:
        return self.leg2_fee


class TickRoundingPolicy(str, Enum):
    ROUND_HALF_UP = "ROUND_HALF_UP"
    CONSERVATIVE = "CONSERVATIVE"
    FLOOR = "FLOOR"
    CEILING = "CEILING"


@dataclass(frozen=True)
class InstrumentMetadata:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_quantity: Decimal
    contract_multiplier: Decimal
    settlement_currency: str = "USD"
    price_precision: int = 1
    qty_precision: int = 0
    min_notional: Decimal = Decimal("1.00")

    @classmethod
    def for_btcusd(cls) -> "InstrumentMetadata":
        """Authoritative Delta Exchange India BTCUSD (Product ID 84) metadata."""
        return cls(
            symbol="BTCUSD",
            tick_size=Decimal("0.10"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            contract_multiplier=Decimal("0.001"),
            settlement_currency="USD",
            price_precision=1,
            qty_precision=0,
            min_notional=Decimal("1.00"),
        )

    @property
    def quantity_step(self) -> Decimal:
        return self.step_size


def validate_instrument_constraints(
    price: Decimal | float | str | None,
    quantity: Decimal | float | str | None,
    tick_size: Decimal | float | str | None = None,
    quantity_step: Decimal | float | str = Decimal("1"),
    min_quantity: Decimal | float | str = Decimal("1"),
    multiplier: Decimal | float | str | None = None,
    meta: InstrumentMetadata | None = None,
    raise_exception: bool = True,
) -> tuple[bool, str | None]:
    """Validate price tick alignment and quantity step constraints against authoritative specifications.

    Fails closed on None, non-finite, zero, or negative inputs, and rejects conflicting metadata.
    """
    if price is None:
        err = "Price cannot be None"
        if raise_exception:
            raise ValueError(err)
        return False, err
    if quantity is None:
        err = "Quantity cannot be None"
        if raise_exception:
            raise ValueError(err)
        return False, err

    try:
        p = Decimal(str(price))
        q = Decimal(str(quantity))
    except Exception as e:
        err = f"Non-numeric price or quantity: {e}"
        if raise_exception:
            raise ValueError(err)
        return False, err

    if not p.is_finite() or p <= Decimal("0"):
        err = "Price must be positive and finite"
        if raise_exception:
            raise ValueError(err)
        return False, err
    if not q.is_finite() or q <= Decimal("0"):
        err = "Quantity must be positive and finite"
        if raise_exception:
            raise ValueError(err)
        return False, err

    if meta is not None:
        tick = meta.tick_size
        step = meta.step_size
        min_q = meta.min_quantity
        if tick_size is not None and Decimal(str(tick_size)) != tick:
            err = f"Metadata conflict: argument tick_size ({tick_size}) does not match meta.tick_size ({tick})"
            if raise_exception:
                raise ValueError(err)
            return False, err
        if multiplier is not None and Decimal(str(multiplier)) != meta.contract_multiplier:
            err = f"Metadata conflict: argument multiplier ({multiplier}) does not match meta.contract_multiplier ({meta.contract_multiplier})"
            if raise_exception:
                raise ValueError(err)
            return False, err
    else:
        tick = Decimal("0.10") if tick_size is None else Decimal(str(tick_size))
        step = Decimal(str(quantity_step))
        min_q = Decimal(str(min_quantity))

    if multiplier is not None:
        try:
            m_val = Decimal(str(multiplier))
            if not m_val.is_finite() or m_val <= Decimal("0"):
                err = f"Multiplier must be finite and strictly positive: {m_val}"
                if raise_exception:
                    raise ValueError(err)
                return False, err
        except Exception as e:
            err = f"Non-numeric multiplier: {e}"
            if raise_exception:
                raise ValueError(err)
            return False, err

    if not tick.is_finite() or tick <= Decimal("0"):
        err = f"Tick size must be finite and strictly positive: {tick}"
        if raise_exception:
            raise ValueError(err)
        return False, err
    if not step.is_finite() or step <= Decimal("0"):
        err = f"Quantity step must be finite and strictly positive: {step}"
        if raise_exception:
            raise ValueError(err)
        return False, err
    if not min_q.is_finite() or min_q <= Decimal("0"):
        err = f"Minimum quantity must be finite and strictly positive: {min_q}"
        if raise_exception:
            raise ValueError(err)
        return False, err

    err = None
    if q < min_q:
        err = f"Quantity {q} is below minimum {min_q}"
    elif (p % tick) != Decimal("0"):
        err = f"Price {p} does not align with tick size {tick}"
    elif (q % step) != Decimal("0"):
        err = f"Quantity {q} does not align with quantity step {step}"

    if err:
        if raise_exception:
            raise ValueError(err)
        return False, err
    return True, None


def normalize_price_to_tick(
    price: Decimal | float | str | None,
    tick_size: Decimal | float | str | None = None,
    policy: TickRoundingPolicy | str = TickRoundingPolicy.ROUND_HALF_UP,
    side: str | None = None,
    is_stop: bool = False,
    meta: InstrumentMetadata | None = None,
) -> Decimal:
    """Deterministically normalize a price to the instrument's tick grid.

    Fails closed on None, NaN, Infinity, non-positive price or tick size.
    Rejects conflicting metadata.
    Under CONSERVATIVE policy:
        * BUY Limit: floors down (never pays more than intended limit)
        * SELL Limit: ceilings up (never sells for less than intended limit)
        * LONG Stop Loss: ceilings up (closer to entry, never expands risk budget)
        * SHORT Stop Loss: floors down (closer to entry, never expands risk budget)
    """
    if price is None:
        raise ValueError("Price cannot be None")
    try:
        p = Decimal(str(price))
    except Exception as e:
        raise ValueError(f"Price is non-numeric: {price!r}") from e

    if not p.is_finite() or p <= Decimal("0"):
        raise ValueError(f"Price must be finite and positive, got {price!r}")

    if meta is not None:
        tick = meta.tick_size
        if tick_size is not None and Decimal(str(tick_size)) != tick:
            raise ValueError(f"Metadata conflict: argument tick_size ({tick_size}) does not match meta.tick_size ({tick})")
    else:
        tick = Decimal("0.10") if tick_size is None else Decimal(str(tick_size))

    if not tick.is_finite() or tick <= Decimal("0"):
        raise ValueError(f"Tick size must be finite and positive, got {tick!r}")

    if isinstance(policy, TickRoundingPolicy):
        pol = policy
    else:
        pol = TickRoundingPolicy(str(policy).upper())

    if pol == TickRoundingPolicy.ROUND_HALF_UP:
        rounding_mode = ROUND_HALF_UP
    elif pol == TickRoundingPolicy.FLOOR:
        rounding_mode = ROUND_FLOOR
    elif pol == TickRoundingPolicy.CEILING:
        rounding_mode = ROUND_CEILING
    elif pol == TickRoundingPolicy.CONSERVATIVE:
        side_norm = str(side).upper() if side else "BUY"
        if is_stop:
            # Long position stop is below entry -> ceiling up towards entry avoids risk expansion
            # Short position stop is above entry -> floor down towards entry avoids risk expansion
            if side_norm in ("BUY", "LONG"):
                rounding_mode = ROUND_CEILING
            else:
                rounding_mode = ROUND_FLOOR
        else:
            # Limit order: BUY floors down (cheaper); SELL ceilings up (richer)
            if side_norm in ("BUY", "LONG"):
                rounding_mode = ROUND_FLOOR
            else:
                rounding_mode = ROUND_CEILING
    else:
        rounding_mode = ROUND_HALF_UP

    ticks = (p / tick).quantize(Decimal("1"), rounding=rounding_mode)
    normalized = (ticks * tick).quantize(tick)
    return normalized


def calculate_leg_fee(
    notional: Decimal | float | str,
    base_rate: Decimal | float | str,
    gst_rate: Decimal | float | str = DEFAULT_GST_RATE,
    style: ExecutionStyle = ExecutionStyle.TAKER,
) -> FeeDecomposition:
    """Calculate single-leg fee decomposed into base fee and GST with Decimal precision."""
    n = Decimal(str(notional))
    br = Decimal(str(base_rate))
    gr = Decimal(str(gst_rate))

    if n <= Decimal("0"):
        raise ValueError("Notional must be strictly positive")

    base_fee = (n * br).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    if base_fee > Decimal("0"):
        gst = (base_fee * gr).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        total_fee = base_fee + gst
    elif base_fee < Decimal("0"):
        # Rebate tier: no GST owed on rebates paid to trader
        gst = Decimal("0.00000000")
        total_fee = base_fee
    else:
        gst = Decimal("0.00000000")
        total_fee = Decimal("0.00000000")

    effective_rate_bps = (total_fee / n * Decimal("10000")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return FeeDecomposition(
        style=style,
        notional=n,
        base_rate=br,
        base_fee=base_fee,
        gst_rate=gr,
        gst=gst,
        total_fee=total_fee,
        effective_rate_bps=effective_rate_bps,
    )


def _resolve_base_rate(style: ExecutionStyle, custom_base_rate: Decimal | float | str | None = None) -> Decimal:
    if custom_base_rate is not None:
        return Decimal(str(custom_base_rate))
    if style == ExecutionStyle.TAKER:
        return TAKER_BASE_RATE
    elif style == ExecutionStyle.MAKER:
        return MAKER_BASE_RATE
    elif style == ExecutionStyle.REBATE_VIP:
        return REBATE_BASE_RATE
    return TAKER_BASE_RATE


def calculate_round_trip(
    entry_price: Decimal | float | str,
    exit_price: Decimal | float | str,
    quantity: Decimal | float | str,
    contract_multiplier: Decimal | float | str,
    style: ExecutionStyle = ExecutionStyle.TAKER,
    custom_base_rate: Decimal | float | str | None = None,
) -> RoundTripEconomics:
    """Calculate round-trip execution economics with symmetric execution style."""
    ep = Decimal(str(entry_price))
    xp = Decimal(str(exit_price))
    qty = Decimal(str(quantity))
    cm = Decimal(str(contract_multiplier))

    if ep <= Decimal("0") or xp <= Decimal("0") or qty <= Decimal("0") or cm <= Decimal("0"):
        raise ValueError("Prices, quantity, and contract multiplier must be positive")

    leg1_notional = ep * cm * qty
    leg2_notional = xp * cm * qty

    br = _resolve_base_rate(style, custom_base_rate)

    leg1_fee = calculate_leg_fee(leg1_notional, br, DEFAULT_GST_RATE, style)
    leg2_fee = calculate_leg_fee(leg2_notional, br, DEFAULT_GST_RATE, style)
    total_fees = leg1_fee.total_fee + leg2_fee.total_fee

    gross_pnl = ((xp - ep) * cm * qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    net_pnl = gross_pnl - total_fees

    breakeven_points = (total_fees / (cm * qty)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    fee_to_gross = None
    if gross_pnl != Decimal("0"):
        fee_to_gross = (total_fees / abs(gross_pnl)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    return RoundTripEconomics(
        entry_price=ep,
        exit_price=xp,
        quantity=qty,
        contract_multiplier=cm,
        style=style,
        gross_pnl=gross_pnl,
        leg1_fee=leg1_fee,
        leg2_fee=leg2_fee,
        total_fees=total_fees,
        net_pnl=net_pnl,
        breakeven_points=breakeven_points,
        fee_to_gross_ratio=fee_to_gross,
    )


def calculate_asymmetric_round_trip(
    entry_price: Decimal | float | str,
    exit_price: Decimal | float | str,
    quantity: Decimal | float | str,
    contract_multiplier: Decimal | float | str,
    entry_style: ExecutionStyle = ExecutionStyle.MAKER,
    exit_style: ExecutionStyle = ExecutionStyle.TAKER,
    settlement_currency: str = "USD",
    funding_fee: Decimal | float | str = Decimal("0.0"),
    borrow_fee: Decimal | float | str = Decimal("0.0"),
    custom_entry_rate: Decimal | float | str | None = None,
    custom_exit_rate: Decimal | float | str | None = None,
    custom_maker_rate: Decimal | float | str | None = None,
) -> AsymmetricRoundTripEconomics:
    """Calculate round-trip economics with distinct entry/exit styles and funding."""
    ep = Decimal(str(entry_price))
    xp = Decimal(str(exit_price))
    qty = Decimal(str(quantity))
    cm = Decimal(str(contract_multiplier))
    fund = Decimal(str(funding_fee))
    borrow = Decimal(str(borrow_fee))

    if ep <= Decimal("0") or xp <= Decimal("0") or qty <= Decimal("0") or cm <= Decimal("0"):
        raise ValueError("Prices, quantity, and contract multiplier must be positive")

    leg1_notional = ep * cm * qty
    leg2_notional = xp * cm * qty

    resolved_entry_custom = custom_entry_rate if custom_entry_rate is not None else custom_maker_rate
    br_entry = _resolve_base_rate(entry_style, resolved_entry_custom)
    br_exit = _resolve_base_rate(exit_style, custom_exit_rate)

    leg1_fee = calculate_leg_fee(leg1_notional, br_entry, DEFAULT_GST_RATE, entry_style)
    leg2_fee = calculate_leg_fee(leg2_notional, br_exit, DEFAULT_GST_RATE, exit_style)
    
    total_fees = leg1_fee.total_fee + leg2_fee.total_fee + fund + borrow
    gross_pnl = ((xp - ep) * cm * qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    net_pnl = gross_pnl - total_fees

    breakeven_points = (total_fees / (cm * qty)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    fee_to_gross = None
    if gross_pnl != Decimal("0"):
        fee_to_gross = (total_fees / abs(gross_pnl)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    return AsymmetricRoundTripEconomics(
        entry_style=entry_style,
        exit_style=exit_style,
        entry_price=ep,
        exit_price=xp,
        quantity=qty,
        contract_multiplier=cm,
        settlement_currency=settlement_currency,
        gross_pnl=gross_pnl,
        leg1_fee=leg1_fee,
        leg2_fee=leg2_fee,
        funding_fee=fund,
        borrow_fee=borrow,
        total_fees=total_fees,
        net_pnl=net_pnl,
        breakeven_points=breakeven_points,
        fee_to_gross_ratio=fee_to_gross,
    )


def compare_styles(
    entry_price: Decimal | float | str,
    exit_price: Decimal | float | str,
    quantity: Decimal | float | str,
    contract_multiplier: Decimal | float | str,
) -> Dict[str, Any]:
    """Compare Taker, Maker, Asymmetric (Maker Entry / Taker Exit), and Rebate styles."""
    taker = calculate_round_trip(
        entry_price, exit_price, quantity, contract_multiplier, ExecutionStyle.TAKER
    )
    maker = calculate_round_trip(
        entry_price, exit_price, quantity, contract_multiplier, ExecutionStyle.MAKER
    )
    asym = calculate_asymmetric_round_trip(
        entry_price, exit_price, quantity, contract_multiplier,
        entry_style=ExecutionStyle.MAKER, exit_style=ExecutionStyle.TAKER,
    )
    rebate = calculate_round_trip(
        entry_price, exit_price, quantity, contract_multiplier, ExecutionStyle.REBATE_VIP
    )

    fee_savings_maker = taker.total_fees - maker.total_fees
    fee_savings_asym = taker.total_fees - asym.total_fees
    fee_savings_rebate = taker.total_fees - rebate.total_fees

    return {
        "gross_pnl": str(taker.gross_pnl),
        "taker": {
            "total_fees": str(taker.total_fees),
            "net_pnl": str(taker.net_pnl),
            "breakeven_points": str(taker.breakeven_points),
            "fee_to_gross_ratio": str(taker.fee_to_gross_ratio),
        },
        "maker": {
            "total_fees": str(maker.total_fees),
            "net_pnl": str(maker.net_pnl),
            "breakeven_points": str(maker.breakeven_points),
            "fee_to_gross_ratio": str(maker.fee_to_gross_ratio),
            "fee_savings_usd": str(fee_savings_maker),
            "fee_reduction_pct": str(
                (fee_savings_maker / taker.total_fees * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            ),
        },
        "asymmetric_maker_entry_taker_exit": {
            "total_fees": str(asym.total_fees),
            "net_pnl": str(asym.net_pnl),
            "breakeven_points": str(asym.breakeven_points),
            "fee_to_gross_ratio": str(asym.fee_to_gross_ratio),
            "fee_savings_usd": str(fee_savings_asym),
            "fee_reduction_pct": str(
                (fee_savings_asym / taker.total_fees * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            ),
        },
        "rebate_vip": {
            "total_fees": str(rebate.total_fees),
            "net_pnl": str(rebate.net_pnl),
            "breakeven_points": str(rebate.breakeven_points),
            "fee_to_gross_ratio": str(rebate.fee_to_gross_ratio),
            "fee_savings_usd": str(fee_savings_rebate),
        },
    }


@dataclass(frozen=True, slots=True)
class StopRiskAuditResult:
    valid: bool
    rejection_reason: str | None
    side: str
    entry_price: Decimal
    raw_stop_price: Decimal
    normalized_stop_price: Decimal
    raw_stop_distance: Decimal
    normalized_stop_distance: Decimal
    quantity: Decimal
    contract_multiplier: Decimal
    risk_budget: Decimal
    raw_gross_risk_usd: Decimal
    normalized_gross_risk_usd: Decimal
    estimated_stop_fees_usd: Decimal
    total_normalized_risk_usd: Decimal
    risk_expansion_usd: Decimal
    premature_trigger_risk_delta_pts: Decimal
    policy_applied: TickRoundingPolicy


def audit_and_recalculate_stop_risk(
    entry_price: Decimal | float | str,
    raw_stop_price: Decimal | float | str,
    quantity: Decimal | float | str,
    risk_budget: Decimal | float | str,
    side: str = "BUY",
    contract_multiplier: Decimal | float | str | None = None,
    policy: TickRoundingPolicy | str = TickRoundingPolicy.CONSERVATIVE,
    tick_size: Decimal | float | str | None = None,
    meta: InstrumentMetadata | None = None,
    estimated_entry_style: ExecutionStyle = ExecutionStyle.MAKER,
    estimated_exit_style: ExecutionStyle = ExecutionStyle.TAKER,
) -> StopRiskAuditResult:
    """Audit and recalculate risk using the normalized stop price.

    Guarantees:
      1. Normalizes the stop price onto the instrument's tick grid.
      2. Validates stop geometry: long stops must be below entry, short stops above entry.
      3. Recalculates gross loss and round-trip execution fees at the normalized stop price.
      4. Fails closed (valid=False) if the normalized total risk breaches the risk budget.
      5. Quantifies risk expansion and premature trigger displacement in points.
      6. Hardened contract-multiplier handling:
         - Uses authoritative metadata multiplier when supplied.
         - Accepts explicit multiplier when metadata is absent.
         - Fails closed on metadata conflicts if both are supplied and differ.
         - Fails closed if neither authoritative metadata nor explicit multiplier is provided.
         - Fails closed on zero, negative, non-finite, or non-numeric multipliers.
    """
    try:
        ep = Decimal(str(entry_price))
        raw_sp = Decimal(str(raw_stop_price))
        qty = Decimal(str(quantity))
        rb = Decimal(str(risk_budget))
    except Exception as e:
        return StopRiskAuditResult(
            valid=False,
            rejection_reason=f"Non-numeric risk input: {e}",
            side=str(side).upper(),
            entry_price=Decimal("0"),
            raw_stop_price=Decimal("0"),
            normalized_stop_price=Decimal("0"),
            raw_stop_distance=Decimal("0"),
            normalized_stop_distance=Decimal("0"),
            quantity=Decimal("0"),
            contract_multiplier=Decimal("0"),
            risk_budget=Decimal("0"),
            raw_gross_risk_usd=Decimal("0"),
            normalized_gross_risk_usd=Decimal("0"),
            estimated_stop_fees_usd=Decimal("0"),
            total_normalized_risk_usd=Decimal("0"),
            risk_expansion_usd=Decimal("0"),
            premature_trigger_risk_delta_pts=Decimal("0"),
            policy_applied=TickRoundingPolicy.CONSERVATIVE,
        )

    # Resolve contract multiplier unambiguously
    cm: Decimal
    if contract_multiplier is None and meta is None:
        return StopRiskAuditResult(
            valid=False,
            rejection_reason="Missing contract multiplier: neither authoritative metadata nor explicit multiplier provided",
            side=str(side).upper(),
            entry_price=ep if ep.is_finite() else Decimal("0"),
            raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
            normalized_stop_price=Decimal("0"),
            raw_stop_distance=Decimal("0"),
            normalized_stop_distance=Decimal("0"),
            quantity=qty if qty.is_finite() else Decimal("0"),
            contract_multiplier=Decimal("0"),
            risk_budget=rb if rb.is_finite() else Decimal("0"),
            raw_gross_risk_usd=Decimal("0"),
            normalized_gross_risk_usd=Decimal("0"),
            estimated_stop_fees_usd=Decimal("0"),
            total_normalized_risk_usd=Decimal("0"),
            risk_expansion_usd=Decimal("0"),
            premature_trigger_risk_delta_pts=Decimal("0"),
            policy_applied=TickRoundingPolicy.CONSERVATIVE,
        )
    elif contract_multiplier is None and meta is not None:
        if not hasattr(meta, "contract_multiplier") or not meta.contract_multiplier.is_finite() or meta.contract_multiplier <= Decimal("0"):
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid contract multiplier in metadata: {getattr(meta, 'contract_multiplier', None)}",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=Decimal("0"),
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
        cm = meta.contract_multiplier
    elif contract_multiplier is not None and meta is None:
        try:
            cm = Decimal(str(contract_multiplier))
        except Exception as e:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Non-numeric contract multiplier: {e}",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=Decimal("0"),
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
        if not cm.is_finite() or cm <= Decimal("0"):
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid contract multiplier: must be finite and strictly positive ({cm})",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=cm if cm.is_finite() else Decimal("0"),
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
    else:  # contract_multiplier is not None and meta is not None
        try:
            cm_explicit = Decimal(str(contract_multiplier))
        except Exception as e:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Non-numeric contract multiplier: {e}",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=Decimal("0"),
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
        if not cm_explicit.is_finite() or cm_explicit <= Decimal("0"):
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid contract multiplier: must be finite and strictly positive ({cm_explicit})",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=cm_explicit if cm_explicit.is_finite() else Decimal("0"),
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
        if not hasattr(meta, "contract_multiplier") or not meta.contract_multiplier.is_finite() or meta.contract_multiplier <= Decimal("0"):
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid contract multiplier in metadata: {getattr(meta, 'contract_multiplier', None)}",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=cm_explicit,
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
        if cm_explicit != meta.contract_multiplier:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Metadata conflict: explicit contract_multiplier ({cm_explicit}) does not match meta.contract_multiplier ({meta.contract_multiplier})",
                side=str(side).upper(),
                entry_price=ep if ep.is_finite() else Decimal("0"),
                raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
                normalized_stop_price=Decimal("0"),
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                contract_multiplier=cm_explicit,
                risk_budget=rb if rb.is_finite() else Decimal("0"),
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=TickRoundingPolicy.CONSERVATIVE,
            )
        cm = cm_explicit

    if not (ep.is_finite() and raw_sp.is_finite() and qty.is_finite() and rb.is_finite() and cm.is_finite()):
        return StopRiskAuditResult(
            valid=False,
            rejection_reason="Non-finite input encountered",
            side=str(side).upper(),
            entry_price=ep if ep.is_finite() else Decimal("0"),
            raw_stop_price=raw_sp if raw_sp.is_finite() else Decimal("0"),
            normalized_stop_price=Decimal("0"),
            raw_stop_distance=Decimal("0"),
            normalized_stop_distance=Decimal("0"),
            quantity=qty if qty.is_finite() else Decimal("0"),
            contract_multiplier=cm if cm.is_finite() else Decimal("0"),
            risk_budget=rb if rb.is_finite() else Decimal("0"),
            raw_gross_risk_usd=Decimal("0"),
            normalized_gross_risk_usd=Decimal("0"),
            estimated_stop_fees_usd=Decimal("0"),
            total_normalized_risk_usd=Decimal("0"),
            risk_expansion_usd=Decimal("0"),
            premature_trigger_risk_delta_pts=Decimal("0"),
            policy_applied=TickRoundingPolicy.CONSERVATIVE,
        )

    if ep <= Decimal("0") or raw_sp <= Decimal("0") or qty <= Decimal("0") or rb <= Decimal("0") or cm <= Decimal("0"):
        return StopRiskAuditResult(
            valid=False,
            rejection_reason="Inputs must be strictly positive",
            side=str(side).upper(),
            entry_price=ep,
            raw_stop_price=raw_sp,
            normalized_stop_price=Decimal("0"),
            raw_stop_distance=Decimal("0"),
            normalized_stop_distance=Decimal("0"),
            quantity=qty,
            contract_multiplier=cm,
            risk_budget=rb,
            raw_gross_risk_usd=Decimal("0"),
            normalized_gross_risk_usd=Decimal("0"),
            estimated_stop_fees_usd=Decimal("0"),
            total_normalized_risk_usd=Decimal("0"),
            risk_expansion_usd=Decimal("0"),
            premature_trigger_risk_delta_pts=Decimal("0"),
            policy_applied=TickRoundingPolicy.CONSERVATIVE,
        )

    side_norm = str(side).upper()
    if isinstance(policy, TickRoundingPolicy):
        pol = policy
    else:
        pol = TickRoundingPolicy(str(policy).upper())

    # 1. Normalize stop price
    try:
        norm_sp = normalize_price_to_tick(
            price=raw_sp,
            tick_size=tick_size,
            policy=pol,
            side=side_norm,
            is_stop=True,
            meta=meta,
        )
    except Exception as e:
        return StopRiskAuditResult(
            valid=False,
            rejection_reason=f"Stop price normalization error: {e}",
            side=side_norm,
            entry_price=ep,
            raw_stop_price=raw_sp,
            normalized_stop_price=Decimal("0"),
            raw_stop_distance=Decimal("0"),
            normalized_stop_distance=Decimal("0"),
            quantity=qty,
            contract_multiplier=cm,
            risk_budget=rb,
            raw_gross_risk_usd=Decimal("0"),
            normalized_gross_risk_usd=Decimal("0"),
            estimated_stop_fees_usd=Decimal("0"),
            total_normalized_risk_usd=Decimal("0"),
            risk_expansion_usd=Decimal("0"),
            premature_trigger_risk_delta_pts=Decimal("0"),
            policy_applied=pol,
        )

    # 2. Check stop geometry
    if side_norm in ("BUY", "LONG"):
        if raw_sp >= ep:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid long stop geometry: raw stop ({raw_sp}) >= entry ({ep})",
                side=side_norm,
                entry_price=ep,
                raw_stop_price=raw_sp,
                normalized_stop_price=norm_sp,
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty,
                contract_multiplier=cm,
                risk_budget=rb,
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=pol,
            )
        if norm_sp >= ep:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid long stop geometry: normalized stop ({norm_sp}) >= entry ({ep})",
                side=side_norm,
                entry_price=ep,
                raw_stop_price=raw_sp,
                normalized_stop_price=norm_sp,
                raw_stop_distance=abs(ep - raw_sp),
                normalized_stop_distance=Decimal("0"),
                quantity=qty,
                contract_multiplier=cm,
                risk_budget=rb,
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=pol,
            )
        raw_dist = ep - raw_sp
        norm_dist = ep - norm_sp
        premature_delta = norm_sp - raw_sp
    else:
        if raw_sp <= ep:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid short stop geometry: raw stop ({raw_sp}) <= entry ({ep})",
                side=side_norm,
                entry_price=ep,
                raw_stop_price=raw_sp,
                normalized_stop_price=norm_sp,
                raw_stop_distance=Decimal("0"),
                normalized_stop_distance=Decimal("0"),
                quantity=qty,
                contract_multiplier=cm,
                risk_budget=rb,
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=pol,
            )
        if norm_sp <= ep:
            return StopRiskAuditResult(
                valid=False,
                rejection_reason=f"Invalid short stop geometry: normalized stop ({norm_sp}) <= entry ({ep})",
                side=side_norm,
                entry_price=ep,
                raw_stop_price=raw_sp,
                normalized_stop_price=norm_sp,
                raw_stop_distance=abs(raw_sp - ep),
                normalized_stop_distance=Decimal("0"),
                quantity=qty,
                contract_multiplier=cm,
                risk_budget=rb,
                raw_gross_risk_usd=Decimal("0"),
                normalized_gross_risk_usd=Decimal("0"),
                estimated_stop_fees_usd=Decimal("0"),
                total_normalized_risk_usd=Decimal("0"),
                risk_expansion_usd=Decimal("0"),
                premature_trigger_risk_delta_pts=Decimal("0"),
                policy_applied=pol,
            )
        raw_dist = raw_sp - ep
        norm_dist = norm_sp - ep
        premature_delta = raw_sp - norm_sp

    raw_gross_risk = (raw_dist * cm * qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    norm_gross_risk = (norm_dist * cm * qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    risk_expansion = norm_gross_risk - raw_gross_risk

    # 3. Calculate stop fees
    entry_notional = ep * cm * qty
    exit_notional = norm_sp * cm * qty
    br_entry = _resolve_base_rate(estimated_entry_style)
    br_exit = _resolve_base_rate(estimated_exit_style)
    f_entry = calculate_leg_fee(entry_notional, br_entry, DEFAULT_GST_RATE, estimated_entry_style).total_fee
    f_exit = calculate_leg_fee(exit_notional, br_exit, DEFAULT_GST_RATE, estimated_exit_style).total_fee
    total_fees = f_entry + f_exit

    total_norm_risk = norm_gross_risk + total_fees

    # 4. Check risk budget
    if total_norm_risk > rb:
        return StopRiskAuditResult(
            valid=False,
            rejection_reason=f"Normalized stop risk ({total_norm_risk:.4f} USD) exceeds risk budget ({rb:.4f} USD)",
            side=side_norm,
            entry_price=ep,
            raw_stop_price=raw_sp,
            normalized_stop_price=norm_sp,
            raw_stop_distance=raw_dist,
            normalized_stop_distance=norm_dist,
            quantity=qty,
            contract_multiplier=cm,
            risk_budget=rb,
            raw_gross_risk_usd=raw_gross_risk,
            normalized_gross_risk_usd=norm_gross_risk,
            estimated_stop_fees_usd=total_fees,
            total_normalized_risk_usd=total_norm_risk,
            risk_expansion_usd=risk_expansion,
            premature_trigger_risk_delta_pts=premature_delta,
            policy_applied=pol,
        )

    return StopRiskAuditResult(
        valid=True,
        rejection_reason=None,
        side=side_norm,
        entry_price=ep,
        raw_stop_price=raw_sp,
        normalized_stop_price=norm_sp,
        raw_stop_distance=raw_dist,
        normalized_stop_distance=norm_dist,
        quantity=qty,
        contract_multiplier=cm,
        risk_budget=rb,
        raw_gross_risk_usd=raw_gross_risk,
        normalized_gross_risk_usd=norm_gross_risk,
        estimated_stop_fees_usd=total_fees,
        total_normalized_risk_usd=total_norm_risk,
        risk_expansion_usd=risk_expansion,
        premature_trigger_risk_delta_pts=premature_delta,
        policy_applied=pol,
    )
