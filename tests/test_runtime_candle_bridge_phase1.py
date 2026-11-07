"""Tests for the fail-closed normalized-to-runtime candle boundary."""

import unittest

from data.delta.public_event_stream import DeltaPublicEventStream
from data.delta.runtime_candle_bridge import to_runtime_candle


T = 1_775_814_780_000_000


def candle(start, publish, *, symbol="BTCUSDT", volume=4):
    frame = {
        "type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101,
        "res": "1m", "sy": symbol, "cst": start, "ts": publish,
    }
    if volume is not None:
        frame["v"] = volume
    return frame


class TestRuntimeCandleBridge(unittest.TestCase):
    def _closed_result(self, *, symbol="BTCUSDT", volume=4):
        stream = DeltaPublicEventStream()
        stream.ingest(candle(T, T + 1, symbol=symbol, volume=volume), receipt_timestamp=T + 2)
        return stream.ingest(
            candle(T + 60_000_000, T + 60_000_001, symbol=symbol, volume=volume),
            receipt_timestamp=T + 60_000_002,
        )

    def test_only_verified_traded_closed_candle_converts(self):
        decision = to_runtime_candle(self._closed_result(), expected_resolution="1m")
        self.assertEqual(decision.reason, "accepted")
        self.assertTrue(decision.candle.closed)
        self.assertEqual(decision.candle.volume, 4)
        self.assertEqual(decision.candle.symbol, "BTCUSDT")

    def test_missing_volume_does_not_become_zero(self):
        decision = to_runtime_candle(self._closed_result(volume=None), expected_resolution="1m")
        self.assertIsNone(decision.candle)
        self.assertEqual(decision.reason, "traded candle volume is unavailable")

    def test_mark_price_never_crosses_runtime_boundary(self):
        decision = to_runtime_candle(self._closed_result(symbol="MARK:BTCUSDT"), expected_resolution="1m")
        self.assertIsNone(decision.candle)
        self.assertEqual(decision.reason, "mark-price candle cannot enter strategy runtime")

    def test_mismatched_resolution_is_rejected(self):
        decision = to_runtime_candle(self._closed_result(), expected_resolution="5m")
        self.assertIsNone(decision.candle)
        self.assertEqual(decision.reason, "candle resolution does not match subscription")


if __name__ == "__main__":
    unittest.main()
