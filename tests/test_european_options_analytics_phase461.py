"""Phase 461: European option valuation, Greeks, and implied volatility."""
import math

import pytest

from core.options.black_scholes import (
    calculate_option_valuation,
    implied_volatility,
    price_european_option,
)


def _price(spot=100.0, strike=100.0, expiry=1.0, volatility=0.2,
           right="call", rate=0.05, dividend=0.0):
    return price_european_option(
        spot=spot, strike=strike, time_to_expiry_years=expiry,
        volatility=volatility, option_right=right,
        risk_free_rate=rate, dividend_yield=dividend,
    )


def test_known_black_scholes_reference_values():
    assert _price(right="call") == pytest.approx(10.4505835722, abs=1e-8)
    assert _price(right="put") == pytest.approx(5.5735260223, abs=1e-8)


def test_put_call_parity_with_dividend_yield():
    call = _price(spot=125, strike=120, expiry=0.75, volatility=0.31,
                  right="call", rate=0.06, dividend=0.02)
    put = _price(spot=125, strike=120, expiry=0.75, volatility=0.31,
                 right="put", rate=0.06, dividend=0.02)
    expected = 125 * math.exp(-0.02 * 0.75) - 120 * math.exp(-0.06 * 0.75)
    assert call - put == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize("right", ["call", "put"])
def test_greeks_match_finite_difference_checks(right):
    spot, strike, expiry, volatility, rate, dividend = 103.0, 100.0, 0.8, 0.27, 0.04, 0.01
    value = calculate_option_valuation(
        spot=spot, strike=strike, time_to_expiry_years=expiry,
        volatility=volatility, option_right=right,
        risk_free_rate=rate, dividend_yield=dividend,
    )
    h_spot, h_vol, h_time, h_rate = 1e-3, 1e-4, 1e-4, 1e-4
    p_up = _price(spot=spot+h_spot, strike=strike, expiry=expiry,
                  volatility=volatility, right=right, rate=rate, dividend=dividend)
    p_down = _price(spot=spot-h_spot, strike=strike, expiry=expiry,
                    volatility=volatility, right=right, rate=rate, dividend=dividend)
    delta = (p_up - p_down) / (2*h_spot)
    gamma = (p_up - 2*value.fair_value + p_down) / (h_spot*h_spot)
    vega = (
        _price(spot=spot, strike=strike, expiry=expiry, volatility=volatility+h_vol,
               right=right, rate=rate, dividend=dividend)
        - _price(spot=spot, strike=strike, expiry=expiry, volatility=volatility-h_vol,
                 right=right, rate=rate, dividend=dividend)
    ) / (2*h_vol)
    theta = (
        _price(spot=spot, strike=strike, expiry=expiry-h_time, volatility=volatility,
               right=right, rate=rate, dividend=dividend)
        - _price(spot=spot, strike=strike, expiry=expiry+h_time, volatility=volatility,
                 right=right, rate=rate, dividend=dividend)
    ) / (2*h_time)
    rho = (
        _price(spot=spot, strike=strike, expiry=expiry, volatility=volatility,
               right=right, rate=rate+h_rate, dividend=dividend)
        - _price(spot=spot, strike=strike, expiry=expiry, volatility=volatility,
                 right=right, rate=rate-h_rate, dividend=dividend)
    ) / (2*h_rate)
    assert value.delta == pytest.approx(delta, abs=2e-6)
    assert value.gamma == pytest.approx(gamma, abs=2e-5)
    assert value.vega == pytest.approx(vega, abs=2e-5)
    assert value.theta_per_year == pytest.approx(theta, abs=2e-5)
    assert value.rho == pytest.approx(rho, abs=2e-5)
    assert value.theta_per_day == pytest.approx(value.theta_per_year / 365)


@pytest.mark.parametrize("right", ["call", "put"])
def test_implied_volatility_round_trip(right):
    market = _price(
        spot=22500, strike=22600, expiry=0.18, volatility=0.34,
        right=right, rate=0.065, dividend=0.0,
    )
    recovered = implied_volatility(
        market_price=market, spot=22500, strike=22600,
        time_to_expiry_years=0.18, option_right=right,
        risk_free_rate=0.065, max_volatility=3.0,
    )
    assert recovered == pytest.approx(0.34, abs=1e-6)


def test_expiry_returns_intrinsic_and_boundary_delta():
    call = calculate_option_valuation(
        spot=110, strike=100, time_to_expiry_years=0,
        volatility=0, option_right="call",
    )
    put = calculate_option_valuation(
        spot=90, strike=100, time_to_expiry_years=0,
        volatility=0, option_right="put",
    )
    atm = calculate_option_valuation(
        spot=100, strike=100, time_to_expiry_years=0,
        volatility=0, option_right="call",
    )
    assert (call.fair_value, call.delta, call.time_value) == (10, 1, 0)
    assert (put.fair_value, put.delta, put.time_value) == (10, -1, 0)
    assert atm.delta == 0.5
    assert call.gamma == call.vega == call.theta_per_year == call.rho == 0


def test_implied_volatility_rejects_prices_outside_no_arbitrage_bounds():
    with pytest.raises(ValueError, match="no-arbitrage bounds"):
        implied_volatility(
            market_price=150, spot=100, strike=100,
            time_to_expiry_years=1, option_right="call",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"spot": 0}, {"strike": -1}, {"time_to_expiry_years": -0.1},
        {"volatility": 0.0}, {"volatility": float("nan")},
        {"risk_free_rate": float("inf")}, {"dividend_yield": float("nan")},
    ],
)
def test_invalid_model_inputs_are_rejected(kwargs):
    values = dict(
        spot=100, strike=100, time_to_expiry_years=1,
        volatility=0.2, option_right="call",
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        calculate_option_valuation(**values)


def test_unknown_option_right_is_rejected():
    with pytest.raises(ValueError, match="option_right"):
        calculate_option_valuation(
            spot=100, strike=100, time_to_expiry_years=1,
            volatility=0.2, option_right="binary",
        )


def test_volatility_increases_option_value_for_both_rights():
    for right in ("call", "put"):
        low = _price(volatility=0.1, right=right)
        high = _price(volatility=0.5, right=right)
        assert high > low
