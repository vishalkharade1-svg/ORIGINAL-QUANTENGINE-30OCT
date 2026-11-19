"""Phase 465: provider-neutral option chain integrity and quote freshness."""
from datetime import datetime, timedelta, timezone
import pytest
from core.exchanges.market_data_validation import NormalizedQuote
from core.options import build_option_chain
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION, PRODUCT_PUT_OPTION

AS_OF = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
EXPIRY = int(datetime(2026, 12, 31, 8, 0, tzinfo=timezone.utc).timestamp())


def _instrument(right, strike=22500, **changes):
    values = dict(
        instrument_id=f"nse-nifty-{EXPIRY}-{strike}-{right}",
        symbol=f"NIFTY26DEC{strike}{'CE' if right == 'call' else 'PE'}",
        exchange="NSE",
        product_type=PRODUCT_CALL_OPTION if right == "call" else PRODUCT_PUT_OPTION,
        underlying_asset="NIFTY",
        quote_asset="INR",
        expiry_time=EXPIRY,
        strike_price=float(strike),
        option_type=right,
        tick_size=0.05,
        quantity_step=1.0,
        minimum_quantity=25.0,
        trading_enabled=True,
        lot_size=25,
        contract_multiplier=1.0,
    )
    values.update(changes)
    return Instrument(**values)


def _quote(symbol, *, age_seconds=0, source="broker"):
    return NormalizedQuote(
        symbol=symbol, timestamp=AS_OF - timedelta(seconds=age_seconds),
        source=source, last=100, bid=99, ask=101,
    )


def test_chain_pairs_calls_and_puts_by_strike_in_sorted_order():
    call_22500 = _instrument("call", 22500)
    put_22500 = _instrument("put", 22500)
    call_22600 = _instrument("call", 22600)
    quotes = {
        call_22500.symbol: _quote(call_22500.symbol),
        put_22500.symbol: _quote(put_22500.symbol),
        call_22600.symbol: _quote(call_22600.symbol),
    }
    chain = build_option_chain(
        [call_22600, put_22500, call_22500], quotes,
        underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
    )
    assert [entry.strike for entry in chain.entries] == [22500, 22600]
    assert chain.entries[0].call.quote.last == 100
    assert chain.entries[0].put.quote.last == 100
    assert chain.entries[1].put is None
    assert chain.missing_call_quotes == 0
    assert chain.missing_put_quotes == 0
    assert chain.source == "broker"


def test_missing_quote_is_preserved_as_missing_not_synthesized():
    call = _instrument("call")
    put = _instrument("put")
    chain = build_option_chain(
        [call, put], {call.symbol: _quote(call.symbol)},
        underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
    )
    assert chain.entries[0].call.quote is not None
    assert chain.entries[0].put.quote is None
    assert chain.missing_put_quotes == 1


def test_chain_rejects_stale_or_wrong_symbol_quotes():
    call = _instrument("call")
    with pytest.raises(ValueError, match="stale market data"):
        build_option_chain(
            [call], {call.symbol: _quote(call.symbol, age_seconds=30)},
            underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
            max_quote_age_seconds=5,
        )
    wrong = NormalizedQuote(symbol="OTHER", timestamp=AS_OF, source="broker", last=100)
    with pytest.raises(ValueError, match="symbol mismatch"):
        build_option_chain(
            [call], {call.symbol: wrong},
            underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
        )


def test_chain_rejects_duplicate_right_and_inconsistent_contract_size():
    call = _instrument("call")
    duplicate = _instrument("call", symbol="NIFTY26DEC22500CE-ALT")
    with pytest.raises(ValueError, match="duplicate call"):
        build_option_chain(
            [call, duplicate], {}, underlying="NIFTY",
            expiry_time=EXPIRY, as_of=AS_OF,
        )
    with pytest.raises(ValueError, match="lot size or multiplier mismatch"):
        build_option_chain(
            [call, _instrument("put", lot_size=50)], {},
            underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
        )


@pytest.mark.parametrize(
    "instruments, underlying, expiry",
    [
        ([_instrument("call", underlying_asset="BANKNIFTY")], "NIFTY", EXPIRY),
        ([_instrument("call")], "NIFTY", EXPIRY + 1),
        ([_instrument("call", lot_size=None)], "NIFTY", EXPIRY),
        ([_instrument("call", option_type="put")], "NIFTY", EXPIRY),
    ],
)
def test_chain_rejects_mismatched_or_incomplete_contract_metadata(instruments, underlying, expiry):
    with pytest.raises(ValueError):
        build_option_chain(
            instruments, {}, underlying=underlying,
            expiry_time=expiry, as_of=AS_OF,
        )


def test_chain_rejects_mixed_quote_sources_and_expired_chain():
    call = _instrument("call")
    put = _instrument("put")
    with pytest.raises(ValueError, match="one consistent source"):
        build_option_chain(
            [call, put],
            {call.symbol: _quote(call.symbol, source="vendor-a"),
             put.symbol: _quote(put.symbol, source="vendor-b")},
            underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
        )
    with pytest.raises(ValueError, match="not in the future"):
        build_option_chain(
            [call], {}, underlying="NIFTY",
            expiry_time=int((AS_OF - timedelta(days=1)).timestamp()),
            as_of=AS_OF,
        )
