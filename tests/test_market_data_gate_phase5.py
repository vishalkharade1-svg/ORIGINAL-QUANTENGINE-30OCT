"""Market-data risk precondition tests."""

import unittest

from core.risk.market_data_gate import evaluate_market_data
from data.delta.public_event_stream import DeltaPublicEventStream


T = 1_775_815_380_000_000
NOW = T // 1_000_000 + 2


def add_candle(stream, *, volume=2):
    frame = {"type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101,
             "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1}
    if volume is not None:
        frame["v"] = volume
    stream.ingest(frame, receipt_timestamp=T + 2)


class TestMarketDataGate(unittest.TestCase):
    def test_missing_state_fails_closed(self):
        self.assertFalse(evaluate_market_data(None).allowed)

    def test_continuous_volume_state_passes(self):
        stream = DeltaPublicEventStream()
        add_candle(stream)
        state = stream.store.snapshot("DELTA", "BTCUSDT", now=NOW, stale_after_seconds=60)
        self.assertTrue(evaluate_market_data(state).allowed)

    def test_missing_volume_stale_and_gap_are_each_blocked(self):
        stream = DeltaPublicEventStream()
        add_candle(stream, volume=None)
        state = stream.store.snapshot("DELTA", "BTCUSDT", now=NOW, stale_after_seconds=60)
        self.assertEqual(evaluate_market_data(state).reason, "MARKET_DATA_VOLUME_UNAVAILABLE")
        add_candle(stream, volume=2)
        stale = stream.store.snapshot("DELTA", "BTCUSDT", now=NOW + 1000, stale_after_seconds=60)
        self.assertEqual(evaluate_market_data(stale).reason, "MARKET_DATA_STALE")
        stream.store.set_gap_status("DELTA", "BTCUSDT", "DATA_GAP_UNREPAIRED")
        gap = stream.store.snapshot("DELTA", "BTCUSDT", now=NOW, stale_after_seconds=60)
        self.assertEqual(evaluate_market_data(gap).reason, "MARKET_DATA_GAP_OR_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
