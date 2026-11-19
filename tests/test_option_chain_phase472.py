"""Phase 472: option-chain quote coverage and missing-leg metrics."""
from datetime import datetime, timezone

from core.exchanges.market_data_validation import NormalizedQuote
from core.options import build_option_chain
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION, PRODUCT_PUT_OPTION

AS_OF = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
EXPIRY = int(datetime(2026, 12, 31, 8, 0, tzinfo=timezone.utc).timestamp())


def _instrument(right):
    return Instrument(
        instrument_id=f"nse-nifty-{EXPIRY}-{right}",
        symbol=f"NIFTY26DEC22500{'CE' if right == 'call' else 'PE'}",
        exchange="NSE",
        product_type=PRODUCT_CALL_OPTION if right == "call" else PRODUCT_PUT_OPTION,
        underlying_asset="NIFTY", quote_asset="INR", expiry_time=EXPIRY,
        strike_price=22500.0, option_type=right, tick_size=0.05,
        quantity_step=1.0, minimum_quantity=25.0, trading_enabled=True,
        lot_size=25, contract_multiplier=1.0,
    )


def _quote(symbol):
    return NormalizedQuote(symbol=symbol, timestamp=AS_OF, source="broker", last=100)


def test_chain_reports_quote_coverage_separately_from_missing_contract_legs():
    call, put = _instrument("call"), _instrument("put")
    chain = build_option_chain(
        [call, put], {call.symbol: _quote(call.symbol)},
        underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
    )
    assert chain.contract_count == 2
    assert chain.quoted_contract_count == 1
    assert chain.quote_coverage == 0.5
    assert chain.missing_call_quotes == 0
    assert chain.missing_put_quotes == 1
    assert chain.missing_call_legs == 0
    assert chain.missing_put_legs == 0


def test_chain_reports_missing_put_contract_leg_without_counting_it_as_quote():
    call = _instrument("call")
    chain = build_option_chain(
        [call], {call.symbol: _quote(call.symbol)},
        underlying="NIFTY", expiry_time=EXPIRY, as_of=AS_OF,
    )
    assert chain.contract_count == 1
    assert chain.quoted_contract_count == 1
    assert chain.quote_coverage == 1.0
    assert chain.missing_call_legs == 0
    assert chain.missing_put_legs == 1


def test_chain_with_no_quotes_reports_zero_coverage():
    chain = build_option_chain(
        [_instrument("call")], {}, underlying="NIFTY",
        expiry_time=EXPIRY, as_of=AS_OF,
    )
    assert chain.quoted_contract_count == 0
    assert chain.quote_coverage == 0.0
