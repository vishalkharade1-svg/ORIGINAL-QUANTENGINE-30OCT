from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.exchanges.market_data_validation import (
    NormalizedBar,
    NormalizedQuote,
    validate_quote,
    validate_quote_batch,
)

NOW = datetime(2026, 10, 25, 4, 30, tzinfo=timezone.utc)


def test_quote_normalizes_timezone_and_accepts_valid_two_sided_market():
    local = timezone(timedelta(hours=5, minutes=30))
    quote = NormalizedQuote("NIFTY", NOW.astimezone(local), "fixture", last="101.5", bid="101", ask="102")
    assert quote.timestamp == NOW
    report = validate_quote(quote, now=NOW, max_age_seconds=2, expected_symbol="NIFTY")
    assert report.valid
    assert quote.bid == Decimal("101")


def test_quote_rejects_naive_timestamp_empty_symbol_bad_price_and_crossed_market():
    with pytest.raises(ValueError, match="timezone-aware"):
        NormalizedQuote("BTCUSD", datetime(2026, 10, 25), "fixture", last=1)
    with pytest.raises(ValueError, match="symbol is required"):
        NormalizedQuote(" ", NOW, "fixture", last=1)
    with pytest.raises(ValueError, match="finite positive"):
        NormalizedQuote("EUR/USD", NOW, "fixture", last="NaN")
    with pytest.raises(ValueError, match="crossed quote"):
        NormalizedQuote("BTCUSD", NOW, "fixture", bid=102, ask=101)


def test_stale_future_and_wrong_symbol_are_rejected():
    stale = NormalizedQuote("BTCUSD", NOW - timedelta(seconds=10), "fixture", last=100)
    report = validate_quote(stale, now=NOW, max_age_seconds=2, expected_symbol="BTCUSD")
    assert not report.valid and "stale market data" in report.errors
    future = NormalizedQuote("BTCUSD", NOW + timedelta(seconds=5), "fixture", last=100)
    report = validate_quote(future, now=NOW, max_age_seconds=10)
    assert "market data timestamp is in the future" in report.errors
    report = validate_quote(stale, now=NOW, max_age_seconds=20, expected_symbol="ETHUSD")
    assert "symbol mismatch" in report.errors


def test_batch_rejects_duplicates_and_empty_input():
    quote = NormalizedQuote("eur/usd", NOW, "fixture", last=1.1)
    report = validate_quote_batch([quote, quote], now=NOW, max_age_seconds=1)
    assert not report.valid and "duplicate symbol in quote batch" in report.errors
    assert "quote batch is empty" in validate_quote_batch([], now=NOW, max_age_seconds=1).errors


def test_bar_rejects_invalid_ohlc_and_negative_volume():
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        NormalizedBar("NIFTY", NOW, "fixture", open=10, high=9, low=8, close=9, volume=1)
    with pytest.raises(ValueError, match="non-negative"):
        NormalizedBar("NIFTY", NOW, "fixture", open=9, high=10, low=8, close=9, volume=-1)


def test_bar_accepts_consistent_ohlc_and_converts_numeric_fields():
    bar = NormalizedBar("NIFTY", NOW, "fixture", open="9", high="11", low="8", close="10", volume="12")
    assert bar.open == Decimal("9")
    assert bar.volume == Decimal("12")
