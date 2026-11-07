"""Contract tests for a bounded, credential-free observed Delta India capture.

This fixture is evidence of public frame shape and rollover only.  It is not a
recording of a complete candle and must not be used to validate candle-volume
conservation or to authorize live runtime wiring.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from data.delta.candle_finality import CandleFinalityTracker
from data.delta.market_events import normalize_candlestick_frame, normalize_trade_frame
from data.delta.verified_candle_subscription import is_observed_subscription_snapshot


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "data" / "fixtures" / "delta"
    / "observed_india_btcusd_trades_candles_rollover_20260916.json"
)


def observed_frames() -> list[dict]:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert bundle["schema"] == "quantengine.delta-public-capture.v1"
    assert bundle["endpoint"] == "wss://public-socket.india.delta.exchange"
    return [record["frame"] for record in bundle["frames"]]


class TestObservedIndiaPublicFixture(unittest.TestCase):
    def test_observed_trade_and_candle_envelopes_normalize_without_inference(self):
        frames = observed_frames()
        trades = [frame for frame in frames if frame.get("type") == "trades"]
        candles = [frame for frame in frames if frame.get("type") == "candlestick_1m"]
        self.assertGreaterEqual(len(trades), 1)
        self.assertGreaterEqual(len(candles), 2)
        for frame in trades:
            event = normalize_trade_frame(frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA")
            self.assertEqual(event.provenance.instrument, "BTCUSD")
            self.assertIsNone(event.provenance.sequence)
            self.assertIsNone(event.aggressor_side)
        for frame in candles:
            event = normalize_candlestick_frame(frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA")
            self.assertEqual(event.resolution, "1m")
            self.assertEqual(event.price_basis, "TRADED_PRICE")
            self.assertIsNotNone(event.volume)
            self.assertIsNotNone(event.candle_start_timestamp)
            self.assertFalse(event.closed)
            self.assertIsNone(event.provenance.sequence)

    def test_observed_later_candle_start_causally_finalizes_previous_update(self):
        tracker = CandleFinalityTracker()
        closed = []
        starts = []
        for frame in observed_frames():
            if frame.get("type") != "candlestick_1m":
                continue
            event = normalize_candlestick_frame(frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA")
            starts.append(event.candle_start_timestamp)
            result = tracker.ingest(event)
            if result is not None:
                closed.append(result)
        distinct_starts = list(dict.fromkeys(starts))
        self.assertGreaterEqual(len(distinct_starts), 2)
        self.assertEqual(distinct_starts[1] - distinct_starts[0], 60)
        self.assertEqual(len(closed), 1)
        self.assertTrue(closed[0].closed)
        self.assertEqual(closed[0].candle_start_timestamp, distinct_starts[0])

    def test_fixture_does_not_claim_volume_conservation_or_provider_finality(self):
        bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertIn("No candle frame is considered closed", bundle["limitations"][1])
        self.assertTrue(all("sequence" not in record["frame"] for record in bundle["frames"]))

    def test_observed_control_echo_is_recognized_but_not_treated_as_finality(self):
        control_fixture = (
            FIXTURE.parent / "observed_india_btcusd_candle_control_20260916.json"
        )
        bundle = json.loads(control_fixture.read_text(encoding="utf-8"))
        controls = [
            record["frame"] for record in bundle["frames"]
            if record.get("classification") == "control_or_unrequested"
        ]
        self.assertEqual(len(controls), 1)
        self.assertTrue(is_observed_subscription_snapshot(
            controls[0], symbols=["BTCUSD"], resolution="1m",
        ))
        self.assertFalse(is_observed_subscription_snapshot(
            controls[0], symbols=["BTCUSDT"], resolution="1m",
        ))

    def test_client_reconnect_fixture_requires_each_session_to_resubscribe(self):
        reconnect_fixture = (
            FIXTURE.parent / "observed_india_btcusd_client_reconnect_20260916.json"
        )
        bundle = json.loads(reconnect_fixture.read_text(encoding="utf-8"))
        self.assertEqual(bundle["schema"], "quantengine.delta-public-reconnect-observation.v1")
        self.assertIn("client-initiated", bundle["limitations"][0])
        self.assertEqual(len(bundle["sessions"]), 2)
        for session in bundle["sessions"]:
            controls = [
                record["frame"] for record in session["frames"]
                if record.get("classification") == "control_or_unrequested"
            ]
            self.assertEqual(len(controls), 1)
            self.assertTrue(is_observed_subscription_snapshot(
                controls[0], symbols=["BTCUSD"], resolution="1m",
            ))

    def test_client_reconnect_fixture_contains_a_duplicate_candle_update(self):
        reconnect_fixture = (
            FIXTURE.parent / "observed_india_btcusd_client_reconnect_20260916.json"
        )
        bundle = json.loads(reconnect_fixture.read_text(encoding="utf-8"))
        first_session_candles = [
            record["frame"] for record in bundle["sessions"][0]["frames"]
            if record["frame"].get("type") == "candlestick_1m"
        ]
        serialized = [json.dumps(frame, sort_keys=True) for frame in first_session_candles]
        self.assertGreater(len(serialized), len(set(serialized)))


if __name__ == "__main__":
    unittest.main()
