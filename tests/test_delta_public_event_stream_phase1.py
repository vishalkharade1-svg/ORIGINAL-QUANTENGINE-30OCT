"""Raw-frame -> normalized event -> authoritative state Phase-1 tests."""

import unittest

from data.delta.public_event_stream import DeltaPublicEventStream


T = 1_775_814_834_503_627


class TestDeltaPublicEventStream(unittest.TestCase):
    def test_documented_frames_reach_one_authoritative_state(self):
        stream = DeltaPublicEventStream()
        trade = {"type": "trades", "p": "100", "s": "2", "r": "t", "sy": "BTCUSD", "t": T, "ts": T}
        candle = {"type": "candlestick_1m", "o": 99, "h": 103, "l": 98, "c": 100, "v": 5, "res": "1m", "sy": "BTCUSD", "ts": T + 1_000_000}
        book = {"type": "ob_l1", "bp": "99", "bs": "3", "ap": "101", "as": "4", "sy": "BTCUSD", "ts": T + 2_000_000}
        for frame in (trade, candle, book):
            self.assertEqual(stream.ingest(frame, receipt_timestamp=T + 3_000_000).status, "APPLIED")
        state = stream.store.snapshot("DELTA", "BTCUSD")
        self.assertEqual(state.last_trade.price, 100.0)
        self.assertEqual(state.candles["1m"].volume, 5.0)
        self.assertEqual(state.order_book.ask_price, 101.0)

    def test_bad_old_and_unknown_frames_are_never_applied(self):
        stream = DeltaPublicEventStream()
        valid = {"type": "ob_l1", "bp": "99", "bs": "1", "ap": "101", "as": "1", "sy": "BTCUSD", "ts": T}
        self.assertEqual(stream.ingest(valid, receipt_timestamp=T + 1).status, "APPLIED")
        self.assertEqual(stream.ingest(valid, receipt_timestamp=T + 2).status, "DUPLICATE_OR_OLD")
        self.assertEqual(stream.ingest({"type": "ob_l1", "bp": "100", "ap": "99", "sy": "BTCUSD", "ts": T + 2}, receipt_timestamp=T + 3).status, "REJECTED")
        self.assertEqual(stream.ingest({"type": "ticker"}, receipt_timestamp=T + 4).status, "UNHANDLED")
        self.assertEqual(stream.stats(), {"applied": 1, "duplicates_or_old": 1, "rejected": 1, "unhandled": 1})

    def test_candle_result_reports_unrepaired_gap(self):
        stream = DeltaPublicEventStream()
        first = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1, "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1}
        jumped = dict(first, cst=T + 180_000_000, ts=T + 180_000_001)
        self.assertEqual(stream.ingest(first, receipt_timestamp=T + 1).data_gap_status, "CONTINUOUS")
        self.assertEqual(stream.ingest(jumped, receipt_timestamp=T + 180_000_002).data_gap_status, "DATA_GAP_UNREPAIRED")
        self.assertEqual(stream.store.snapshot("DELTA", "BTCUSDT").data_quality.gap_status, "DATA_GAP_UNREPAIRED")

    def test_later_candle_start_emits_the_latest_prior_forming_value(self):
        stream = DeltaPublicEventStream()
        first = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1, "res": "1m", "sy": "BTCUSD", "cst": T, "ts": T + 1}
        update = dict(first, h=103, c=102, v=2, ts=T + 2)
        next_candle = dict(first, cst=T + 60_000_000, ts=T + 60_000_001, c=104, h=104)
        self.assertIsNone(stream.ingest(first, receipt_timestamp=T + 1).closed_candle)
        self.assertIsNone(stream.ingest(update, receipt_timestamp=T + 2).closed_candle)
        closed = stream.ingest(next_candle, receipt_timestamp=T + 60_000_002).closed_candle
        self.assertTrue(closed.closed)
        self.assertEqual(closed.close, 102.0)


if __name__ == "__main__":
    unittest.main()
