"""
====================================================

QuantEngine

Phase 9P-j -- Delta WebSocket endpoint regression.

Phase 9P-j validation discovered a real defect: the live
PAPER runtime's WebSocket adapters pointed at the DELTA
INDIA public socket (wss://public-socket.india.delta.exchange),
which streams only India-denominated products (BTCUSD,
ETHUSD, HYPEUSD ...). The configured universe -- live GLOBAL
USDT-perpetuals (BTCUSDT, ETHUSDT, DOGEUSDT, XRPUSDT) --
received ZERO real-time ticker data on the India socket
(proven: 0 frames across all channels), so the runtime went
STALE and never produced candles, signals, or paper trades.

The fix points both WebSocket adapters at the Delta GLOBAL
public socket (wss://public-socket.delta.exchange), matching
the REST base already used by delta_rest.py (Global). Real
validation confirmed the Global socket streams the full
configured universe on `ticker` (21 frames across BTCUSDT /
ETHUSDT / DOGEUSDT / XRPUSDT in 25s) and the production
adapter now emits closed candles for every configured symbol.

These offline tests PIN the corrected endpoint so it cannot
silently regress to the India socket, and lock the parser to
the real Global ticker frame structure.

No network, no threads.
====================================================
"""

import unittest

from data.delta.delta_subscription_stream import DeltaSubscriptionStream
from data.delta.delta_subscription_stream import WS_URL

GLOBAL_PUBLIC_SOCKET = "wss://public-socket.delta.exchange"
INDIA_PUBLIC_SOCKET = "wss://public-socket.india.delta.exchange"


class TestGlobalEndpointRegression(unittest.TestCase):

    def module_source(self):
        import inspect
        import data.delta.delta_subscription_stream as mod
        return inspect.getsource(mod)

    def test_ws_url_is_global_public_socket(self):
        self.assertEqual(
            WS_URL,
            GLOBAL_PUBLIC_SOCKET,
            "Delta WS adapter must target the GLOBAL public socket so the "
            "configured USDT-perp universe receives real-time ticker data.",
        )

    def test_ws_url_is_not_india_public_socket(self):
        self.assertNotEqual(
            WS_URL,
            INDIA_PUBLIC_SOCKET,
            "India public socket streams only India products (BTCUSD/ETHUSD); "
            "it cannot feed the configured GLOBAL USDT-perp universe.",
        )

    def test_adapters_consistent_with_global_rest_base(self):
        import data.delta.delta_subscription_stream as stream_mod
        import data.websocket_client as ws_mod
        from core.exchanges.delta.delta_rest import DeltaREST

        self.assertTrue(stream_mod.WS_URL.startswith("wss://public-socket.delta.exchange"))
        self.assertTrue(ws_mod.WS_URL.startswith("wss://public-socket.delta.exchange"))
        self.assertIn("api.delta.exchange", DeltaREST.BASE_URL)
        self.assertNotIn("india", stream_mod.WS_URL)
        self.assertNotIn("india", ws_mod.WS_URL)

    def test_subscribe_payload_uses_ticker_channel_sorted_symbols(self):
        stream = DeltaSubscriptionStream()

        def cb(_candle):
            pass

        stream._handlers = {"ETHUSDT": (cb, cb), "BTCUSDT": (cb, cb)}
        payload = stream._subscribe_payload()

        self.assertEqual(payload["type"], "subscribe")
        channels = payload["payload"]["channels"]
        self.assertEqual(channels[0]["name"], "ticker")
        self.assertEqual(channels[0]["symbols"], ["BTCUSDT", "ETHUSDT"])

    def test_emit_ticker_parses_global_frame_and_rolls_closed_candle(self):
        stream = DeltaSubscriptionStream()

        closed = []

        def on_candle(candle):
            closed.append(candle)

        def on_down():
            pass

        stream._handlers = {"BTCUSDT": (on_candle, on_down)}

        frame = {
            "type": "ticker",
            "d": [
                {
                    "i": 139,
                    "s": "BTCUSDT",
                    "m": "81307.72730586",
                    "ohlc": [77229.0, 81710.0, 76950.5, 81329.5],
                }
            ],
            "ts": 1000000020 * 1_000_000,
        }

        stream._emit_ticker(frame)
        self.assertEqual(
            sum(1 for c in closed if c.closed), 0,
            "first tick in a fresh bucket must not emit a closed candle",
        )

        frame["d"][0]["m"] = "81400.0"
        frame["ts"] = 1000000080 * 1_000_000

        stream._emit_ticker(frame)
        self.assertEqual(
            sum(1 for c in closed if c.closed), 1,
            "boundary roll must emit exactly one closed candle",
        )
        candle = closed[-1]
        self.assertTrue(candle.closed)
        self.assertEqual(candle.symbol, "BTCUSDT")
        self.assertEqual(candle.timestamp, 1000000020)


if __name__ == "__main__":
    unittest.main()
