"""Phase-1 Global evidence gate tests (deterministic, offline).

All bundles below are SYNTHETIC verifier fixtures built in-test to prove
the gate logic.  They are not exchange captures and must never be presented
as Global verification.  Real Global verification requires a bounded capture
from ``wss://public-socket.delta.exchange`` for ``BTCUSDT`` that passes
``scripts/verify_delta_global_evidence.py``.
"""

import json
import unittest

from scripts.verify_delta_global_evidence import (
    GLOBAL_PUBLIC_SOCKET,
    verify_reconnect_observation,
    verify_single_session,
)


T = 1_775_814_834_000_000


def _record(frame, classification="requested_public_data", ordinal=1):
    return {
        "receipt_ordinal": ordinal,
        "receipt_unix_ns": T,
        "frame": frame,
        "classification": classification,
    }


def _synthetic_global_bundle(*, with_control=True, with_trades=True,
                             with_rollover=True):
    candle_one = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
                  "c": 100, "v": 5, "res": "1m", "sy": "BTCUSDT",
                  "ts": T + 1_000_000, "cst": T}
    candle_two = dict(candle_one, h=102, c=101, v=7, ts=T + 2_000_000)
    frames = [_record(candle_one, ordinal=1), _record(candle_two, ordinal=2)]
    if with_rollover:
        candle_next = dict(candle_one, cst=T + 60_000_000,
                           ts=T + 60_000_001, c=103, h=103, v=9)
        frames.append(_record(candle_next, ordinal=3))
    if with_trades:
        trade = {"type": "trades", "p": "100", "s": "2", "r": "t",
                 "sy": "BTCUSDT", "t": T, "ts": T + 500_000}
        frames.insert(0, _record(trade, ordinal=0))
        for index, record in enumerate(frames):
            record["receipt_ordinal"] = index + 1
    if with_control:
        echo = {"type": "subscriptions",
                "channels": [{"name": "candlestick_1m",
                              "symbols": ["BTCUSDT"]}]}
        frames.append(_record(echo, classification="control_or_unrequested",
                              ordinal=len(frames) + 1))
    return {
        "schema": "quantengine.delta-public-capture.v1",
        "endpoint": GLOBAL_PUBLIC_SOCKET,
        "symbol": "BTCUSDT",
        "started_unix": 1_775_814_834.0,
        "timeout_seconds": 130.0,
        "max_frames": 500,
        "requested_channels": ["trades", "candlestick_1m"],
        "include_control_frames": with_control,
        "frames": frames,
        "limitations": [],
    }


class TestGlobalEvidenceGate(unittest.TestCase):
    def test_synthetic_global_bundle_passes_verifier_shape(self):
        verdict = verify_single_session(_synthetic_global_bundle())
        self.assertTrue(verdict.passed, [c.detail for c in verdict.failures()])

    def test_india_endpoint_never_counts_as_global_evidence(self):
        bundle = _synthetic_global_bundle()
        bundle["endpoint"] = "wss://public-socket.india.delta.exchange"
        bundle["symbol"] = "BTCUSD"
        verdict = verify_single_session(bundle)
        self.assertFalse(verdict.passed)
        names = [c.name for c in verdict.failures()]
        self.assertIn("global_endpoint", names)
        self.assertIn("global_symbol_in_universe", names)

    def test_btcusd_symbol_never_counts_as_global_btcusdt(self):
        bundle = _synthetic_global_bundle()
        bundle["symbol"] = "BTCUSD"
        for record in bundle["frames"]:
            if record["frame"].get("sy") == "BTCUSDT":
                record["frame"] = dict(record["frame"], sy="BTCUSD")
        verdict = verify_single_session(bundle)
        self.assertFalse(verdict.passed)

    def test_missing_trades_fails_closed(self):
        verdict = verify_single_session(
            _synthetic_global_bundle(with_trades=False))
        self.assertFalse(verdict.passed)
        self.assertIn("trades_present",
                      [c.name for c in verdict.failures()])

    def test_missing_rollover_fails_closed(self):
        verdict = verify_single_session(
            _synthetic_global_bundle(with_rollover=False))
        self.assertFalse(verdict.passed)
        self.assertIn("candle_rollover",
                      [c.name for c in verdict.failures()])

    def test_missing_control_frames_fails_acknowledgement(self):
        verdict = verify_single_session(
            _synthetic_global_bundle(with_control=False))
        self.assertFalse(verdict.passed)
        self.assertIn("subscription_acknowledgement",
                      [c.name for c in verdict.failures()])

    def test_reconnect_observation_requires_two_subscribed_sessions(self):
        bundle = {
            "schema": "quantengine.delta-public-reconnect-observation.v1",
            "endpoint": GLOBAL_PUBLIC_SOCKET,
            "symbol": "BTCUSDT",
            "requested_channels": ["candlestick_1m"],
            "sessions": [_synthetic_global_bundle(),
                         _synthetic_global_bundle()],
            "limitations": [],
        }
        verdict = verify_reconnect_observation(bundle)
        self.assertTrue(verdict.passed)
        single = dict(bundle, sessions=[_synthetic_global_bundle()])
        self.assertFalse(verify_reconnect_observation(single).passed)

    def test_default_paper_transport_remains_fail_closed(self):
        from data.realtime.subscription_manager import default_transport_factory
        transport = default_transport_factory()
        with self.assertRaisesRegex(RuntimeError,
                                    "authoritative traded-candle transport"):
            transport.subscribe("BTCUSDT", lambda c: None, lambda: None)

    def test_legacy_websocket_client_defaults_to_reference_only(self):
        import inspect
        import data.websocket_client as ws_mod
        params = inspect.signature(ws_mod.start).parameters
        self.assertIn("publish_candles", params)
        self.assertFalse(params["publish_candles"].default)


if __name__ == "__main__":
    unittest.main()
