"""Phase 469: finite positive option contract precision facts."""
from datetime import datetime, timezone
import pytest
from core.options import build_option_chain
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION

AS_OF = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
EXPIRY = int(datetime(2026, 12, 31, 8, 0, tzinfo=timezone.utc).timestamp())


def _call(**changes):
    values = dict(
        instrument_id=f"nse-nifty-{EXPIRY}-call",
        symbol="NIFTY26DEC22500CE", exchange="NSE",
        product_type=PRODUCT_CALL_OPTION, underlying_asset="NIFTY",
        quote_asset="INR", expiry_time=EXPIRY, strike_price=22500.0,
        option_type="call", tick_size=0.05, quantity_step=1.0,
        minimum_quantity=25.0, trading_enabled=True, lot_size=25,
        contract_multiplier=1.0,
    )
    values.update(changes)
    return Instrument(**values)


@pytest.mark.parametrize("changes", [
    {"tick_size": 0},
    {"tick_size": float("inf")},
    {"quantity_step": 0},
    {"quantity_step": float("nan")},
    {"minimum_quantity": 0},
    {"minimum_quantity": float("inf")},
])
def test_chain_rejects_non_positive_or_non_finite_precision(changes):
    with pytest.raises(ValueError, match="option contract precision metadata is invalid"):
        build_option_chain(
            [_call(**changes)], {}, underlying="NIFTY",
            expiry_time=EXPIRY, as_of=AS_OF,
        )
