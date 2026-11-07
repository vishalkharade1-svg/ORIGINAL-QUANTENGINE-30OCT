"""Verified market-data gap recovery stays fail-closed and non-retroactive."""

import json
import tempfile
import unittest
from pathlib import Path

from data.delta.verified_socket_transport import GLOBAL_PUBLIC_SOCKET, VerifiedSocketTransport
from core.history.candle import Candle
from core.exchanges.delta.delta_history import DeltaHistory

T = 1_775_814_840


class FakeSocket:
    def send(self, payload):
        self.payload = payload

    def close(self):
        pass


def bundle():
    def candle(cst, ts):
        return {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
                "c": 100, "v": 5, "res": "1m", "sy": "BTCUSDT",
                "ts": ts, "cst": cst}
    base = T * 1_000_000
    trade = {"type": "trades", "p": "100", "s": "1", "r": "t",
             "sy": "BTCUSDT", "t": base, "ts": base + 500_000}
    echo = {"type": "subscriptions",
            "channels": [{"name": "candlestick_1m", "symbols": ["BTCUSDT"]}]}
    return {
        "schema": "quantengine.delta-public-capture.v1",
        "endpoint": GLOBAL_PUBLIC_SOCKET,
        "symbol": "BTCUSDT",
        "started_unix": float(T),
        "timeout_seconds": 130.0,
        "max_frames": 500,
        "requested_channels": ["trades", "candlestick_1m"],
        "include_control_frames": True,
        "frames": [
            {"receipt_ordinal": 1, "receipt_unix_ns": base, "frame": trade,
             "classification": "requested_public_data"},
            {"receipt_ordinal": 2, "receipt_unix_ns": base, "frame": candle(base, base + 1_000_000),
             "classification": "requested_public_data"},
            {"receipt_ordinal": 3, "receipt_unix_ns": base, "frame": candle(base + 60_000_000, base + 61_000_000),
             "classification": "requested_public_data"},
            {"receipt_ordinal": 4, "receipt_unix_ns": base, "frame": candle(base + 120_000_000, base + 121_000_000),
             "classification": "requested_public_data"},
            {"receipt_ordinal": 5, "receipt_unix_ns": base, "frame": echo,
             "classification": "control_or_unrequested"},
        ],
        "limitations": [],
    }



class TestVerifiedGapRecovery(unittest.TestCase):
    def _transport(self, fetcher=None):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        handle.write(json.dumps(bundle()))
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        delivered = []
        transport = VerifiedSocketTransport(
            ["BTCUSDT"], delivered.append, evidence_bundle=handle.name,
            socket_factory=lambda endpoint: FakeSocket(), history_fetcher=fetcher,
        )
        transport.connect()
        return transport, delivered

    @staticmethod
    def candle(cst):
        return Candle(timestamp=cst, open=100, high=101, low=99, close=100, volume=5)

    def test_gap_blocks_then_verified_backfill_restores_continuity(self):
        calls = []
        def fetcher(symbol, resolution, after, before):
            calls.append((symbol, resolution, after, before))
            return [self.candle(T + 60), self.candle(T + 120)]

        transport, delivered = self._transport(fetcher)
        first = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100,
                 "v": 5, "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1}
        jumped = dict(first, cst=T + 180, ts=T + 181)
        self.assertFalse(transport.ingest(first, receipt_timestamp=T + 2)["delivered"])
        blocked = transport.ingest(jumped, receipt_timestamp=T + 182)
        self.assertFalse(blocked["delivered"])
        report = transport.repair_gaps("BTCUSDT")
        self.assertEqual(report["status"], "CONTINUOUS")
        self.assertEqual(report["candles_repaired"], 2)
        self.assertEqual(calls, [("BTCUSDT", "1m", T, T + 180)])

        next_frame = dict(first, cst=T + 240, ts=T + 241, c=102, h=102)
        accepted = transport.ingest(next_frame, receipt_timestamp=T + 242)
        self.assertTrue(accepted["delivered"])
        self.assertEqual(len(delivered), 1)

    def test_partial_or_missing_history_keeps_strategy_blocked(self):
        transport, delivered = self._transport(
            lambda symbol, resolution, after, before: [self.candle(T + 60)]
        )
        first = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100,
                 "v": 5, "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1}
        jumped = dict(first, cst=T + 180, ts=T + 181)
        transport.ingest(first, receipt_timestamp=T + 2)
        transport.ingest(jumped, receipt_timestamp=T + 182)
        report = transport.repair_gaps("BTCUSDT")
        self.assertEqual(report["status"], "DATA_GAP_UNREPAIRED")
        self.assertEqual(delivered, [])
        later = dict(first, cst=T + 240, ts=T + 241)
        self.assertFalse(transport.ingest(later, receipt_timestamp=T + 242)["delivered"])

    def test_delta_history_adapter_uses_strict_gap_bounds(self):
        history = DeltaHistory()
        calls = []
        def fake_get(endpoint, params=None, headers=None):
            calls.append((endpoint, dict(params or {})))
            return {"result": [
                {"time": T + 60, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 5},
                {"time": T + 120, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 5},
            ]}
        history.rest.get = fake_get
        candles = history.gap_candles("BTCUSDT", "1m", T, T + 180)
        self.assertEqual([c.timestamp for c in candles], [T + 60, T + 120])
        self.assertEqual(calls[0][0], "/v2/history/candles")
        self.assertEqual(calls[0][1]["start"], T + 60)
        self.assertEqual(calls[0][1]["end"], T + 120)

    def test_no_history_adapter_is_fail_closed(self):
        transport, delivered = self._transport()
        first = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99, "c": 100,
                 "v": 5, "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1}
        jumped = dict(first, cst=T + 180, ts=T + 181)
        transport.ingest(first, receipt_timestamp=T + 2)
        transport.ingest(jumped, receipt_timestamp=T + 182)
        report = transport.repair_gaps("BTCUSDT")
        self.assertEqual(report["status"], "DATA_GAP_UNREPAIRED")
        self.assertEqual(delivered, [])


if __name__ == "__main__":
    unittest.main()
