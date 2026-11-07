"""Phase-1 authoritative market-state tests."""

import unittest

from data.delta.market_events import normalize_candlestick_frame, normalize_trade_frame
from data.delta.market_events import normalize_l1_book_frame
from data.delta.market_state_store import MarketStateStore


T = 1_775_814_834_503_627


def candle(*, ts=T, volume=2.0, symbol="BTCUSD"):
    frame = {
        "type": "candlestick_1m", "o": 100, "h": 103, "l": 99,
        "c": 102, "v": volume, "res": "1m", "sy": symbol, "ts": ts,
    }
    if volume is None:
        del frame["v"]
    return normalize_candlestick_frame(frame, receipt_timestamp=ts + 1)


class TestAuthoritativeMarketState(unittest.TestCase):
    def test_candle_is_deduplicated_and_stale_state_is_explicit(self):
        store = MarketStateStore()
        self.assertTrue(store.apply_candle(candle()))
        self.assertFalse(store.apply_candle(candle()))
        state = store.snapshot("DELTA", "BTCUSD", now=1_775_814_900, stale_after_seconds=60)
        self.assertEqual(state.candles["1m"].close, 102.0)
        self.assertTrue(state.data_quality.stale)
        self.assertEqual(state.data_quality.rejected_events, 1)
        self.assertEqual(state.data_quality.sequence_status, "UNAVAILABLE")

    def test_missing_mark_volume_remains_unavailable(self):
        store = MarketStateStore()
        self.assertTrue(store.apply_candle(candle(volume=None, symbol="MARK:BTCUSD")))
        state = store.snapshot("DELTA", "MARK:BTCUSD")
        self.assertFalse(state.volume_available)
        self.assertIsNone(state.candles["1m"].volume)
        self.assertIsNone(state.delta)
        self.assertIsNone(state.order_book)

    def test_newer_publish_for_same_candle_start_replaces_forming_snapshot(self):
        store = MarketStateStore()
        first = normalize_candlestick_frame({
            "type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100,
            "v": 1, "res": "1m", "sy": "BTCUSD", "cst": T, "ts": T + 1,
        }, receipt_timestamp=T + 2)
        update = normalize_candlestick_frame({
            "type": "candlestick_1m", "o": 100, "h": 103, "l": 99, "c": 102,
            "v": 2, "res": "1m", "sy": "BTCUSD", "cst": T, "ts": T + 2,
        }, receipt_timestamp=T + 3)
        self.assertTrue(store.apply_candle(first))
        self.assertTrue(store.apply_candle(update))
        self.assertEqual(store.snapshot("DELTA", "BTCUSD").candles["1m"].close, 102.0)

    def test_trade_is_retained_without_false_deduplication(self):
        store = MarketStateStore()
        event = normalize_trade_frame({
            "type": "trades", "p": "100", "s": "2", "r": "t",
            "sy": "BTCUSD", "t": T, "ts": T,
        }, receipt_timestamp=T + 2)
        self.assertTrue(store.apply_trade(event))
        state = store.snapshot("DELTA", "BTCUSD")
        self.assertEqual(state.last_trade.quantity, 2.0)
        self.assertIsNone(state.last_trade.aggressor_side)

    def test_newer_book_replaces_older_snapshot(self):
        store = MarketStateStore()
        first = normalize_l1_book_frame({
            "type": "ob_l1", "bp": "99", "bs": "1", "ap": "101", "as": "2",
            "sy": "BTCUSD", "ts": T,
        }, receipt_timestamp=T + 1)
        second = normalize_l1_book_frame({
            "type": "ob_l1", "bp": "100", "bs": "3", "ap": "102", "as": "4",
            "sy": "BTCUSD", "ts": T + 1_000_000,
        }, receipt_timestamp=T + 1_000_001)
        self.assertTrue(store.apply_order_book(first))
        self.assertTrue(store.apply_order_book(second))
        self.assertFalse(store.apply_order_book(first))
        self.assertEqual(store.snapshot("DELTA", "BTCUSD").order_book.bid_price, 100.0)

    def test_gap_status_is_explicit_state_quality(self):
        store = MarketStateStore()
        store.apply_candle(candle())
        store.set_gap_status("DELTA", "BTCUSD", "DATA_GAP_UNREPAIRED")
        self.assertEqual(store.snapshot("DELTA", "BTCUSD").data_quality.gap_status, "DATA_GAP_UNREPAIRED")
        with self.assertRaises(ValueError):
            store.set_gap_status("DELTA", "BTCUSD", "HEALTHY")


if __name__ == "__main__":
    unittest.main()
