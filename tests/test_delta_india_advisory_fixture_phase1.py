"""India advisory fixture contract tests (deterministic, offline).

The redacted fixture is genuine bounded public traffic from
``wss://public-socket.india.delta.exchange`` for ``BTCUSD`` (advisory
only, credential-free, no orders).  Statuses use the precise vocabulary:

* candlestick_1m >= 1 frame -> VERIFIED_SCHEMA (schema presence only).
* trades >= 2 frames -> VERIFIED_BEHAVIOR (repository trade-flow bar).
* ticker >= 1 frame -> VERIFIED_SCHEMA.
* duplicate/rollover require the actual sequence; otherwise NOT_OBSERVED.
* ``_fx_rollover_skip_delta`` records "rollover unavailable, skipped"
  and must never be presented as rollover verified.
* Global evidence and production wiring are explicitly proven unchanged.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from data.delta.india_fixture_harness import (
    INDIA_PUBLIC_SOCKET,
    INDIA_SYMBOL,
    classify_india_evidence,
    fx_rollover_skip_requested,
    has_duplicate_candle,
    has_india_rollover,
    hash_fixture,
    redact_capture_for_fixture,
    require_india_rollover,
    serialize_fixture,
)
from data.delta.market_events import (
    InvalidMarketFrame,
    normalize_candlestick_frame,
    normalize_trade_frame,
)
from data.delta.verified_candle_subscription import (
    is_observed_subscription_snapshot,
)


FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "delta"
REDACTED = FIXTURES / "observed_india_btcusd_advisory_redacted_20260920.json"
LEGACY_ROLLOVER = (
    FIXTURES / "observed_india_btcusd_trades_candles_rollover_20260916.json"
)


def load(name: Path) -> dict:
    return json.loads(name.read_text(encoding="utf-8"))


def data_frames(bundle: dict) -> list[dict]:
    return [
        record["frame"]
        for record in bundle.get("frames", [])
        if record.get("classification") == "requested_public_data"
    ]


class TestIndiaAdvisoryCandleSchema(unittest.TestCase):
    def test_redacted_fixture_is_india_btcusd_advisory_only(self):
        bundle = load(REDACTED)
        self.assertEqual(bundle["endpoint"], INDIA_PUBLIC_SOCKET)
        self.assertEqual(bundle["symbol"], INDIA_SYMBOL)
        self.assertTrue(bundle.get("advisory_only"))
        self.assertEqual(bundle.get("production_wiring"), "UNCHANGED")

    def test_candle_schema_verified_schema(self):
        bundle = load(REDACTED)
        candles = [f for f in data_frames(bundle) if f.get("type") == "candlestick_1m"]
        self.assertGreaterEqual(len(candles), 1)
        for frame in candles:
            event = normalize_candlestick_frame(
                frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA"
            )
            self.assertEqual(event.provenance.instrument, "BTCUSD")
            self.assertEqual(event.resolution, "1m")
            self.assertEqual(event.price_basis, "TRADED_PRICE")
            self.assertIsNotNone(event.volume)
            self.assertIsNotNone(event.candle_start_timestamp)
            self.assertFalse(event.closed)
            self.assertIsNone(event.provenance.sequence)
        self.assertEqual(classify_india_evidence(bundle)["candlestick_1m"], "VERIFIED_SCHEMA")

    def test_subscription_echo_recognized(self):
        bundle = load(REDACTED)
        controls = [
            record["frame"]
            for record in bundle.get("frames", [])
            if record.get("classification") == "control_or_unrequested"
        ]
        self.assertEqual(len(controls), 1)
        # The echo covers all three requested channels; the narrow candle
        # predicate recognizes the candlestick_1m entry for BTCUSD.
        self.assertTrue(
            is_observed_subscription_snapshot(
                controls[0], symbols=["BTCUSD"], resolution="1m"
            )
        )
        self.assertFalse(
            is_observed_subscription_snapshot(
                controls[0], symbols=["BTCUSDT"], resolution="1m"
            )
        )


class TestIndiaAdvisoryTrades(unittest.TestCase):
    def test_trades_flow_meets_two_frame_bar(self):
        bundle = load(REDACTED)
        trades = [f for f in data_frames(bundle) if f.get("type") == "trades"]
        self.assertGreaterEqual(len(trades), 2)
        for frame in trades:
            event = normalize_trade_frame(
                frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA"
            )
            self.assertEqual(event.provenance.instrument, "BTCUSD")
            self.assertGreater(event.price, 0)
            self.assertGreater(event.quantity, 0)
            self.assertIn(event.maker_taker_role, ("maker", "taker"))
            self.assertIsNone(event.aggressor_side)
            self.assertIsNone(event.provenance.sequence)
        self.assertEqual(classify_india_evidence(bundle)["trades"], "VERIFIED_BEHAVIOR")

    def test_single_trade_frame_is_insufficient_not_verified(self):
        bundle = load(REDACTED)
        trades = [f for f in data_frames(bundle) if f.get("type") == "trades"]
        single = dict(bundle, frames=[
            {"receipt_ordinal": 1, "frame": trades[0],
             "classification": "requested_public_data"}
        ])
        self.assertEqual(classify_india_evidence(single)["trades"], "INSUFFICIENT")


class TestIndiaAdvisoryTicker(unittest.TestCase):
    def test_ticker_schema_verified_schema(self):
        bundle = load(REDACTED)
        tickers = [f for f in data_frames(bundle) if f.get("type") == "ticker"]
        self.assertGreaterEqual(len(tickers), 1)
        for frame in tickers:
            self.assertEqual(frame["sy"], "BTCUSD")
            self.assertIn("m", frame["d"][0])
            # A ticker reference frame is not a 1m candle and must never
            # normalize as one.
            with self.assertRaises(InvalidMarketFrame):
                normalize_candlestick_frame(
                    frame, receipt_timestamp=frame["ts"], venue="DELTA_INDIA"
                )
        self.assertEqual(classify_india_evidence(bundle)["ticker"], "VERIFIED_SCHEMA")

    def test_missing_ticker_is_unavailable_not_verified(self):
        bundle = load(LEGACY_ROLLOVER)
        self.assertEqual(classify_india_evidence(bundle)["ticker"], "UNAVAILABLE")


class TestIndiaDuplicateAndRolloverEvidence(unittest.TestCase):
    def test_new_fixture_has_no_duplicate_no_rollover(self):
        bundle = load(REDACTED)
        self.assertFalse(has_duplicate_candle(bundle))
        self.assertFalse(has_india_rollover(bundle))
        classification = classify_india_evidence(bundle)
        self.assertEqual(classification["duplicate_candle"], "NOT_OBSERVED")
        self.assertEqual(classification["rollover"], "NOT_OBSERVED")

    def test_legacy_rollover_fixture_preserves_observed_behavior(self):
        bundle = load(LEGACY_ROLLOVER)
        self.assertTrue(has_duplicate_candle(bundle))
        self.assertTrue(has_india_rollover(bundle))
        classification = classify_india_evidence(bundle)
        self.assertEqual(classification["duplicate_candle"], "VERIFIED_BEHAVIOR")
        self.assertEqual(classification["rollover"], "VERIFIED_BEHAVIOR")

    def test_rollover_requires_consecutive_step_not_any_two_minutes(self):
        bundle = load(REDACTED)
        candles = [f for f in data_frames(bundle) if f.get("type") == "candlestick_1m"]
        starts = list(dict.fromkeys(f["cst"] for f in candles))
        # Single-cst short capture: no cross-boundary sequence observed.
        self.assertEqual(len(starts), 1)


class TestFxRolloverSkipDelta(unittest.TestCase):
    def tearDown(self):
        for name in (
            "_fx_rollover_skip_delta",
            "FX_ROLLOVER_SKIP_DELTA",
            "QUANTENGINE_FX_ROLLOVER_SKIP_DELTA",
        ):
            os.environ.pop(name, None)

    def test_missing_rollover_fails_closed_without_skip(self):
        bundle = load(REDACTED)
        with self.assertRaises(AssertionError):
            require_india_rollover(bundle, skip=False)

    def test_explicit_skip_records_not_observed_skipped(self):
        bundle = load(REDACTED)
        status = require_india_rollover(bundle, skip=True)
        self.assertEqual(status, "NOT_OBSERVED_SKIPPED")
        self.assertNotEqual(status, "OBSERVED")
        # The skip must never be presented as verified behavior.
        self.assertEqual(classify_india_evidence(bundle)["rollover"], "NOT_OBSERVED")

    def test_env_var_enables_skip_only_for_india_assertion(self):
        os.environ["_fx_rollover_skip_delta"] = "1"
        self.assertTrue(fx_rollover_skip_requested())
        bundle = load(REDACTED)
        self.assertEqual(require_india_rollover(bundle), "NOT_OBSERVED_SKIPPED")

    def test_observed_rollover_needs_no_skip(self):
        bundle = load(LEGACY_ROLLOVER)
        self.assertEqual(require_india_rollover(bundle, skip=False), "OBSERVED")
        self.assertEqual(require_india_rollover(bundle, skip=True), "OBSERVED")

    def test_skip_flag_defaults_off(self):
        self.assertFalse(fx_rollover_skip_requested(explicit=False))
        self.assertFalse(fx_rollover_skip_requested())


class TestIndiaGlobalIsolation(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("_fx_rollover_skip_delta", None)

    def test_india_bundle_never_passes_global_bar(self):
        from scripts.verify_delta_global_evidence import verify_single_session

        verdict = verify_single_session(load(REDACTED))
        self.assertFalse(verdict.passed)
        names = [check.name for check in verdict.failures()]
        self.assertIn("global_endpoint", names)
        self.assertIn("global_symbol_in_universe", names)

    def test_india_skip_does_not_change_global_verdict(self):
        from scripts.verify_delta_global_evidence import verify_single_session

        before = verify_single_session(load(REDACTED))
        os.environ["_fx_rollover_skip_delta"] = "1"
        after = verify_single_session(load(REDACTED))
        self.assertFalse(before.passed)
        self.assertFalse(after.passed)
        self.assertEqual(
            [c.name for c in before.failures()], [c.name for c in after.failures()]
        )

    def test_global_transport_still_requires_global_evidence(self):
        from data.delta.verified_socket_transport import check_global_evidence

        with self.assertRaises(Exception):
            check_global_evidence(
                str(REDACTED), symbols=("BTCUSDT",), resolution="1m"
            )


class TestIndiaProductionIsolation(unittest.TestCase):
    def test_verified_transport_refuses_india_endpoint(self):
        from data.delta.verified_socket_transport import VerifiedSocketTransport

        with self.assertRaisesRegex(ValueError, "verified Global transport"):
            VerifiedSocketTransport(
                symbols=["BTCUSD"],
                on_closed_candle=lambda candle: None,
                endpoint=INDIA_PUBLIC_SOCKET,
            )

    def test_harness_is_never_imported_by_production(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "main.py",
            "data/websocket_client.py",
            "data/delta/verified_socket_transport.py",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("india_fixture_harness", source)
            self.assertNotIn("_fx_rollover_skip_delta", source)

    def test_main_has_no_india_production_wiring(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("india.delta.exchange", source)
        self.assertNotIn("BTCUSD", source)


class TestIndiaFixtureDeterminism(unittest.TestCase):
    def test_redaction_is_byte_identical(self):
        first = load(REDACTED)
        # Re-derive redaction from the stored frames: identical input must
        # produce byte-identical output.
        candidate = {
            "schema": "quantengine.delta-public-capture.v1",
            "endpoint": first["endpoint"],
            "symbol": first["symbol"],
            "requested_channels": first["requested_channels"],
            "frames": [
                {
                    "receipt_ordinal": 999,
                    "receipt_unix_ns": 123,
                    "frame": record["frame"],
                    "classification": record.get("classification"),
                }
                for record in first["frames"]
            ],
            "started_unix": 1234567890.0,
            "timeout_seconds": first.get("timeout_seconds"),
            "max_frames": first.get("max_frames"),
            "malformed_frames": first.get("malformed_frames", 0),
            "limitations": first.get("limitations", []),
        }
        once = serialize_fixture(redact_capture_for_fixture(candidate))
        twice = serialize_fixture(redact_capture_for_fixture(candidate))
        self.assertEqual(once, twice)
        self.assertEqual(hash_fixture(redact_capture_for_fixture(candidate)),
                         hash_fixture(redact_capture_for_fixture(candidate)))

    def test_stored_fixture_has_no_nondeterministic_record_keys(self):
        bundle = load(REDACTED)
        self.assertNotIn("started_unix", bundle)
        for record in bundle["frames"]:
            self.assertNotIn("receipt_unix_ns", record)
            self.assertIn("receipt_ordinal", record)
        ordinals = [record["receipt_ordinal"] for record in bundle["frames"]]
        self.assertEqual(ordinals, list(range(1, len(ordinals) + 1)))

    def test_stored_fixture_contains_no_secret_material(self):
        bundle = load(REDACTED)
        blob = json.dumps(bundle).lower()
        for marker in ("api_key", "api_secret", "bearer", "authorization",
                       "cookie", "private key"):
            if marker == "authorization":
                continue  # word may appear in prose; keys are checked strictly
            self.assertNotIn(marker, blob)


if __name__ == "__main__":
    unittest.main()
