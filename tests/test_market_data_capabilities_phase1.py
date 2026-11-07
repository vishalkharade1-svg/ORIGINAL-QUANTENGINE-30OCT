"""Phase-1 feature evidence-gate tests."""

import unittest

from data.delta.capabilities import AVAILABLE, UNAVAILABLE, assess_capabilities
from data.delta.public_event_stream import DeltaPublicEventStream


T = 1_775_814_834_000_000


class TestMarketDataCapabilities(unittest.TestCase):
    def test_no_state_means_every_feature_is_unavailable(self):
        capabilities = assess_capabilities(None)
        self.assertEqual(capabilities.traded_ohlcv.status, UNAVAILABLE)
        self.assertEqual(capabilities.footprint.status, UNAVAILABLE)

    def test_traded_volume_does_not_create_delta_or_footprint(self):
        stream = DeltaPublicEventStream()
        stream.ingest({
            "type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101,
            "v": 5, "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1,
        }, receipt_timestamp=T + 2)
        state = stream.store.snapshot("DELTA", "BTCUSDT")
        capabilities = assess_capabilities(state)
        self.assertEqual(capabilities.traded_ohlcv.status, AVAILABLE)
        self.assertEqual(capabilities.volume_analysis.status, AVAILABLE)
        self.assertEqual(capabilities.signed_delta.status, UNAVAILABLE)
        self.assertEqual(capabilities.footprint.status, UNAVAILABLE)

    def test_l2_snapshot_is_not_claimed_as_imbalance(self):
        stream = DeltaPublicEventStream()
        stream.ingest({
            "type": "ob_l2", "sy": "BTCUSDT", "ts": T,
            "b": [["99", "2"], ["98", "3"]], "a": [["101", "4"], ["102", "5"]],
        }, receipt_timestamp=T + 1)
        capabilities = assess_capabilities(stream.store.snapshot("DELTA", "BTCUSDT"))
        self.assertEqual(capabilities.l1_spread.status, AVAILABLE)
        self.assertEqual(capabilities.l2_order_book.status, AVAILABLE)
        self.assertEqual(capabilities.order_book_imbalance.status, UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
