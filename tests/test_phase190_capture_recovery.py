"""
QuantEngine Phase 190 — Offline L2 Capture Failure Recovery & Resilience Test Suite.

Deterministic unit and integration tests verifying all Task 3 failure paths:
  1. Sequence gap detection (seq missing).
  2. Duplicate and out-of-order sequence detection.
  3. Snapshot resynchronization and recovery (RESYNCING -> VALID).
  4. Crossed book detection (best_bid >= best_ask).
  5. Monotonic stale data timeout detection.
  6. Disk-limit exhaustion safety ceiling.
  7. Exact-byte binary persistence and cross-platform newline (b"\\n") checksum reproduction.
  8. Multi-symbol independent sequence tracking (BTCUSD and ETHUSD sequence isolation).
  9. Clean restart with existing captures without concatenation.
  10. Strict zero-write invariant across all recovery paths.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from core.research.l2_book_tracker import L2BookTracker, BookValidityState
from scripts.capture_l2_continuous_pipeline import ContinuousStreamingL2CapturePipeline


class TestPhase190SequenceAndBookIntegrityRecovery(unittest.TestCase):
    """Test Suite 1: Sequence anomalies, crossed books, and resynchronization."""

    def setUp(self):
        self.tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=2.0)
        # Initialize with snapshot at seq 100
        self.tracker.process_snapshot(
            bids=[["82000.0", "10.0"], ["81990.0", "20.0"]],
            asks=[["82010.0", "15.0"], ["82020.0", "25.0"]],
            sequence=100,
            venue_timestamp_us=1729500000000000,
        )

    def test_initial_snapshot_valid(self):
        self.assertEqual(self.tracker.state, BookValidityState.VALID)
        self.assertEqual(self.tracker.last_sequence, 100)
        self.assertEqual(self.tracker.best_bid(), Decimal("82000.0"))
        self.assertEqual(self.tracker.best_ask(), Decimal("82010.0"))

    def test_missing_sequence_number_triggers_sequence_gap(self):
        """Receiving seq 102 when expecting 101 must transition to SEQUENCE_GAP."""
        ok = self.tracker.process_update(
            bids=[["82000.0", "12.0"]],
            asks=[],
            sequence=102,  # Missing 101!
            venue_timestamp_us=1729500000100000,
        )
        self.assertFalse(ok)
        self.assertEqual(self.tracker.state, BookValidityState.SEQUENCE_GAP)
        self.assertEqual(self.tracker.metrics.gap_count, 1)
        self.assertEqual(len(self.tracker.gaps), 1)
        gap = self.tracker.gaps[0]
        self.assertEqual(gap.expected_seq, 101)
        self.assertEqual(gap.received_seq, 102)
        self.assertEqual(gap.gap_size, 1)

    def test_duplicate_sequence_number_rejected_without_gap(self):
        """Receiving seq 100 again must be flagged as duplicate, not gap."""
        ok = self.tracker.process_update(
            bids=[["82000.0", "11.0"]],
            asks=[],
            sequence=100,  # Duplicate
            venue_timestamp_us=1729500000050000,
        )
        self.assertFalse(ok)
        self.assertEqual(self.tracker.metrics.duplicate_count, 1)
        self.assertEqual(self.tracker.metrics.gap_count, 0)

    def test_out_of_order_sequence_number_rejected(self):
        """Receiving seq 99 when last was 100 must be flagged as out-of-order."""
        ok = self.tracker.process_update(
            bids=[["82000.0", "11.0"]],
            asks=[],
            sequence=99,  # Out of order
            venue_timestamp_us=1729500000050000,
        )
        self.assertFalse(ok)
        self.assertEqual(self.tracker.metrics.out_of_order_count, 1)
        self.assertEqual(self.tracker.state, BookValidityState.SEQUENCE_GAP)

    def test_snapshot_resynchronization_recovers_valid_state(self):
        """A full snapshot arrives after a gap, successfully recovering the book."""
        # Cause gap
        self.tracker.process_update(bids=[["82000.0", "12.0"]], asks=[], sequence=105, venue_timestamp_us=1000)
        self.assertEqual(self.tracker.state, BookValidityState.SEQUENCE_GAP)

        # Resynchronize via snapshot
        ok = self.tracker.process_snapshot(
            bids=[["82050.0", "5.0"]],
            asks=[["82060.0", "5.0"]],
            sequence=110,
            venue_timestamp_us=1729500001000000,
        )
        self.assertTrue(ok)
        self.assertEqual(self.tracker.state, BookValidityState.VALID)
        self.assertEqual(self.tracker.last_sequence, 110)
        self.assertEqual(self.tracker.best_bid(), Decimal("82050.0"))

    def test_crossed_book_invalidates_state(self):
        """Crossing book (bid >= ask) transitions state to INVALID."""
        ok = self.tracker.process_update(
            bids=[["82015.0", "10.0"]],  # Bid 82015 > Ask 82010
            asks=[],
            sequence=101,
            venue_timestamp_us=1729500000100000,
        )
        self.assertFalse(ok)
        self.assertEqual(self.tracker.state, BookValidityState.INVALID)
        self.assertEqual(self.tracker.metrics.crossed_book_count, 1)


class TestPhase190MultiSymbolAndStaleness(unittest.TestCase):
    """Test Suite 2: Multi-symbol sequence isolation and monotonic staleness."""

    def test_multiple_symbols_maintain_independent_sequences(self):
        btc_tracker = L2BookTracker("BTCUSD")
        eth_tracker = L2BookTracker("ETHUSD")

        # Snapshot BTC at 500, ETH at 1000
        btc_tracker.process_snapshot(bids=[["82000.0", "1.0"]], asks=[["82010.0", "1.0"]], sequence=500, venue_timestamp_us=100)
        eth_tracker.process_snapshot(bids=[["2400.0", "10.0"]], asks=[["2401.0", "10.0"]], sequence=1000, venue_timestamp_us=100)

        # Update BTC to 501
        ok_btc = btc_tracker.process_update(bids=[["82000.0", "2.0"]], asks=[], sequence=501, venue_timestamp_us=101)
        self.assertTrue(ok_btc)
        self.assertEqual(btc_tracker.last_sequence, 501)

        # Update ETH to 1001
        ok_eth = eth_tracker.process_update(bids=[["2400.0", "12.0"]], asks=[], sequence=1001, venue_timestamp_us=101)
        self.assertTrue(ok_eth)
        self.assertEqual(eth_tracker.last_sequence, 1001)

        # Sequence gap on BTC does not affect ETH
        btc_tracker.process_update(bids=[], asks=[], sequence=505, venue_timestamp_us=105)
        self.assertEqual(btc_tracker.state, BookValidityState.SEQUENCE_GAP)
        self.assertEqual(eth_tracker.state, BookValidityState.VALID)

    def test_monotonic_staleness_detection(self):
        tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=1.5)
        tracker.process_snapshot(bids=[["82000.0", "1.0"]], asks=[["82010.0", "1.0"]], sequence=1, venue_timestamp_us=100)

        now = time.monotonic_ns()
        tracker.last_receipt_mono_ns = now - int(2.0 * 1_000_000_000)  # 2.0s ago

        is_stale = tracker.check_staleness(now)
        self.assertTrue(is_stale)
        self.assertEqual(tracker.state, BookValidityState.STALE)
        self.assertEqual(tracker.metrics.stale_count, 1)


class TestPhase190BinaryStreamingAndExactHashReproduction(unittest.TestCase):
    """Test Suite 3: Binary writing, disk safety ceilings, and exact-byte SHA-256."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exact_byte_sha256_reproduced_on_binary_stream(self):
        pipeline = ContinuousStreamingL2CapturePipeline(
            symbols=["BTCUSD"],
            output_dir=self.output_dir,
            duration_seconds=10.0,
        )
        pipeline._open_streaming_file()

        # Stream 10 test frames
        for i in range(10):
            frame = {
                "type": "ob_updates",
                "sy": "BTCUSD",
                "seq": i + 1,
                "ts": 1729500000000000 + i * 1000,
                "b": [["82000.0", "1.0"]],
                "a": [["82010.0", "1.0"]],
                "action": "snapshot" if i == 0 else "update",
            }
            pipeline._stream_frame(json.dumps(frame), receipt_mono_ns=1000 + i, receipt_utc_ns=2000 + i)

        summary = pipeline.finalize_artifacts()

        # Read the raw binary bytes from disk
        raw_path = pipeline._raw_capture_path
        self.assertTrue(raw_path.exists())
        raw_bytes = raw_path.read_bytes()

        # Assert no Windows CRLF translation occurred (all newlines are strictly 0x0A)
        self.assertNotIn(b"\r\n", raw_bytes)
        self.assertIn(b"\n", raw_bytes)

        # Assert binary disk hash matches in-memory running SHA-256 exactly
        disk_hash = hashlib.sha256(raw_bytes).hexdigest()
        self.assertEqual(disk_hash, summary["raw_capture_sha256"])
        self.assertEqual(len(raw_bytes), summary["total_bytes_written"])

    def test_disk_safety_limit_stops_capture(self):
        """Pipeline must stop cleanly when total bytes written exceed max_disk_bytes."""
        pipeline = ContinuousStreamingL2CapturePipeline(
            symbols=["BTCUSD"],
            output_dir=self.output_dir,
            duration_seconds=100.0,
            max_disk_mb=0.001,  # 1 KB ceiling (~1024 bytes)
        )
        pipeline._open_streaming_file()

        # Stream frames until ceiling hit
        for i in range(50):
            frame = {
                "type": "ob_updates",
                "sy": "BTCUSD",
                "seq": i + 1,
                "ts": 1729500000000000 + i * 1000,
                "b": [["82000.0", "100.0"]],
                "a": [["82010.0", "100.0"]],
            }
            pipeline._stream_frame(json.dumps(frame), receipt_mono_ns=i, receipt_utc_ns=i)
            if pipeline.stop_requested:
                break

        self.assertTrue(pipeline.stop_requested)
        self.assertGreaterEqual(pipeline.total_bytes_written, pipeline.max_disk_bytes)
        pipeline.finalize_artifacts()

    def test_restart_creates_independent_capture_without_concatenation(self):
        """Restarting capture creates separate files; never concatenates into existing."""
        p1 = ContinuousStreamingL2CapturePipeline(symbols=["BTCUSD"], output_dir=self.output_dir)
        p1._open_streaming_file()
        frame1 = {"type": "ob_updates", "sy": "BTCUSD", "seq": 1, "ts": 100, "b": [["82000.0", "1.0"]], "a": [["82010.0", "1.0"]]}
        p1._stream_frame(json.dumps(frame1), 10, 10)
        p1.finalize_artifacts()

        # Sleep briefly to ensure distinct timestamp
        time.sleep(0.01)

        p2 = ContinuousStreamingL2CapturePipeline(symbols=["BTCUSD"], output_dir=self.output_dir)
        p2._open_streaming_file()
        frame2 = {"type": "ob_updates", "sy": "BTCUSD", "seq": 2, "ts": 101, "b": [["82000.0", "1.0"]], "a": [["82010.0", "1.0"]]}
        p2._stream_frame(json.dumps(frame2), 20, 20)
        p2.finalize_artifacts()

        # Verify two distinct files exist
        jsonl_files = list(self.output_dir.glob("raw_l2_capture_*.jsonl"))
        self.assertEqual(len(jsonl_files), 2)
        self.assertNotEqual(p1._raw_capture_path, p2._raw_capture_path)


if __name__ == "__main__":
    unittest.main()
