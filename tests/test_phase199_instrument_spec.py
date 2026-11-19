from decimal import Decimal
import pytest

from core.exchanges.instrument_spec import InstrumentSpec, OptionRight


def test_normalizes_numeric_metadata_to_decimal():
    spec = InstrumentSpec("BTC-PERP", "crypto", "perpetual", "0.5", "1", 1)
    assert spec.tick_size == Decimal("0.5")
    assert spec.quantity_step == Decimal("1")


@pytest.mark.parametrize("field,value", [
    ("tick_size", 0), ("tick_size", -0.01),
    ("quantity_step", float("inf")), ("contract_multiplier", "NaN"),
])
def test_rejects_nonpositive_or_nonfinite_quantities(field, value):
    kwargs = dict(symbol="X", family="crypto", instrument_type="spot",
                  tick_size=0.01, quantity_step=1)
    kwargs[field] = value
    with pytest.raises(ValueError):
        InstrumentSpec(**kwargs)


def test_valid_nse_index_option_requires_contract_identity():
    spec = InstrumentSpec("NIFTY-2026-11-03-25000-CE", "nse_index", "option",
                          0.05, 1, currency="INR", underlying="NIFTY",
                          option_right="call", strike=25000,
                          expiry="2026-11-03", lot_size=65)
    assert spec.option_right is OptionRight.CALL
    assert spec.strike == Decimal("25000")
    assert spec.lot_size == 65


@pytest.mark.parametrize("kwargs", [
    {"underlying": "NIFTY", "option_right": "call", "strike": 25000,
     "expiry": "2026-11-03"},
    {"underlying": "NIFTY", "option_right": "straddle", "strike": 25000,
     "expiry": "2026-11-03", "lot_size": 65},
    {"underlying": "NIFTY", "option_right": "put", "strike": 0,
     "expiry": "2026-11-03", "lot_size": 65},
    {"underlying": "NIFTY", "option_right": "put", "strike": 25000,
     "expiry": "2026-02-30", "lot_size": 65},
    {"underlying": "NIFTY", "option_right": "put", "strike": 25000,
     "expiry": "2026-11-03", "lot_size": 0},
])
def test_rejects_incomplete_or_invalid_option_metadata(kwargs):
    with pytest.raises(ValueError):
        InstrumentSpec("NIFTY-OPTION", "nse_index", "option", 0.05, 1, **kwargs)


def test_forex_pair_requires_normalized_three_letter_codes():
    good = InstrumentSpec("EUR/USD", "forex", "fx_spot", 0.0001, 1)
    assert good.symbol == "EUR/USD"
    with pytest.raises(ValueError, match="BASE/QUOTE"):
        InstrumentSpec("EURUSD", "forex", "fx_spot", 0.0001, 1)
