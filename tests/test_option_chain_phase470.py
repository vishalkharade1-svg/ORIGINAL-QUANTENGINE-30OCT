"""Phase 470: option-chain quote timestamp coherence."""
from datetime import datetime, timedelta, timezone
import pytest

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
    return NormalizedQuote(
        symbol=symbol, timestamp=timestamp, source="broker",
        last=100, bid=99, ask=101,
    )


def test_chain_rejects_quote_skew_even_when_each_quote_is_fresh():
    call, put = _instrument("call"), _instrument("put")
    quotes = {
        call.symbol: _quote(call.symbol, AS_OF),
        put.symbol: _quote(put.symbol, AS_OF - timedelta(seconds=3)),
    }
    with pytest.raises(ValueError, match="quote timestamp skew exceeds limit"):
        build_option_chain(
            [call, put], quotes, underlying="NIFTY",
            expiry_time=EXPIRY, as_of=AS_OF,
            max_quote_age_seconds=5, max_quote_skew_seconds=2,
        )


def test_chain_accepts_quotes_within_configured_timestamp_skew():
    call, put = _instrument("call"), _instrument("put")
    quotes = {
        call.symbol: _quote(call.symbol, AS_OF),
        put.symbol: _quote(put.symbol, AS_OF - timedelta(seconds=1)),
    }
    chain = build_option_chain(
        [call, put], quotes, underlying="NIFTY",
        expiry_time=EXPIRY, as_of=AS_OF,
        max_quote_age_seconds=5, max_quote_skew_seconds=1,
    )
    assert chain.entries[0].call.quote.timestamp == AS_OF
    assert chain.entries[0].put.quote.timestamp == AS_OF - timedelta(seconds=1)


@pytest.mark.parametrize("limit", [True, False, -1, float("nan"), float("inf")])
def test_chain_rejects_invalid_quote_skew_limit(limit):
    with pytest.raises(ValueError, match="max_quote_skew_seconds must be finite and non-negative"):
        build_option_chain(
            [_instrument("call")], {}, underlying="NIFTY",
            expiry_time=EXPIRY, as_of=AS_OF,
            max_quote_skew_seconds=limit,
        )
