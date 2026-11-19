"""Phase 464: exact option model repricing under bounded risk scenarios."""
import pytest
from core.options import evaluate_option_scenario

def _scenario(**changes):
    values = dict(
        spot=22500, strike=22600, time_to_expiry_years=0.18,
        volatility=0.34, option_right="call",
        signed_contracts=1, lot_size=25, risk_free_rate=0.065,
    )
    values.update(changes)
    return evaluate_option_scenario(**values)

def test_long_call_scenario_pnl_increases_with_spot_and_volatility():
    base = _scenario()
    up = _scenario(spot_change_pct=0.05)
    vol_up = _scenario(volatility_change=0.05)
    assert up.pnl > base.pnl
    assert vol_up.pnl > base.pnl

def test_short_position_scenario_pnl_is_exactly_opposite():
    long = _scenario(spot_change_pct=-0.07, volatility_change=0.08, days_elapsed=5)
    short = _scenario(
        spot_change_pct=-0.07, volatility_change=0.08,
        days_elapsed=5, signed_contracts=-1,
    )
    assert short.pnl == pytest.approx(-long.pnl)
    assert short.base_model_value == pytest.approx(-long.base_model_value)

def test_put_position_benefits_from_downside_spot_scenario():
    down = _scenario(
        option_right="put", spot_change_pct=-0.08,
        strike=22500, volatility=0.25,
    )
    up = _scenario(
        option_right="put", spot_change_pct=0.08,
        strike=22500, volatility=0.25,
    )
    assert down.pnl > up.pnl

def test_time_decay_reaches_intrinsic_at_expiry_without_going_negative():
    result = _scenario(
        spot=23000, strike=22500, time_to_expiry_years=30/365,
        volatility=0.3, days_elapsed=30,
    )
    assert result.remaining_time_years == 0
    assert result.scenario_valuation.fair_value == 500
    assert result.scenario_valuation.time_value == 0

@pytest.mark.parametrize(
    "changes, message",
    [
        ({"spot_change_pct": -1.0}, "greater than -1"),
        ({"volatility_change": -0.5}, "scenario volatility"),
        ({"days_elapsed": 100}, "exceeds time to expiry"),
        ({"days_elapsed": -1}, "non-negative"),
        ({"spot": 0}, "spot must be positive"),
    ],
)
def test_invalid_scenario_shocks_are_rejected(changes, message):
    with pytest.raises(ValueError, match=message):
        _scenario(**changes)

def test_scenario_preserves_contract_lot_and_multiplier_scaling():
    one = _scenario()
    two = _scenario(signed_contracts=2)
    multiplied = _scenario(contract_multiplier=2)
    assert two.pnl == pytest.approx(2 * one.pnl)
    assert multiplied.pnl == pytest.approx(2 * one.pnl)
