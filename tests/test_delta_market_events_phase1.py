"""Captured-schema normalization tests for Phase 1 Delta public frames."""

import unittest

from data.delta.market_events import (
    InvalidMarketFrame,
    normalize_candlestick_frame,
    normalize_l1_book_frame,
    normalize_l2_book_frame,
    normalize_trade_frame,
)


MICROSECONDS = 1_775_814_834_503_627


class TestDeltaTradeNormalization(unittest.TestCase):
    def test_documented_trade_frame_preserves_unknown_aggressor(self):
        event = normalize_trade_frame({
            "type": "trades", "p": "72141.5", "r": "m", "s": 1.0,
            "sy": "BTCUSD", "t": MICROSECONDS, "ts": MICROSECONDS + 5,
        }, receipt_timestamp=MICROSECONDS + 9)
        self.assertEqual(event.provenance.instrument, "BTCUSD")
        self.assertEqual(event.provenance.exchange_timestamp, 1_775_814_834)
        self.assertEqual(event.price, 72141.5)
        self.assertEqual(event.quantity, 1.0)
        self.assertEqual(event.maker_taker_role, "maker")
        self.assertIsNone(event.aggressor_side)
        self.assertEqual(event.provenance.provider_publish_timestamp, MICROSECONDS + 5)

    def test_invalid_trade_is_rejected_not_defaulted(self):
        with self.assertRaises(InvalidMarketFrame):
            normalize_trade_frame({
                "type": "trades", "p": "0", "s": 1, "sy": "BTCUSD",
                "t": MICROSECONDS,
            }, receipt_timestamp=MICROSECONDS)


class TestDeltaCandleNormalization(unittest.TestCase):
    def test_traded_price_candle_keeps_documented_volume(self):
        event = normalize_candlestick_frame({
            "type": "candlestick_1m", "c": 71748.0, "h": 71751.5,
            "l": 71737.0, "o": 71737.0, "res": "1m", "sy": "BTCUSD",
            "ts": MICROSECONDS + 9, "cst": MICROSECONDS, "v": 2826.0,
        }, receipt_timestamp=MICROSECONDS + 1)
        self.assertEqual(event.price_basis, "TRADED_PRICE")
        self.assertEqual(event.volume, 2826.0)
        self.assertFalse(event.closed)
        self.assertEqual(event.candle_start_timestamp, 1_775_814_834)
        self.assertEqual(event.provenance.provider_publish_timestamp, MICROSECONDS + 9)

    def test_mark_candle_missing_volume_is_unavailable_not_zero(self):
        event = normalize_candlestick_frame({
            "type": "candlestick_1m", "c": 71748.0, "h": 71751.5,
            "l": 71737.0, "o": 71737.0, "res": "1m", "sy": "MARK:BTCUSD",
            "ts": MICROSECONDS,
        }, receipt_timestamp=MICROSECONDS + 1)
        self.assertEqual(event.price_basis, "MARK_PRICE")
        self.assertIsNone(event.volume)
        self.assertIsNone(event.candle_start_timestamp)

    def test_impossible_ohlc_is_rejected(self):
        with self.assertRaises(InvalidMarketFrame):
            normalize_candlestick_frame({
                "type": "candlestick_1m", "c": 100, "h": 99, "l": 90,
                "o": 95, "res": "1m", "sy": "BTCUSD", "ts": MICROSECONDS,
                "v": 1,
            }, receipt_timestamp=MICROSECONDS)


class TestDeltaBookNormalization(unittest.TestCase):
    def test_documented_l1_frame_has_positive_spread(self):
        event = normalize_l1_book_frame({
            "type": "ob_l1", "bp": "68518.0", "bs": "2452",
            "ap": "68519.0", "as": "285", "sy": "BTCUSD",
            "lts": MICROSECONDS, "ts": MICROSECONDS + 1,
        }, receipt_timestamp=MICROSECONDS + 2)
        self.assertEqual(event.bid_price, 68518.0)
        self.assertEqual(event.ask_quantity, 285.0)
        self.assertIsNone(event.provenance.sequence)

    def test_documented_l2_frame_is_strictly_ordered(self):
        event = normalize_l2_book_frame({
            "type": "ob_l2", "sy": "BTCUSD", "ts": MICROSECONDS,
            "lts": MICROSECONDS - 1,
            "b": [["68524.0", "2452"], ["68523.5", "3000"]],
            "a": [["68525.0", "3313"], ["68525.5", "3009"]],
        }, receipt_timestamp=MICROSECONDS + 1)
        self.assertEqual(len(event.bids), 2)
        self.assertLess(event.bids[0].price, event.asks[0].price)

    def test_crossed_or_unsorted_book_is_rejected(self):
        with self.assertRaises(InvalidMarketFrame):
            normalize_l2_book_frame({
                "type": "ob_l2", "sy": "BTCUSD", "ts": MICROSECONDS,
                "b": [["100", "1"], ["101", "1"]], "a": [["99", "1"]],
            }, receipt_timestamp=MICROSECONDS)


if __name__ == "__main__":
    unittest.main()
