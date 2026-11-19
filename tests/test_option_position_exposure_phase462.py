"""Phase 462: scale option Greeks to signed lots and contract multipliers."""
import pytest

from core.options import calculate_option_valuation, scale_option_position


def _valuation():
    return calculate_option_valuation(
        spot=22500, strike=22600, time_to_expiry_years=0.18,
        volatility=0.34, option_right="call", risk_free_rate=0.065,
    )


def test_long_and_short_option_positions_have_opposite_signed_exposures():
    long = scale_option_position(
        _valuation(), spot=22500, signed_contracts=2, lot_size=25,
    )
    short = scale_option_position(
        _valuation(), spot=22500, signed_contracts=-2, lot_size=25,
    )
    assert long.units == 50
    assert short.units == -50
    for field in (
        "model_market_value", "delta_units", "delta_notional",
        "gamma_units", "gamma_pnl_for_one_percent_spot_move",
        "vega_per_volatility_point", "theta_per_day",
        "rho_per_one_percent_rate",
    ):
        assert getattr(short, field) == pytest.approx(-getattr(long, field))


def test_lot_size_and_contract_multiplier_scale_exposure_linearly():
    valuation = _valuation()
    one_lot = scale_option_position(
        valuation, spot=22500, signed_contracts=1, lot_size=25,
    )
    two_lots = scale_option_position(
        valuation, spot=22500, signed_contracts=2, lot_size=25,
    )
    multiplied = scale_option_position(
        valuation, spot=22500, signed_contracts=1,
        lot_size=25, contract_multiplier=2,
    )
    assert two_lots.delta_notional == pytest.approx(2 * one_lot.delta_notional)
    assert multiplied.model_market_value == pytest.approx(2 * one_lot.model_market_value)


def test_zero_contract_position_has_zero_exposure():
    result = scale_option_position(
        _valuation(), spot=22500, signed_contracts=0, lot_size=25,
    )
    assert result.units == 0
    assert result.model_market_value == 0
    assert result.delta_notional == 0
    assert result.theta_per_day == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"spot": 0}, {"lot_size": 0}, {"lot_size": True},
        {"signed_contracts": 1.5}, {"signed_contracts": True},
        {"contract_multiplier": 0}, {"contract_multiplier": float("nan")},
    ],
)
def test_invalid_contract_exposure_inputs_are_rejected(kwargs):
    values = dict(
        spot=22500, signed_contracts=1, lot_size=25,
        contract_multiplier=1.0,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        scale_option_position(_valuation(), **values)
