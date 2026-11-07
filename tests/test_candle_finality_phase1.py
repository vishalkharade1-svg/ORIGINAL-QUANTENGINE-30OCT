"""Phase-1 causal candle finality tests."""

import unittest

from data.delta.candle_finality import CandleFinalityTracker
from data.delta.market_events import normalize_candlestick_frame


T = 1_775_814_834_000_000


def frame(start: int, close: float):
    return normalize_candlestick_frame({
        "type": "candlestick_1m", "o": 100, "h": max(100, close),
        "l": min(100, close), "c": close, "v": 1, "res": "1m",
        "sy": "BTCUSDT", "cst": start, "ts": start + 10,
    }, receipt_timestamp=start + 20)


class TestCandleFinality(unittest.TestCase):
    def test_only_a_later_observed_start_confirms_previous_candle(self):
        tracker = CandleFinalityTracker()
        self.assertIsNone(tracker.ingest(frame(T, 101)))
        self.assertIsNone(tracker.ingest(frame(T, 102)))
        closed = tracker.ingest(frame(T + 60_000_000, 103))
        self.assertTrue(closed.closed)
        self.assertEqual(closed.close, 102.0)
        self.assertEqual(tracker.forming("DELTA", "BTCUSDT", "1m").close, 103.0)

    def test_older_start_is_rejected_and_cannot_repaint_forming_candle(self):
        tracker = CandleFinalityTracker()
        tracker.ingest(frame(T + 60_000_000, 103))
        self.assertIsNone(tracker.ingest(frame(T, 99)))
        self.assertEqual(tracker.rejected, 1)
        self.assertEqual(tracker.forming("DELTA", "BTCUSDT", "1m").close, 103.0)

    def test_missing_start_is_not_finalized_from_publish_time(self):
        tracker = CandleFinalityTracker()
        candle = normalize_candlestick_frame({
            "type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
            "c": 100, "v": 1, "res": "1m", "sy": "BTCUSDT", "ts": T,
        }, receipt_timestamp=T + 1)
        self.assertIsNone(tracker.ingest(candle))
        self.assertEqual(tracker.rejected, 1)


if __name__ == "__main__":
    unittest.main()
