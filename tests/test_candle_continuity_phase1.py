"""Phase-1 candle gap detection tests."""

import unittest

from data.delta.candle_continuity import CandleContinuityTracker
from data.delta.market_events import normalize_candlestick_frame
from data.delta.public_event_stream import DeltaPublicEventStream


T = 1_775_814_834_000_000


def candle(start):
    return normalize_candlestick_frame({
        "type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100,
        "v": 1, "res": "1m", "sy": "BTCUSDT", "cst": start, "ts": start + 1,
    }, receipt_timestamp=start + 2)


class TestCandleContinuity(unittest.TestCase):
    def test_gap_is_explicit_not_filled(self):
        tracker = CandleContinuityTracker()
        tracker.ingest(candle(T))
        gap = tracker.ingest(candle(T + 180_000_000))
        self.assertEqual(gap.missing_candles, 2)
        status = tracker.status("DELTA", "BTCUSDT", "1m")
        self.assertEqual(status["status"], "DATA_GAP_UNREPAIRED")
        self.assertEqual(status["missing_candles"], 2)

    def test_duplicate_and_out_of_order_do_not_create_false_gap(self):
        tracker = CandleContinuityTracker()
        tracker.ingest(candle(T + 60_000_000))
        self.assertIsNone(tracker.ingest(candle(T + 60_000_000)))
        self.assertIsNone(tracker.ingest(candle(T)))
        self.assertEqual(tracker.rejected, 1)
        self.assertEqual(tracker.status("DELTA", "BTCUSDT", "1m")["status"], "CONTINUOUS")

    def test_stream_exposes_continuity_tracker_without_runtime_routing(self):
        stream = DeltaPublicEventStream()
        for start in (T, T + 180_000_000):
            stream.ingest({
                "type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100,
                "v": 1, "res": "1m", "sy": "BTCUSDT", "cst": start, "ts": start + 1,
            }, receipt_timestamp=start + 2)
        self.assertEqual(stream.continuity.status("DELTA", "BTCUSDT", "1m")["missing_candles"], 2)


if __name__ == "__main__":
    unittest.main()
