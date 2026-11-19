from datetime import datetime, timedelta, timezone

from core.exchanges.market_data_validation import NormalizedQuote
from core.exchanges.paper_data_quality_gate import evaluate_paper_quote

NOW = datetime(2026, 10, 25, 4, 30, tzinfo=timezone.utc)


def test_valid_fresh_quote_is_accepted_for_paper_data_only():
    quote = NormalizedQuote("BTCUSD", NOW, "fixture", last="100", bid="99", ask="101")
    result = evaluate_paper_quote(quote, now=NOW, expected_symbol="BTCUSD", max_age_seconds=2)
    assert result.accepted
    assert result.reason_codes == ("PAPER_DATA_ACCEPTED",)


def test_missing_quote_fails_closed():
    result = evaluate_paper_quote(None, now=NOW, expected_symbol="BTCUSD", max_age_seconds=2)
    assert not result.accepted
    assert "MARKET_DATA_UNAVAILABLE" in result.reason_codes


def test_stale_and_mismatched_quote_rejected():
    quote = NormalizedQuote("ETHUSD", NOW - timedelta(seconds=10), "fixture", last=100)
    result = evaluate_paper_quote(quote, now=NOW, expected_symbol="BTCUSD", max_age_seconds=2)
    assert not result.accepted
    assert "SYMBOL_MISMATCH" in result.reason_codes
    assert "MARKET_DATA_STALE" in result.reason_codes


def test_future_timestamp_rejected():
    quote = NormalizedQuote("BTCUSD", NOW + timedelta(seconds=5), "fixture", last=100)
    result = evaluate_paper_quote(quote, now=NOW, expected_symbol="BTCUSD", max_age_seconds=10)
    assert not result.accepted
    assert "MARKET_DATA_FUTURE_TIMESTAMP" in result.reason_codes


def test_two_sided_requirement_rejects_last_only_quote():
    quote = NormalizedQuote("EUR/USD", NOW, "fixture", last="1.1")
    result = evaluate_paper_quote(
        quote, now=NOW, expected_symbol="EUR/USD", max_age_seconds=2,
        require_two_sided_quote=True,
    )
    assert not result.accepted
    assert result.reason_codes == ("TWO_SIDED_QUOTE_REQUIRED",)


def test_invalid_age_tolerance_fails_closed():
    quote = NormalizedQuote("BTCUSD", NOW, "fixture", last=100)
    result = evaluate_paper_quote(quote, now=NOW, expected_symbol="BTCUSD", max_age_seconds=-1)
    assert not result.accepted
    assert result.reason_codes == ("AGE_TOLERANCE_INVALID",)
