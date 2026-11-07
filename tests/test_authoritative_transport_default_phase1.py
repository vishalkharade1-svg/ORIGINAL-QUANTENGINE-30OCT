"""The runtime default must not route synthetic ticker marks as OHLCV."""

import unittest

from data.realtime.subscription_manager import default_transport_factory


class TestAuthoritativeTransportDefault(unittest.TestCase):
    def test_default_transport_refuses_legacy_ticker_derived_candles(self):
        transport = default_transport_factory()
        with self.assertRaisesRegex(RuntimeError, "authoritative traded-candle transport"):
            transport.subscribe("BTCUSDT", lambda candle: None, lambda: None)

    def test_fail_closed_transport_is_safe_to_stop_or_unsubscribe(self):
        transport = default_transport_factory()
        transport.unsubscribe("BTCUSDT")
        self.assertIsNone(transport.close())


if __name__ == "__main__":
    unittest.main()
