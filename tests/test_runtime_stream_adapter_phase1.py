"""Phase-1 tests for the fail-closed runtime stream adapter."""

import unittest

from data.delta.runtime_stream_adapter import DeltaRuntimeStreamAdapter


T = 1_775_814_900_000_000


def candle(start, publish, *, symbol="BTCUSDT", volume=3, resolution="1m"):
    frame = {
        "type": "candlestick_" + resolution, "o": 100, "h": 102,
        "l": 99, "c": 101, "res": resolution, "sy": symbol,
        "cst": start, "ts": publish,
    }
    if volume is not None:
        frame["v"] = volume
    return frame


class TestDeltaRuntimeStreamAdapter(unittest.TestCase):
    def test_delivers_only_previous_verified_closed_candle(self):
        received = []
        adapter = DeltaRuntimeStreamAdapter("BTCUSDT", "1m", received.append)
        adapter.ingest(candle(T, T + 1), receipt_timestamp=T + 2)
        adapter.ingest(candle(T + 60_000_000, T + 60_000_001), receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].closed)
        self.assertEqual(received[0].volume, 3)
        self.assertEqual(adapter.stats()["delivered"], 1)

    def test_rejects_missing_volume_and_wrong_symbol(self):
        received = []
        adapter = DeltaRuntimeStreamAdapter("BTCUSDT", "1m", received.append)
        adapter.ingest(candle(T, T + 1, volume=None), receipt_timestamp=T + 2)
        adapter.ingest(candle(T + 60_000_000, T + 60_000_001, volume=None), receipt_timestamp=T + 60_000_002)
        adapter.ingest(candle(T + 120_000_000, T + 120_000_001, symbol="ETHUSDT"), receipt_timestamp=T + 120_000_002)
        adapter.ingest(candle(T + 180_000_000, T + 180_000_001, symbol="ETHUSDT"), receipt_timestamp=T + 180_000_002)
        self.assertEqual(received, [])
        drops = adapter.stats()["drops"]
        self.assertGreater(drops["traded candle volume is unavailable"], 0)
        self.assertGreater(drops["candle is for another subscription symbol"], 0)

    def test_callback_failure_is_observable_and_isolated(self):
        def broken(_candle):
            raise RuntimeError("consumer failed")

        adapter = DeltaRuntimeStreamAdapter("BTCUSDT", "1m", broken)
        adapter.ingest(candle(T, T + 1), receipt_timestamp=T + 2)
        adapter.ingest(candle(T + 60_000_000, T + 60_000_001), receipt_timestamp=T + 60_000_002)
        stats = adapter.stats()
        self.assertEqual(stats["callback_errors"], 1)
        self.assertEqual(stats["last_callback_error"], "consumer failed")


if __name__ == "__main__":
    unittest.main()
