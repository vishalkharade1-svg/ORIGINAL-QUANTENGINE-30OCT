"""Contract tests for genuine bounded Global Delta captures (2026-09-18).

Every fixture below is real public traffic from
``wss://public-socket.delta.exchange`` for ``BTCUSDT``.  Nothing is
fabricated.  The tests pin exactly what was observed — and explicitly what
was NOT (no rollover, sparse publication) — so no future change can
silently promote partial evidence into Global verification.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from data.delta.market_events import (
    InvalidMarketFrame,
    normalize_candlestick_frame,
    normalize_trade_frame,
)
from data.delta.verified_candle_subscription import (
    is_observed_subscription_snapshot,
)
from scripts.verify_delta_global_evidence import verify_single_session


FIXTURES = (
    Path(__file__).resolve().parents[1] / "data" / "fixtures" / "delta"
)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def data_frames(bundle: dict) -> list[dict]:
    return [r["frame"] for r in bundle["frames"]
            if r.get("classification") == "requested_public_data"]


def control_frames(bundle: dict) -> list[dict]:
    return [r["frame"] for r in bundle["frames"]
            if r.get("classification") == "control_or_unrequested"]


CANDLE_BUNDLES = [
    "observed_global_btcusdt_candles_20260918.json",
    "observed_global_btcusdt_candles_rollover_attempt_20260918.json",
    "observed_global_btcusdt_candle_rollover_timed_20260918.json",
    "observed_global_btcusdt_candles_long_20260918.json",
]

# The 150s silence bundle is genuine negative evidence: the channel was
# accepted (subscription echo present) yet delivered zero data frames.
SILENCE_BUNDLE = "observed_global_btcusdt_candle_silence_20260918.json"


class TestGlobalSubscriptionEcho(unittest.TestCase):
    def test_global_echo_is_recognized_for_btcusdt(self):
        bundle = load("observed_global_btcusdt_subscription_echo_20260918.json")
        self.assertEqual(bundle["endpoint"],
                         "wss://public-socket.delta.exchange")
        self.assertEqual(bundle["symbol"], "BTCUSDT")
        controls = control_frames(bundle)
        self.assertEqual(len(controls), 1)
        self.assertTrue(is_observed_subscription_snapshot(
            controls[0], symbols=["BTCUSDT"], resolution="1m"))
        # India BTCUSD must never satisfy the Global universe check.
        self.assertFalse(is_observed_subscription_snapshot(
            controls[0], symbols=["BTCUSD"], resolution="1m"))

    def test_global_reconnect_sessions_each_resubscribe(self):
        bundle = load("observed_global_btcusdt_client_reconnect_20260918.json")
        self.assertEqual(
            bundle["schema"],
            "quantengine.delta-public-reconnect-observation.v1")
        self.assertIn("client-initiated", bundle["limitations"][0])
        self.assertEqual(len(bundle["sessions"]), 2)
        for session in bundle["sessions"]:
            controls = control_frames(session)
            self.assertEqual(len(controls), 1)
            self.assertTrue(is_observed_subscription_snapshot(
                controls[0], symbols=["BTCUSDT"], resolution="1m"))


class TestGlobalCandleSchema(unittest.TestCase):
    def test_silence_bundle_is_accepted_but_empty(self):
        # Genuine negative evidence: channel accepted (echo present) yet
        # zero data frames in 150s.  Silent minutes are normal on this
        # endpoint, which is why continuity must fail closed on gaps.
        bundle = load(SILENCE_BUNDLE)
        self.assertEqual(len(control_frames(bundle)), 1)
        self.assertEqual(data_frames(bundle), [])

    def test_observed_candles_normalize_without_inference(self):
        for name in CANDLE_BUNDLES:
            with self.subTest(bundle=name):
                bundle = load(name)
                candles = [f for f in data_frames(bundle)
                           if f.get("type") == "candlestick_1m"]
                self.assertGreaterEqual(len(candles), 1)
                for frame in candles:
                    event = normalize_candlestick_frame(
                        frame, receipt_timestamp=frame["ts"],
                        venue="DELTA_GLOBAL")
                    self.assertEqual(event.provenance.instrument, "BTCUSDT")
                    self.assertEqual(event.resolution, "1m")
                    self.assertEqual(event.price_basis, "TRADED_PRICE")
                    self.assertIsNotNone(event.volume)
                    self.assertIsNotNone(event.candle_start_timestamp)
                    self.assertFalse(event.closed)
                    self.assertIsNone(event.provenance.sequence)

    def test_endpoint_sends_natural_duplicates(self):
        bundle = load("observed_global_btcusdt_candles_long_20260918.json")
        candles = [f for f in data_frames(bundle)
                   if f.get("type") == "candlestick_1m"]
        serialized = [json.dumps(f, sort_keys=True) for f in candles]
        self.assertGreater(len(serialized), len(set(serialized)))

    def test_no_single_capture_contains_a_rollover(self):
        for name in CANDLE_BUNDLES:
            with self.subTest(bundle=name):
                bundle = load(name)
                starts = list(dict.fromkeys(
                    f["cst"] for f in data_frames(bundle)
                    if f.get("type") == "candlestick_1m"))
                self.assertEqual(len(starts), 1,
                                 "a second distinct cst would be rollover "
                                 "evidence; none was observed")

    def test_distinct_csts_across_captures_are_gaps_not_rollovers(self):
        starts = set()
        for name in CANDLE_BUNDLES:
            for f in data_frames(load(name)):
                if f.get("type") == "candlestick_1m":
                    starts.add(f["cst"])
        self.assertGreater(len(starts), 1)
        ordered = sorted(starts)
        for earlier, later in zip(ordered, ordered[1:]):
            # Consecutive 1m candles are exactly 60_000_000 µs apart.
            # Every observed spacing is a multiple-minute gap instead.
            self.assertNotEqual(later - earlier, 60_000_000)

    def test_no_single_bundle_passes_the_full_global_bar(self):
        names = (CANDLE_BUNDLES + [SILENCE_BUNDLE] + [
            "observed_global_btcusdt_subscription_echo_20260918.json",
            "observed_global_btcusdt_trades_20260918.json",
        ])
        for name in names:
            with self.subTest(bundle=name):
                verdict = verify_single_session(load(name))
                self.assertFalse(
                    verdict.passed,
                    "partial Global evidence must never pass the full bar")


class TestGlobalTrades(unittest.TestCase):
    def test_observed_trades_preserve_role_without_aggressor(self):
        bundle = load("observed_global_btcusdt_trades_20260918.json")
        trades = [f for f in data_frames(bundle) if f.get("type") == "trades"]
        self.assertGreaterEqual(len(trades), 1)
        for frame in trades:
            event = normalize_trade_frame(
                frame, receipt_timestamp=frame["ts"], venue="DELTA_GLOBAL")
            self.assertEqual(event.provenance.instrument, "BTCUSDT")
            self.assertGreater(event.price, 0)
            self.assertGreater(event.quantity, 0)
            self.assertIn(event.maker_taker_role, ("maker", "taker"))
            self.assertIsNone(event.aggressor_side)
            self.assertIsNone(event.provenance.sequence)


class TestGlobalTickerIsReferenceOnly(unittest.TestCase):
    def test_ticker_shape_is_mark_price_not_ohlcv(self):
        bundle = load("observed_global_btcusdt_ticker_20260918.json")
        tickers = [f for f in data_frames(bundle) if f.get("type") == "ticker"]
        self.assertGreaterEqual(len(tickers), 1)
        for frame in tickers:
            self.assertEqual(frame["sy"], "BTCUSDT")
            self.assertIn("m", frame["d"][0])
            # The embedded daily-stats array is not a 1m candle and must
            # never normalize as one.
            with self.assertRaises(InvalidMarketFrame):
                normalize_candlestick_frame(
                    frame, receipt_timestamp=frame["ts"],
                    venue="DELTA_GLOBAL")


if __name__ == "__main__":
    unittest.main()
