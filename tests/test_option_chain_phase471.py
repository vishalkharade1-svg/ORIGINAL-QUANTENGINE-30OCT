"""Phase 471: explicit option-chain quote timestamp provenance."""
from datetime import datetime, timedelta, timezone

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


def _quote(symbol, timestamp):
    return NormalizedQuote(symbol=symbol, timestamp=timestamp, source="broker", last=100)


def test_chain_exposes_actual_quote_time_bounds_and_skew():
    call, put = _instrument("call"), _instrument("put")
    oldest = AS_OF - timedelta(milliseconds=750)
    quotes = {
        call.symbol: _quote(call.symbol, AS_OF),
        put.symbol: _quote(put.symbol, oldest),
    }
    chain = build_option_chain(
        [call, put], quotes, underlying="NIFTY",
        expiry_time=EXPIRY, as_of=AS_OF,
        max_quote_age_seconds=5, max_quote_skew_seconds=1,
    )
    assert chain.quote_timestamp_start == oldest
    assert chain.quote_timestamp_end == AS_OF
    assert chain.quote_skew_seconds == 0.75


def test_chain_without_quotes_reports_unknown_quote_time_provenance():
    chain = build_option_chain(
        [_instrument("call")], {}, underlying="NIFTY",
        expiry_time=EXPIRY, as_of=AS_OF,
    )
    assert chain.quote_timestamp_start is None
    assert chain.quote_timestamp_end is None
    assert chain.quote_skew_seconds is None
