"""Research-only scaling of per-unit option Greeks to signed contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math

from core.options.black_scholes import OptionValuation


@dataclass(frozen=True, slots=True)
class OptionPositionExposure:
    signed_contracts: int
    lot_size: int
    contract_multiplier: float
    units: float
    model_market_value: float
    delta_units: float
    delta_notional: float
    gamma_units: float
    gamma_pnl_for_one_percent_spot_move: float
    vega_per_volatility_point: float
    theta_per_day: float
    rho_per_one_percent_rate: float


def _positive(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("%s must be finite and positive" % name)
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("%s must be finite and positive" % name) from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("%s must be finite and positive" % name)
    return parsed


def scale_option_position(
    valuation: OptionValuation,
    *,
    spot: float,
    signed_contracts: int,
    lot_size: int,
    contract_multiplier: float = 1.0,
) -> OptionPositionExposure:
    """Scale a per-unit valuation into signed lot/contract risk exposures.

    Positive contracts represent long options; negative contracts represent
    short options. This is an exposure calculation, not a margin or max-loss
    model. The contract multiplier and lot size must come from verified
    instrument metadata, not guessed defaults.
    """
    if not isinstance(valuation, OptionValuation):
        raise TypeError("valuation must be an OptionValuation")
    reference_spot = _positive("spot", spot)
    multiplier = _positive("contract_multiplier", contract_multiplier)
    if isinstance(signed_contracts, bool) or not isinstance(signed_contracts, int):
        raise ValueError("signed_contracts must be an integer")
    if isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size <= 0:
        raise ValueError("lot_size must be a positive integer")

    units = float(signed_contracts * lot_size) * multiplier
    delta_units = valuation.delta * units
    gamma_units = valuation.gamma * units
    one_percent_move = reference_spot * 0.01
    return OptionPositionExposure(
        signed_contracts=signed_contracts,
        lot_size=lot_size,
        contract_multiplier=multiplier,
        units=units,
        model_market_value=valuation.fair_value * units,
        delta_units=delta_units,
        delta_notional=delta_units * reference_spot,
        gamma_units=gamma_units,
        gamma_pnl_for_one_percent_spot_move=(
            0.5 * gamma_units * one_percent_move * one_percent_move
        ),
        vega_per_volatility_point=valuation.vega * units * 0.01,
        theta_per_day=valuation.theta_per_day * units,
        rho_per_one_percent_rate=valuation.rho * units * 0.01,
    )
