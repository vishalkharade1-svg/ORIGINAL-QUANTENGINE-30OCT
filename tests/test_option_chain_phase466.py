"""Phase 466: option-chain identity and tolerance hardening."""
from datetime import datetime, timezone
import pytest
from core.options import build_option_chain
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION, PRODUCT_PUT_OPTION

AS_OF = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
EXPIRY = int(datetime(2026, 12, 31, 8, 0, tzinfo=timezone.utc).timestamp())

def _instrument(right="call", **changes):
    values = dict(instrument_id=f"nse-nifty-{EXPIRY}-{right}",
                  symbol=f"NIFTY26DEC22500{'CE' if right == 'call' else 'PE'}",
                  exchange="NSE",
                  product_type=PRODUCT_CALL_OPTION if right == "call" else PRODUCT_PUT_OPTION,
                  underlying_asset="NIFTY", quote_asset="INR", expiry_time=EXPIRY,
                  strike_price=22500.0, option_type=right, tick_size=0.05,
                  quantity_step=1.0, minimum_quantity=25.0, trading_enabled=True,
                  lot_size=25, contract_multiplier=1.0)
    values.update(changes)
    return Instrument(**values)

@pytest.mark.parametrize("changes, message", [
    ({"instrument_id": ""}, "instrument ID is required"),
    ({"symbol": ""}, "instrument symbol is required"),
    ({"exchange": ""}, "instrument exchange is required"),
])
def test_chain_rejects_missing_canonical_identity(changes, message):
    with pytest.raises(ValueError, match=message):
        build_option_chain([_instrument(**changes)], {}, underlying="NIFTY",
                           expiry_time=EXPIRY, as_of=AS_OF)

def test_chain_rejects_duplicate_instrument_id_even_when_symbols_differ():
    call = _instrument()
    put = _instrument("put", instrument_id=call.instrument_id)
    with pytest.raises(ValueError, match="duplicate option instrument ID"):
        build_option_chain([call, put], {}, underlying="NIFTY",
                           expiry_time=EXPIRY, as_of=AS_OF)

@pytest.mark.parametrize("age", [True, False])
def test_chain_rejects_boolean_quote_age_tolerance(age):
    with pytest.raises(ValueError, match="finite and non-negative"):
        build_option_chain([_instrument()], {}, underlying="NIFTY",
                           expiry_time=EXPIRY, as_of=AS_OF,
                           max_quote_age_seconds=age)

def test_chain_accepts_broader_quote_snapshot_without_consuming_other_symbols():
    from core.exchanges.market_data_validation import NormalizedQuote
    call = _instrument()
    unrelated = NormalizedQuote(symbol="OTHER", timestamp=AS_OF, source="other-feed", last=10)
    chain = build_option_chain([call], {"OTHER": unrelated}, underlying="NIFTY",
                               expiry_time=EXPIRY, as_of=AS_OF)
    assert chain.entries[0].call.quote is None
    assert chain.source == ""
