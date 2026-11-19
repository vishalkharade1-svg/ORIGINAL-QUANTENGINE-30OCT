"""European Black-Scholes option valuation and implied volatility.

Research analytics only. Values are per underlying unit and do not model
exchange fees, contract multipliers, margin, early exercise, discrete
dividends, volatility smiles, or venue-specific settlement rules.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from core.exchanges.instrument_spec import OptionRight


@dataclass(frozen=True, slots=True)
class OptionValuation:
    model: str
    fair_value: float
    intrinsic_value: float
    time_value: float
    delta: float
    gamma: float
    vega: float
    theta_per_year: float
    theta_per_day: float
    rho: float


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


def _right(value: OptionRight | str) -> OptionRight:
    try:
        return value if isinstance(value, OptionRight) else OptionRight(str(value).lower())
    except ValueError:
        raise ValueError("option_right must be call or put") from None


def _inputs(
    spot: object,
    strike: object,
    time_to_expiry_years: object,
    volatility: object,
    risk_free_rate: object,
    dividend_yield: object,
) -> tuple[float, float, float, float, float, float]:
    s = _finite("spot", spot)
    k = _finite("strike", strike)
    t = _finite("time_to_expiry_years", time_to_expiry_years)
    sigma = _finite("volatility", volatility)
    rate = _finite("risk_free_rate", risk_free_rate)
    dividend = _finite("dividend_yield", dividend_yield)
    if s <= 0 or k <= 0:
        raise ValueError("spot and strike must be positive")
    if t < 0:
        raise ValueError("time_to_expiry_years must be non-negative")
    if t > 0 and sigma <= 0:
        raise ValueError("volatility must be positive before expiry")
    if sigma < 0:
        raise ValueError("volatility must be non-negative")
    return s, k, t, sigma, rate, dividend


def _cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _intrinsic(spot: float, strike: float, right: OptionRight) -> float:
    if right is OptionRight.CALL:
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def calculate_option_valuation(
    *,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    option_right: OptionRight | str,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> OptionValuation:
    """Return Black-Scholes fair value and first/second-order Greeks.

    Vega and rho are derivatives per 1.0 absolute change in volatility/rate.
    Theta is calendar-time decay per year; theta_per_day uses ACT/365.
    """
    right = _right(option_right)
    s, k, t, sigma, rate, dividend = _inputs(
        spot, strike, time_to_expiry_years, volatility,
        risk_free_rate, dividend_yield,
    )
    intrinsic = _intrinsic(s, k, right)
    if t == 0:
        if s == k:
            delta = 0.5 if right is OptionRight.CALL else -0.5
        elif right is OptionRight.CALL:
            delta = 1.0 if s > k else 0.0
        else:
            delta = -1.0 if s < k else 0.0
        return OptionValuation(
            model="BLACK_SCHOLES_EUROPEAN",
            fair_value=intrinsic,
            intrinsic_value=intrinsic,
            time_value=0.0,
            delta=delta,
            gamma=0.0,
            vega=0.0,
            theta_per_year=0.0,
            theta_per_day=0.0,
            rho=0.0,
        )

    root_t = math.sqrt(t)
    sigma_root_t = sigma * root_t
    try:
        discount_spot = math.exp(-dividend * t)
        discount_strike = math.exp(-rate * t)
        d1 = (
            math.log(s / k) + (rate - dividend + 0.5 * sigma * sigma) * t
        ) / sigma_root_t
        d2 = d1 - sigma_root_t
    except (OverflowError, ZeroDivisionError):
        raise ValueError("inputs are outside the stable Black-Scholes domain") from None

    if right is OptionRight.CALL:
        fair_value = s * discount_spot * _cdf(d1) - k * discount_strike * _cdf(d2)
        delta = discount_spot * _cdf(d1)
        theta = (
            -s * discount_spot * _pdf(d1) * sigma / (2.0 * root_t)
            - rate * k * discount_strike * _cdf(d2)
            + dividend * s * discount_spot * _cdf(d1)
        )
        rho = k * t * discount_strike * _cdf(d2)
    else:
        fair_value = k * discount_strike * _cdf(-d2) - s * discount_spot * _cdf(-d1)
        delta = discount_spot * (_cdf(d1) - 1.0)
        theta = (
            -s * discount_spot * _pdf(d1) * sigma / (2.0 * root_t)
            + rate * k * discount_strike * _cdf(-d2)
            - dividend * s * discount_spot * _cdf(-d1)
        )
        rho = -k * t * discount_strike * _cdf(-d2)

    gamma = discount_spot * _pdf(d1) / (s * sigma_root_t)
    vega = s * discount_spot * _pdf(d1) * root_t
    if not all(math.isfinite(x) for x in (fair_value, delta, gamma, vega, theta, rho)):
        raise ValueError("valuation is outside the finite numeric domain")
    fair_value = max(0.0, fair_value)
    return OptionValuation(
        model="BLACK_SCHOLES_EUROPEAN",
        fair_value=fair_value,
        intrinsic_value=intrinsic,
        time_value=max(0.0, fair_value - intrinsic),
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta_per_year=theta,
        theta_per_day=theta / 365.0,
        rho=rho,
    )


def price_european_option(
    *,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    option_right: OptionRight | str,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """Return per-unit European option fair value."""
    return calculate_option_valuation(
        spot=spot,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        volatility=volatility,
        option_right=option_right,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    ).fair_value


def implied_volatility(
    *,
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    option_right: OptionRight | str,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
    tolerance: float = 1e-8,
    max_iterations: int = 120,
    max_volatility: float = 5.0,
) -> float:
    """Solve implied volatility by bounded bisection.

    Prices at/outside theoretical no-arbitrage bounds are rejected because a
    finite implied volatility is not identifiable there.
    """
    right = _right(option_right)
    s = _finite("spot", spot)
    k = _finite("strike", strike)
    t = _finite("time_to_expiry_years", time_to_expiry_years)
    rate = _finite("risk_free_rate", risk_free_rate)
    dividend = _finite("dividend_yield", dividend_yield)
    target = _finite("market_price", market_price)
    tol = _finite("tolerance", tolerance)
    upper = _finite("max_volatility", max_volatility)
    if s <= 0 or k <= 0 or t <= 0:
        raise ValueError("spot, strike, and time to expiry must be positive")
    if target < 0:
        raise ValueError("market_price must be non-negative")
    if tol <= 0 or upper <= 0:
        raise ValueError("tolerance and max_volatility must be positive")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")

    discount_spot = math.exp(-dividend * t)
    discount_strike = math.exp(-rate * t)
    if right is OptionRight.CALL:
        lower_bound = max(s * discount_spot - k * discount_strike, 0.0)
        upper_bound = s * discount_spot
    else:
        lower_bound = max(k * discount_strike - s * discount_spot, 0.0)
        upper_bound = k * discount_strike
    if target <= lower_bound or target >= upper_bound:
        raise ValueError("market_price must lie strictly inside no-arbitrage bounds")

    low, high = 1e-8, upper
    high_price = price_european_option(
        spot=s, strike=k, time_to_expiry_years=t, volatility=high,
        option_right=right, risk_free_rate=rate, dividend_yield=dividend,
    )
    if high_price < target:
        raise ValueError("market_price exceeds configured max_volatility search range")

    for _ in range(max_iterations):
        middle = (low + high) / 2.0
        model_price = price_european_option(
            spot=s, strike=k, time_to_expiry_years=t, volatility=middle,
            option_right=right, risk_free_rate=rate, dividend_yield=dividend,
        )
        if abs(model_price - target) <= tol:
            return middle
        if model_price < target:
            low = middle
        else:
            high = middle
    raise ValueError("implied volatility solver did not converge")
