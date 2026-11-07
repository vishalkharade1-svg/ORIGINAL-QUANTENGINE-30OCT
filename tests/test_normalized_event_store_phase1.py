"""Phase-1 normalized event-journal tests."""

import unittest

from data.delta.event_store import NormalizedEventStore
from data.delta.market_events import normalize_trade_frame
from data.delta.public_event_stream import DeltaPublicEventStream


T = 1_775_814_834_000_000


def trade(price, symbol="BTCUSDT"):
    return normalize_trade_frame({
        "type": "trades", "p": price, "s": 1, "r": "t", "sy": symbol,
        "t": T, "ts": T + 1,
    }, receipt_timestamp=T + 2)


class TestNormalizedEventStore(unittest.TestCase):
    def test_bounded_history_preserves_monotonic_ordinals(self):
        store = NormalizedEventStore(max_events=2)
        store.append(trade(100))
        store.append(trade(101, "ETHUSDT"))
        store.append(trade(102))
        self.assertEqual([item.ordinal for item in store.all()], [2, 3])
        self.assertEqual(len(store.for_instrument("DELTA", "BTCUSDT")), 1)

    def test_rejected_frame_is_not_journaled(self):
        stream = DeltaPublicEventStream(event_store=NormalizedEventStore())
        self.assertEqual(stream.ingest({"type": "ob_l1", "bp": 100, "ap": 99, "sy": "BTCUSDT", "ts": T}, receipt_timestamp=T).status, "REJECTED")
        self.assertEqual(len(stream.event_store), 0)


if __name__ == "__main__":
    unittest.main()
