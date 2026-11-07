"""Phase-3 data-quality gates: every strategy path rejects bad input (offline).

Each test drives the verified chain (normalizer → stream → session gate →
bridge → dispatch) with synthetic frames and proves fail-closed behavior:
no mark-only, volume-less, forming, stale, gapped, badly-timestamped,
duplicate, out-of-order, un-resynchronized, or capability-insufficient input
ever reaches the strategy callback.

All frames are synthetic gate-logic fixtures, never exchange evidence.
"""

import json
import tempfile
import unittest
from pathlib import Path

from core.common.timestamp import normalize_timestamp
from core.history.candle import Candle
from data.delta.market_events import (
    InvalidMarketFrame,
    normalize_candlestick_frame,
)
from data.delta.verified_socket_transport import (
    GLOBAL_PUBLIC_SOCKET,
    VerifiedSocketTransport,
)
from data.delta.verified_strategy_dispatch import VerifiedStrategyDispatcher


T = 1_775_814_834_000_000


class FakeSocket:
    def send(self, payload):
        pass

    def close(self):
        pass


def _bundle():
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


def _evidence_path(test_case):
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    try:
        tmp.write(json.dumps(_bundle()))
        tmp.flush()
        path = tmp.name
    finally:
        tmp.close()
    test_case.addCleanup(Path(path).unlink, True)
    return path


def _connected_transport(test_case, delivered):
    transport = VerifiedSocketTransport(
        ["BTCUSDT"], delivered.append,
        evidence_bundle=_evidence_path(test_case),
        socket_factory=lambda endpoint: FakeSocket())
    transport.connect()
    return transport


def _candle(cst, ts, **overrides):
    frame = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
             "c": 100, "v": 5, "res": "1m", "sy": "BTCUSDT",
             "ts": ts, "cst": cst}
    frame.update(overrides)
    return frame


class TestVerifiedDataQualityGates(unittest.TestCase):
    def test_mark_only_candles_never_reach_strategy(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        transport.ingest(
            _candle(T, T + 1_000_000, sy="MARK:BTCUSDT"),
            receipt_timestamp=T + 1_000_001)
        # MARK: symbol is not a subscribed symbol and, even if routed,
        # the bridge refuses mark-price basis.  Nothing is delivered.
        result = transport.ingest(
            _candle(T + 60_000_000, T + 60_000_001, sy="MARK:BTCUSDT"),
            receipt_timestamp=T + 60_000_002)
        self.assertFalse(result["delivered"])
        self.assertEqual(delivered, [])

    def test_volume_less_candles_never_reach_strategy(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        novol = _candle(T, T + 1_000_000)
        del novol["v"]
        transport.ingest(novol, receipt_timestamp=T + 1_000_001)
        novol_next = _candle(T + 60_000_000, T + 60_000_001)
        del novol_next["v"]
        result = transport.ingest(novol_next, receipt_timestamp=T + 60_000_002)
        self.assertFalse(result["delivered"])
        self.assertEqual(delivered, [])

    def test_forming_candles_never_reach_strategy(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        first = transport.ingest(
            _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        update = transport.ingest(
            _candle(T, T + 2_000_000), receipt_timestamp=T + 2_000_001)
        self.assertFalse(first["delivered"])
        self.assertFalse(update["delivered"])
        self.assertEqual(delivered, [])

    def test_stale_state_rejects_even_closed_candles(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        transport.ingest(
            _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        transport.ingest(
            _candle(T + 60_000_000, T + 60_000_001),
            receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(delivered), 1)
        adapter = transport.subscription._adapters["BTCUSDT"]
        stale_state = adapter.stream.store.snapshot(
            transport.venue, "BTCUSDT",
            now=(T + 60_000_002) // 1_000_000 + 3600,
            stale_after_seconds=30)
        self.assertTrue(stale_state.data_quality.stale)
        dispatcher = VerifiedStrategyDispatcher(lambda candle: delivered.append(candle))
        decision = dispatcher.dispatch(delivered[0], stale_state)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "MARKET_DATA_STALE")
        self.assertEqual(len(delivered), 1)

    def test_gapped_series_never_reaches_strategy(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        transport.ingest(
            _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        jumped = transport.ingest(
            _candle(T + 180_000_000, T + 180_000_001),
            receipt_timestamp=T + 180_000_002)
        self.assertFalse(jumped["delivered"])
        self.assertEqual(delivered, [])

    def test_invalid_timestamps_are_rejected_not_defaulted(self):
        with self.assertRaises(InvalidMarketFrame):
            normalize_candlestick_frame(
                _candle(T, 0), receipt_timestamp=T + 1)
        with self.assertRaises(InvalidMarketFrame):
            normalize_candlestick_frame(
                _candle(T, None), receipt_timestamp=T + 1)
        with self.assertRaises(InvalidMarketFrame):
            normalize_candlestick_frame(
                _candle(T, T + 1), receipt_timestamp="not-a-time")

    def test_timestamp_units_normalize_without_confusion(self):
        second = 1_775_814_834
        self.assertEqual(normalize_timestamp(second), second)
        self.assertEqual(normalize_timestamp(second * 1_000), second)
        self.assertEqual(normalize_timestamp(second * 1_000_000), second)
        self.assertEqual(
            normalize_timestamp(second * 1_000_000_000), second)
        for bad in (0, -5, None, "abc", float("nan")):
            with self.assertRaises(ValueError):
                normalize_timestamp(bad)

    def test_duplicate_updates_deliver_exactly_once(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        frame = _candle(T, T + 1_000_000)
        transport.ingest(dict(frame), receipt_timestamp=T + 1_000_001)
        transport.ingest(dict(frame), receipt_timestamp=T + 1_000_002)
        transport.ingest(
            _candle(T + 60_000_000, T + 60_000_001),
            receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(delivered), 1)

    def test_out_of_order_events_never_rewrite_history(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        transport.ingest(
            _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        transport.ingest(
            _candle(T + 60_000_000, T + 60_000_001),
            receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(delivered), 1)
        late = transport.ingest(
            _candle(T + 30_000_000, T + 90_000_001),
            receipt_timestamp=T + 90_000_002)
        self.assertFalse(late["delivered"])
        self.assertEqual(len(delivered), 1)

    def test_failed_resynchronization_blocks_delivery(self):
        delivered = []
        transport = _connected_transport(self, delivered)
        transport.ingest(
            _candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        transport.ingest(
            _candle(T + 60_000_000, T + 60_000_001),
            receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(delivered), 1)
        transport.close()
        dropped = transport.ingest(
            _candle(T + 120_000_000, T + 120_000_001),
            receipt_timestamp=T + 120_000_002)
        self.assertFalse(dropped["delivered"])
        self.assertEqual(dropped["reason"], "transport is not connected")
        self.assertEqual(len(delivered), 1)

    def test_capability_insufficient_state_rejects_dispatch(self):
        delivered = []
        dispatcher = VerifiedStrategyDispatcher(delivered.append)
        decision = dispatcher.dispatch(
            Candle(timestamp=1_775_814_834, open=100.0, high=101.0,
                   low=99.0, close=100.0, volume=5.0, closed=True,
                   symbol="BTCUSDT"),
            None)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "MARKET_DATA_UNAVAILABLE")
        self.assertEqual(delivered, [])


if __name__ == "__main__":
    unittest.main()
