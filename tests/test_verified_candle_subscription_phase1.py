"""Tests for the verified candle subscription migration contract."""

import unittest

from data.delta.verified_candle_subscription import (
    VerifiedCandleSubscription,
    candle_subscription_payload,
)


T = 1_775_815_020_000_000


def candle(symbol, start, publish):
    return {
        "type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101,
        "v": 2, "res": "1m", "sy": symbol, "cst": start, "ts": publish,
    }


class TestVerifiedCandleSubscription(unittest.TestCase):
    def test_payload_is_documented_sorted_candle_channel(self):
        payload = candle_subscription_payload(["ETHUSDT", "BTCUSDT", "BTCUSDT"], "1m")
        self.assertEqual(payload["type"], "subscribe")
        self.assertEqual(payload["payload"]["channels"], [{
            "name": "candlestick_1m", "symbols": ["BTCUSDT", "ETHUSDT"],
        }])

    def test_only_matching_symbol_can_reach_its_callback(self):
        btc, eth = [], []
        subscription = VerifiedCandleSubscription("1m")
        subscription.subscribe("BTCUSDT", btc.append)
        subscription.subscribe("ETHUSDT", eth.append)
        subscription.ingest(candle("BTCUSDT", T, T + 1), receipt_timestamp=T + 2)
        subscription.ingest(candle("BTCUSDT", T + 60_000_000, T + 60_000_001), receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(btc), 1)
        self.assertEqual(eth, [])
        self.assertEqual(subscription.stats()["routed_frames"], 2)

    def test_control_unknown_and_malformed_frames_do_not_reach_adapter(self):
        received = []
        subscription = VerifiedCandleSubscription("1m")
        subscription.subscribe("BTCUSDT", received.append)
        subscription.ingest({"type": "subscribed"}, receipt_timestamp=T)
        subscription.ingest({"type": "candlestick_1m", "sy": "DOGEUSDT"}, receipt_timestamp=T)
        subscription.ingest("invalid", receipt_timestamp=T)
        stats = subscription.stats()
        self.assertEqual(received, [])
        self.assertEqual(stats["control_frames"], 1)
        self.assertEqual(stats["unowned_or_malformed_frames"], 1)
        self.assertEqual(stats["malformed_frames"], 1)

    def test_empty_subscription_has_no_payload(self):
        with self.assertRaises(ValueError):
            VerifiedCandleSubscription("1m").payload()


if __name__ == "__main__":
    unittest.main()
