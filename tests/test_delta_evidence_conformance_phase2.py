"""Phase-2 evidence conformance tests (deterministic, offline).

Provenance key:
* FRESH_CAPTURE: bounded credential-free captures taken 2026-09-20
  (India 29-frame success persisted as `..._20260920_b.json`; Global 150s
  silence observed but not persisted — a silence fixture already exists).
* EXISTING_GENUINE_FIXTURE: committed India/Global captures.
* TEST_ONLY: in-test synthetic derivations, never exchange evidence.

Nothing here wires production, alters gates, or synthesizes market data.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.history.candle import Candle
from data.delta.candle_session_gate import CandleSessionGate
from data.delta.india_fixture_harness import (
    classify_india_evidence,
    hash_fixture,
    has_india_rollover,
    serialize_fixture,
)
from data.delta.market_events import (
    InvalidMarketFrame,
    normalize_candlestick_frame,
)
from data.delta.public_event_stream import DeltaPublicEventStream
from data.delta.runtime_candle_bridge import to_runtime_candle
from data.delta.verified_strategy_dispatch import VerifiedStrategyDispatcher


FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "delta"
INDIA_A = FIXTURES / "observed_india_btcusd_advisory_redacted_20260920.json"
INDIA_B = FIXTURES / "observed_india_btcusd_advisory_redacted_20260920_b.json"
INDIA_ROLLOVER = FIXTURES / "observed_india_btcusd_trades_candles_rollover_20260916.json"
GLOBAL_TICKER = FIXTURES / "observed_global_btcusdt_ticker_20260918.json"
GLOBAL_SILENCE = FIXTURES / "observed_global_btcusdt_candle_silence_20260918.json"
GLOBAL_RECONNECT = FIXTURES / "observed_global_btcusdt_client_reconnect_20260918.json"


def load(name: Path) -> dict:
    return json.loads(name.read_text(encoding="utf-8"))


def data_frames(bundle: dict) -> list[dict]:
    # Legacy 20260916 genuine captures carry no per-record classification
    # (all data); redacted advisory fixtures mark control records
    # explicitly.  Exclude only explicit control records in both cases.
    return [
        record["frame"]
        for record in bundle.get("frames", [])
        if isinstance(record.get("frame"), dict)
        and record.get("classification") != "control_or_unrequested"
    ]


class TestTickerParityIsSchemaOnly(unittest.TestCase):
    """India and Global tickers share a reference shape; not a venue contract."""

    def test_india_ticker_has_global_documented_shape(self):
        india = [f for f in data_frames(load(INDIA_A)) if f.get("type") == "ticker"]
        glob = [f for f in data_frames(load(GLOBAL_TICKER)) if f.get("type") == "ticker"]
        self.assertGreaterEqual(len(india), 1)
        self.assertGreaterEqual(len(glob), 1)
        for frame in india + glob:
            self.assertIn("m", frame["d"][0])  # mark price
            self.assertIn("ohlc", frame["d"][0])  # daily stats, NOT 1m OHLCV
            self.assertIn("ts", frame)
            with self.assertRaises(InvalidMarketFrame):
                normalize_candlestick_frame(
                    frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA"
                )

    def test_ticker_daily_stats_are_not_candles(self):
        for frame in data_frames(load(INDIA_B)):
            if frame.get("type") != "ticker":
                continue
            daily = frame["d"][0]["ohlc"]
            self.assertEqual(len(daily), 4)
            # Daily open is far from the current 1m candle open: confusing
            # the two would corrupt strategy state.
            candles = [
                f for f in data_frames(load(INDIA_B))
                if f.get("type") == "candlestick_1m"
            ]
            self.assertNotEqual(daily[0], candles[0]["o"])


class TestEventStreamConformance(unittest.TestCase):
    def test_genuine_india_frames_apply_without_inference(self):
        stream = DeltaPublicEventStream(venue="DELTA_INDIA")
        bundle = load(INDIA_A)
        applied = duplicates = 0
        for frame in data_frames(bundle):
            if frame.get("type") == "ticker":
                continue  # ticker has no normalized event by design
            result = stream.ingest(frame, receipt_timestamp=frame["ts"])
            if result.status == "APPLIED":
                applied += 1
            elif result.status == "DUPLICATE_OR_OLD":
                duplicates += 1
            else:
                self.fail("genuine frame %r: %s" % (frame.get("type"), result.reason))
        self.assertGreater(applied, 0)
        stats = stream.stats()
        self.assertEqual(stats["applied"], applied)
        self.assertEqual(stats["rejected"], 0)

    def test_genuine_duplicate_is_rejected_exactly_once(self):
        stream = DeltaPublicEventStream(venue="DELTA_INDIA")
        bundle = load(INDIA_ROLLOVER)
        candles = [f for f in data_frames(bundle) if f.get("type") == "candlestick_1m"]
        serialized = [json.dumps(f, sort_keys=True) for f in candles]
        dup = next(s for s in set(serialized) if serialized.count(s) > 1)
        frame = json.loads(dup)
        first = stream.ingest(frame, receipt_timestamp=frame["ts"])
        second = stream.ingest(frame, receipt_timestamp=frame["ts"])
        self.assertEqual(first.status, "APPLIED")
        self.assertEqual(second.status, "DUPLICATE_OR_OLD")

    def test_ticker_and_control_are_unhandled_not_applied(self):
        stream = DeltaPublicEventStream(venue="DELTA_INDIA")
        ticker = next(
            f for f in data_frames(load(INDIA_A)) if f.get("type") == "ticker"
        )
        self.assertEqual(
            stream.ingest(ticker, receipt_timestamp=ticker["ts"]).status, "UNHANDLED"
        )
        control = load(INDIA_A)["frames"][0]["frame"]
        self.assertEqual(
            stream.ingest(control, receipt_timestamp=1_700_000_000).status, "UNHANDLED"
        )

    def test_malformed_frame_rejected_never_fatal(self):
        stream = DeltaPublicEventStream(venue="DELTA_INDIA")
        self.assertEqual(
            stream.ingest({"type": "candlestick_1m"}, receipt_timestamp=1).status,
            "REJECTED",
        )
        self.assertEqual(stream.ingest("not-a-mapping", receipt_timestamp=1).status,
                         "REJECTED")


class TestSessionGateWithGenuineRollover(unittest.TestCase):
    @staticmethod
    def _starts_seconds() -> list[int]:
        bundle = load(INDIA_ROLLOVER)
        candles = [f for f in data_frames(bundle) if f.get("type") == "candlestick_1m"]
        return sorted({int(f["cst"]) // 1_000_000 for f in candles})

    def test_genuine_rollover_drives_gate_to_ready(self):
        first, second = self._starts_seconds()[:2]
        self.assertEqual(second - first, 60)
        gate = CandleSessionGate("1m")
        gate.on_connected()
        self.assertFalse(gate.observe_candle_start(first).ready)
        self.assertFalse(gate.observe_candle_start(first).ready)
        decision = gate.observe_candle_start(second)
        self.assertTrue(decision.ready)

    def test_disconnect_revokes_until_genuine_resync(self):
        first, second = self._starts_seconds()[:2]
        gate = CandleSessionGate("1m")
        gate.on_connected()
        gate.observe_candle_start(first)
        gate.observe_candle_start(second)
        self.assertTrue(gate.status()["ready"])
        gate.on_disconnected()
        self.assertFalse(gate.status()["ready"])
        gate.on_connected()
        self.assertFalse(gate.observe_candle_start(second).ready)
        self.assertFalse(gate.status()["ready"])


class TestBridgeAndDispatchFailClosed(unittest.TestCase):
    def test_single_cst_stream_never_yields_runtime_candle(self):
        stream = DeltaPublicEventStream(venue="DELTA_INDIA")
        bridge_results = []
        for frame in data_frames(load(INDIA_A)):
            if frame.get("type") != "candlestick_1m":
                continue
            result = stream.ingest(frame, receipt_timestamp=frame["ts"])
            decision = to_runtime_candle(result, expected_resolution="1m")
            bridge_results.append(decision)
            self.assertIsNone(decision.candle)
        self.assertGreater(len(bridge_results), 0)

    def test_dispatcher_refuses_without_authoritative_state(self):
        bundle = load(INDIA_ROLLOVER)
        frame = next(
            f for f in data_frames(bundle) if f.get("type") == "candlestick_1m"
        )
        event = normalize_candlestick_frame(
            frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA"
        )
        candle = Candle(
            timestamp=event.candle_start_timestamp or 0,
            open=event.open, high=event.high, low=event.low,
            close=event.close, volume=event.volume or 0.0,
            closed=True, symbol="BTCUSD",
        )
        dispatcher = VerifiedStrategyDispatcher(lambda _: self.fail("must not deliver"))
        decision = dispatcher.dispatch(candle, None)
        self.assertFalse(decision.allowed)


class TestLookaheadSafety(unittest.TestCase):
    def test_future_frames_do_not_rewrite_historical_statuses(self):
        bundle = load(INDIA_A)
        before = classify_india_evidence(bundle)
        candles = [f for f in data_frames(bundle) if f.get("type") == "candlestick_1m"]
        last_cst = max(f["cst"] for f in candles)
        future_candle = dict(candles[0], cst=last_cst + 3_600_000_000,
                             ts=last_cst + 3_600_000_001)
        extended = dict(bundle, frames=list(bundle["frames"]) + [
            {"receipt_ordinal": len(bundle["frames"]) + 1,
             "frame": future_candle, "classification": "requested_public_data"}
        ])
        after = classify_india_evidence(extended)
        # Schema/flow statuses of the historical window are stable; only the
        # metric that explicitly depends on the new observation may change.
        self.assertEqual(after["candlestick_1m"], before["candlestick_1m"])
        self.assertEqual(after["trades"], before["trades"])
        self.assertEqual(after["ticker"], before["ticker"])
        self.assertTrue(has_india_rollover(extended) or not has_india_rollover(bundle))


class TestExactContractGapsPinned(unittest.TestCase):
    def test_no_genuine_frame_carries_close_or_sequence(self):
        checked = 0
        for name in (INDIA_A, INDIA_B, INDIA_ROLLOVER, GLOBAL_TICKER):
            for frame in data_frames(load(name)):
                checked += 1
                self.assertNotIn("closed", frame)
                self.assertNotIn("is_closed", frame)
                self.assertNotIn("close_flag", frame)
                self.assertNotIn("sequence", frame)
                self.assertNotIn("seq", frame)
        self.assertGreater(checked, 0)

    def test_cst_observed_but_undocumented(self):
        # PARTIALLY_VERIFIED: cst present in genuine India + Global candle
        # captures though absent from the compact documentation sample.
        for name in (INDIA_A, INDIA_ROLLOVER):
            candles = [f for f in data_frames(load(name))
                       if f.get("type") == "candlestick_1m"]
            self.assertGreater(len(candles), 0)
            for frame in candles:
                self.assertIn("cst", frame)


class TestGlobalStatePinned(unittest.TestCase):
    def test_global_silence_is_genuine_negative_evidence(self):
        from scripts.verify_delta_global_evidence import verify_single_session

        bundle = load(GLOBAL_SILENCE)
        self.assertEqual(data_frames(bundle), [])
        self.assertFalse(verify_single_session(bundle).passed)

    def test_global_reconnect_still_passes_client_bar(self):
        from scripts.verify_delta_global_evidence import verify_reconnect_observation

        self.assertTrue(verify_reconnect_observation(load(GLOBAL_RECONNECT)).passed)

    def test_no_single_global_bundle_passes_full_bar(self):
        from scripts.verify_delta_global_evidence import verify_single_session

        names = [
            "observed_global_btcusdt_candles_20260918.json",
            "observed_global_btcusdt_candles_long_20260918.json",
            "observed_global_btcusdt_candles_rollover_attempt_20260918.json",
            "observed_global_btcusdt_candle_rollover_timed_20260918.json",
            "observed_global_btcusdt_candle_silence_20260918.json",
            "observed_global_btcusdt_subscription_echo_20260918.json",
            "observed_global_btcusdt_trades_20260918.json",
        ]
        for name in names:
            with self.subTest(bundle=name):
                self.assertFalse(verify_single_session(load(FIXTURES / name)).passed)


class TestCrossCaptureReproducibility(unittest.TestCase):
    def test_two_independent_captures_share_contract(self):
        first, second = load(INDIA_A), load(INDIA_B)
        for bundle in (first, second):
            self.assertEqual(bundle["endpoint"],
                             "wss://public-socket.india.delta.exchange")
            self.assertEqual(bundle["symbol"], "BTCUSD")
            self.assertEqual(bundle["requested_channels"],
                             ["candlestick_1m", "trades", "ticker"])
        self.assertEqual(classify_india_evidence(first),
                         classify_india_evidence(second))
        for bundle in (first, second):
            keys = {tuple(sorted(f.keys())) for f in data_frames(bundle)
                    if f.get("type") == "candlestick_1m"}
            self.assertEqual(len(keys), 1)

    def test_hashes_are_stable_and_distinct(self):
        first, second = load(INDIA_A), load(INDIA_B)
        self.assertEqual(hash_fixture(first), hash_fixture(first))
        self.assertEqual(serialize_fixture(first), serialize_fixture(first))
        self.assertNotEqual(hash_fixture(first), hash_fixture(second))


if __name__ == "__main__":
    unittest.main()
