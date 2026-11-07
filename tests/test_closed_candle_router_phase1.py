"""Phase-1 closed-candle-only routing tests."""

import unittest

from data.delta.closed_candle_router import ClosedCandleRouter
from data.delta.public_event_stream import DeltaPublicEventStream


T = 1_775_814_834_000_000


def candle(start, close):
    return {
        "type": "candlestick_1m", "o": 100, "h": max(100, close),
        "l": min(100, close), "c": close, "v": 1, "res": "1m",
        "sy": "BTCUSDT", "cst": start, "ts": start + 1,
    }


class TestClosedCandleRouter(unittest.TestCase):
    def test_only_later_start_delivers_a_confirmed_candle(self):
        delivered = []
        stream = DeltaPublicEventStream()
        router = ClosedCandleRouter(delivered.append)
        self.assertFalse(router.route(stream.ingest(candle(T, 101), receipt_timestamp=T + 1)))
        self.assertFalse(router.route(stream.ingest(dict(candle(T, 102), ts=T + 2), receipt_timestamp=T + 2)))
        result = stream.ingest(candle(T + 60_000_000, 103), receipt_timestamp=T + 60_000_001)
        self.assertTrue(router.route(result))
        self.assertEqual([item.close for item in delivered], [102.0])
        self.assertEqual((router.delivered, router.suppressed), (1, 2))

    def test_non_candle_event_cannot_reach_consumer(self):
        delivered = []
        stream = DeltaPublicEventStream()
        router = ClosedCandleRouter(delivered.append)
        result = stream.ingest({
            "type": "trades", "p": 100, "s": 1, "r": "t", "sy": "BTCUSDT", "t": T, "ts": T,
        }, receipt_timestamp=T + 1)
        self.assertFalse(router.route(result))
        self.assertEqual(delivered, [])

    def test_confirmed_candle_after_gap_is_suppressed(self):
        delivered = []
        stream = DeltaPublicEventStream()
        router = ClosedCandleRouter(delivered.append)
        router.route(stream.ingest(candle(T, 101), receipt_timestamp=T + 1))
        # Jump three minutes: the previous candle is final, but the series is
        # discontinuous and therefore cannot enter a strategy consumer.
        result = stream.ingest(candle(T + 180_000_000, 102), receipt_timestamp=T + 180_000_001)
        self.assertEqual(result.data_gap_status, "DATA_GAP_UNREPAIRED")
        self.assertFalse(router.route(result))
        self.assertEqual(delivered, [])


if __name__ == "__main__":
    unittest.main()
