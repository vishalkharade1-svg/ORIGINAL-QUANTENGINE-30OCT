"""Deterministic single-position option scenario repricing."""
from __future__ import annotations
from dataclasses import dataclass
import math
from core.options.black_scholes import OptionValuation, calculate_option_valuation
from core.options.position import scale_option_position

@dataclass(frozen=True, slots=True)
class OptionScenarioResult:
    base_valuation: OptionValuation
    scenario_valuation: OptionValuation
    signed_units: float
    base_model_value: float
    scenario_model_value: float
    pnl: float
    scenario_spot: float
    scenario_volatility: float
    remaining_time_years: float
    spot_change_pct: float
    volatility_change: float
    days_elapsed: float

def _finite(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("%s must be finite" % name)
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("%s must be finite" % name) from None
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % name)
    return result

def evaluate_option_scenario(
    *,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    option_right: str,
    signed_contracts: int,
    lot_size: int,
    spot_change_pct: float = 0.0,
    volatility_change: float = 0.0,
    days_elapsed: float = 0.0,
    contract_multiplier: float = 1.0,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> OptionScenarioResult:
    """Reprice one signed option position under spot/vol/time shocks.

    spot_change_pct=-0.05 means a 5% spot fall. volatility_change=0.05
    means +5 volatility points. Time decays on ACT/365. Model P&L is not
    margin, liquidation, or maximum-loss evidence.
    """
    s = _finite("spot", spot)
    t = _finite("time_to_expiry_years", time_to_expiry_years)
    sigma = _finite("volatility", volatility)
    spot_shock = _finite("spot_change_pct", spot_change_pct)
    vol_shock = _finite("volatility_change", volatility_change)
    elapsed = _finite("days_elapsed", days_elapsed)
    if s <= 0:
        raise ValueError("spot must be positive")
    if t < 0:
        raise ValueError("time_to_expiry_years must be non-negative")
    if sigma < 0:
        raise ValueError("volatility must be non-negative")
    if spot_shock <= -1.0:
        raise ValueError("spot_change_pct must be greater than -1")
    if elapsed < 0:
        raise ValueError("days_elapsed must be non-negative")
    remaining = t - elapsed / 365.0
    if remaining < -1e-12:
        raise ValueError("days_elapsed exceeds time to expiry")
    remaining = max(0.0, remaining)
    shocked_spot = s * (1.0 + spot_shock)
    shocked_vol = sigma + vol_shock
    if shocked_vol < 0 or (remaining > 0 and shocked_vol == 0):
        raise ValueError("scenario volatility must be positive before expiry")
    base = calculate_option_valuation(
        spot=s, strike=strike, time_to_expiry_years=t,
        volatility=sigma, option_right=option_right,
        risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
    )
    stressed = calculate_option_valuation(
        spot=shocked_spot, strike=strike, time_to_expiry_years=remaining,
        volatility=shocked_vol, option_right=option_right,
        risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
    )
    exposure = scale_option_position(
        base, spot=s, signed_contracts=signed_contracts,
        lot_size=lot_size, contract_multiplier=contract_multiplier,
    )
    scenario_value = stressed.fair_value * exposure.units
    pnl = scenario_value - exposure.model_market_value
    if not math.isfinite(scenario_value) or not math.isfinite(pnl):
        raise ValueError("scenario result is outside the finite numeric domain")
    return OptionScenarioResult(
        base_valuation=base,
        scenario_valuation=stressed,
        signed_units=exposure.units,
        base_model_value=exposure.model_market_value,
        scenario_model_value=scenario_value,
        pnl=pnl,
        scenario_spot=shocked_spot,
        scenario_volatility=shocked_vol,
        remaining_time_years=remaining,
        spot_change_pct=spot_shock,
        volatility_change=vol_shock,
        days_elapsed=elapsed,
    )
