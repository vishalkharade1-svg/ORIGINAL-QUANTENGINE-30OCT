"""Phase 467: option-chain exchange-scope integrity."""
from datetime import datetime, timezone
import pytest
from core.options import build_option_chain
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION, PRODUCT_PUT_OPTION

AS_OF = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
EXPIRY = int(datetime(2026, 12, 31, 8, 0, tzinfo=timezone.utc).timestamp())

def _instrument(right, exchange="NSE"):
    return Instrument(
        instrument_id=f"{exchange.lower()}-nifty-{EXPIRY}-{right}",
        symbol=f"{exchange}-NIFTY26DEC22500-{'CE' if right == 'call' else 'PE'}",
        exchange=exchange,
        product_type=PRODUCT_CALL_OPTION if right == "call" else PRODUCT_PUT_OPTION,
        underlying_asset="NIFTY", quote_asset="INR", expiry_time=EXPIRY,
        strike_price=22500.0, option_type=right, tick_size=0.05,
        quantity_step=1.0, minimum_quantity=25.0, trading_enabled=True,
        lot_size=25, contract_multiplier=1.0,
    )

def test_chain_rejects_contracts_from_different_exchanges():
    call = _instrument("call", "NSE")
    put = _instrument("put", "BSE")
    with pytest.raises(ValueError, match="option chain exchange mismatch"):
        build_option_chain([call, put], {}, underlying="NIFTY",
                           expiry_time=EXPIRY, as_of=AS_OF)

def test_chain_exposes_one_verified_exchange_for_all_legs():
    call = _instrument("call", "NSE")
    put = _instrument("put", "NSE")
    chain = build_option_chain([call, put], {}, underlying="NIFTY",
                               expiry_time=EXPIRY, as_of=AS_OF)
    assert chain.exchange == "NSE"
    assert chain.entries[0].call.instrument.exchange == chain.exchange
    assert chain.entries[0].put.instrument.exchange == chain.exchange
