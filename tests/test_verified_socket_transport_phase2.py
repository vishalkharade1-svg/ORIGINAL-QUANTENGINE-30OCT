"""Phase-2 verified socket transport tests (deterministic, offline).

The transport is exercised with a fake socket and synthetic frames only.
No test here opens a network connection or claims Global verification.
"""

import json
import tempfile
import unittest
from pathlib import Path

from data.delta.verified_socket_transport import (
    GLOBAL_PUBLIC_SOCKET,
    GlobalEvidenceMissing,
    VerifiedSocketTransport,
)


T = 1_775_814_834_000_000


class FakeSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    def send(self, payload):
        self.sent.append(payload)

    def close(self):
        self.closed = True


def _synthetic_verified_bundle():
    candle_one = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
                  "c": 100, "v": 5, "res": "1m", "sy": "BTCUSDT",
                  "ts": T + 1_000_000, "cst": T}
    candle_two = dict(candle_one, h=102, c=101, v=7, ts=T + 2_000_000)
    candle_next = dict(candle_one, cst=T + 60_000_000,
                       ts=T + 60_000_001, c=103, h=103, v=9)
    trade = {"type": "trades", "p": "100", "s": "2", "r": "t",
             "sy": "BTCUSDT", "t": T, "ts": T + 500_000}
    echo = {"type": "subscriptions",
            "channels": [{"name": "candlestick_1m", "symbols": ["BTCUSDT"]}]}
    frames = [
        {"receipt_ordinal": 1, "receipt_unix_ns": T, "frame": trade,
         "classification": "requested_public_data"},
        {"receipt_ordinal": 2, "receipt_unix_ns": T, "frame": candle_one,
         "classification": "requested_public_data"},
        {"receipt_ordinal": 3, "receipt_unix_ns": T, "frame": candle_two,
         "classification": "requested_public_data"},
        {"receipt_ordinal": 4, "receipt_unix_ns": T, "frame": candle_next,
         "classification": "requested_public_data"},
        {"receipt_ordinal": 5, "receipt_unix_ns": T, "frame": echo,
         "classification": "control_or_unrequested"},
    ]
    return {
        "schema": "quantengine.delta-public-capture.v1",
        "endpoint": GLOBAL_PUBLIC_SOCKET,
        "symbol": "BTCUSDT",
        "started_unix": 1_775_814_834.0,
        "timeout_seconds": 130.0,
        "max_frames": 500,
        "requested_channels": ["trades", "candlestick_1m"],
        "include_control_frames": True,
        "frames": frames,
        "limitations": [],
    }


def _write_bundle(bundle):
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    try:
        tmp.write(json.dumps(bundle))
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def _candle(cst, ts, *, symbol="BTCUSDT", volume=5, extra=None):
    frame = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
             "c": 100, "v": volume, "res": "1m", "sy": symbol,
             "ts": ts, "cst": cst}
    if extra:
        frame.update(extra)
    return frame


class TestVerifiedSocketTransport(unittest.TestCase):
    def test_connect_refuses_without_evidence(self):
        delivered = []
        transport = VerifiedSocketTransport(
            ["BTCUSDT"], delivered.append,
            socket_factory=lambda endpoint: FakeSocket(),
            evidence_bundle="/nonexistent/global-bundle.json",
        )
        with self.assertRaises(GlobalEvidenceMissing):
            transport.connect()
        self.assertFalse(transport.connected)

    def test_connect_refuses_wrong_endpoint(self):
        delivered = []
        with self.assertRaises(ValueError):
            VerifiedSocketTransport(
                ["BTCUSDT"], delivered.append,
                endpoint="wss://public-socket.india.delta.exchange",
                socket_factory=lambda endpoint: FakeSocket(),
            )

    def test_verified_delivery_requires_post_connect_rollover(self):
        path = _write_bundle(_synthetic_verified_bundle())
        try:
            delivered = []
            factory_sockets: list[FakeSocket] = []

            def factory(endpoint):
                sock = FakeSocket()
                factory_sockets.append(sock)
                return sock

            transport = VerifiedSocketTransport(
                ["BTCUSDT"], delivered.append, evidence_bundle=path,
                socket_factory=factory)
            transport.connect()
            self.assertTrue(transport.connected)
            payload = json.loads(factory_sockets[0].sent[0])
            names = [c["name"] for c in payload["payload"]["channels"]]
            self.assertIn("candlestick_1m", names)
            self.assertIn("trades", names)

            # First forming update: gated, never delivered.
            first = transport.ingest(
                _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
            self.assertFalse(first["delivered"])
            self.assertEqual(delivered, [])

            # Same-candle update: still gated, still nothing delivered.
            second = transport.ingest(
                _candle(T, T + 2_000_000), receipt_timestamp=T + 2_000_001)
            self.assertFalse(second["delivered"])
            self.assertEqual(delivered, [])

            # Continuous rollover: exactly one closed candle delivered.
            third = transport.ingest(
                _candle(T + 60_000_000, T + 60_000_001),
                receipt_timestamp=T + 60_000_002)
            self.assertTrue(third["delivered"], third)
            self.assertEqual(len(delivered), 1)
            self.assertTrue(delivered[0].closed)
            self.assertEqual(delivered[0].symbol, "BTCUSDT")
            self.assertIsNotNone(delivered[0].volume)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_mark_price_and_volume_less_candles_never_delivered(self):
        path = _write_bundle(_synthetic_verified_bundle())
        try:
            delivered = []
            transport = VerifiedSocketTransport(
                ["BTCUSDT"], delivered.append, evidence_bundle=path,
                socket_factory=lambda endpoint: FakeSocket())
            transport.connect()
            transport.ingest(
                _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
            # MARK-price rollover must not deliver traded OHLCV.
            mark = transport.ingest(
                _candle(T + 60_000_000, T + 60_000_001,
                        symbol="MARK:BTCUSDT"),
                receipt_timestamp=T + 60_000_002)
            # Unowned symbol (MARK:BTCUSDT not subscribed) is dropped.
            self.assertFalse(mark["delivered"])
            self.assertEqual(delivered, [])
        finally:
            Path(path).unlink(missing_ok=True)

    def test_disconnect_revokes_delivery_until_new_resync(self):
        path = _write_bundle(_synthetic_verified_bundle())
        try:
            delivered = []
            transport = VerifiedSocketTransport(
                ["BTCUSDT"], delivered.append, evidence_bundle=path,
                socket_factory=lambda endpoint: FakeSocket())
            transport.connect()
            transport.ingest(
                _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
            transport.ingest(
                _candle(T + 60_000_000, T + 60_000_001),
                receipt_timestamp=T + 60_000_002)
            self.assertEqual(len(delivered), 1)
            transport.close()
            self.assertFalse(transport.connected)
            dropped = transport.ingest(
                _candle(T + 120_000_000, T + 120_000_001),
                receipt_timestamp=T + 120_000_002)
            self.assertFalse(dropped["delivered"])
            self.assertEqual(len(delivered), 1)
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
