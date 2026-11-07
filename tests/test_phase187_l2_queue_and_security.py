"""
QuantEngine Phase 187 — Comprehensive Regression Test Suite.

Covers:
  1. L2BookTracker 7-state validity machine (INITIALIZING, VALID, STALE, SEQUENCE_GAP, etc.).
  2. Monotonic sequence gap detection and crossed book invalidation.
  3. L2QualityAnalyzer offline replay and verification across historical Delta testnet archives.
  4. QueueCalibrationEngine identifiability proofs and chronological holdout evaluation.
  5. 120-second order timeout policy verification (strict cancellation, zero market order conversion).
  6. Release packaging security & synthetic canary secret detection.
"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import time
import unittest

from core.research.l2_book_tracker import L2BookTracker, BookValidityState
from core.research.l2_quality_analyzer import L2QualityAnalyzer
from core.research.queue_calibration_engine import QueueCalibrationEngine
from core.paper_trading.queue_aware_paper_engine import (
    QueueAwarePaperExecutionEngine,
    PaperOrderState,
    QueueScenario,
)
from scripts.security.scan_secrets import scan_worktree
from tests.test_packaging_no_secrets_phase132 import _violations

ROOT = Path(__file__).resolve().parents[1]


class TestPhase187L2BookTracker(unittest.TestCase):
    """Test deterministic L2 order book tracker and validity state machine."""

    def test_initial_state_is_initializing(self):
        tracker = L2BookTracker("BTCUSD")
        self.assertEqual(tracker.state, BookValidityState.INITIALIZING)
        self.assertIsNone(tracker.best_bid())
        self.assertIsNone(tracker.best_ask())

    def test_snapshot_transitions_to_valid(self):
        tracker = L2BookTracker("BTCUSD")
        bids = [["82000.0", "5.0"], ["81990.0", "10.0"]]
        asks = [["82010.0", "3.0"], ["82020.0", "8.0"]]
        ok = tracker.process_snapshot(bids, asks, sequence=100, venue_timestamp_us=1700000000000000)
        
        self.assertTrue(ok)
        self.assertEqual(tracker.state, BookValidityState.VALID)
        self.assertEqual(tracker.best_bid(), Decimal("82000.0"))
        self.assertEqual(tracker.best_ask(), Decimal("82010.0"))
        self.assertEqual(tracker.spread(), Decimal("10.0"))

    def test_incremental_updates_maintain_sequence(self):
        tracker = L2BookTracker("BTCUSD")
        bids = [["82000.0", "5.0"]]
        asks = [["82010.0", "3.0"]]
        tracker.process_snapshot(bids, asks, sequence=100, venue_timestamp_us=1700000000000000)

        # In-order update at seq 101
        update_ok = tracker.process_update(
            bids=[["82005.0", "2.0"]],
            asks=[],
            sequence=101,
            venue_timestamp_us=1700000001000000,
        )
        self.assertTrue(update_ok)
        self.assertEqual(tracker.state, BookValidityState.VALID)
        self.assertEqual(tracker.best_bid(), Decimal("82005.0"))
        self.assertEqual(tracker.last_sequence, 101)

    def test_sequence_gap_invalidates_book(self):
        tracker = L2BookTracker("BTCUSD")
        bids = [["82000.0", "5.0"]]
        asks = [["82010.0", "3.0"]]
        tracker.process_snapshot(bids, asks, sequence=100, venue_timestamp_us=1700000000000000)

        # Gap from 100 to 105
        update_ok = tracker.process_update(
            bids=[["82005.0", "2.0"]],
            asks=[],
            sequence=105,
            venue_timestamp_us=1700000005000000,
        )
        self.assertFalse(update_ok)
        self.assertEqual(tracker.state, BookValidityState.SEQUENCE_GAP)
        self.assertEqual(tracker.metrics.gap_count, 1)
        self.assertEqual(len(tracker.gaps), 1)
        self.assertEqual(tracker.gaps[0].gap_size, 4)

    def test_crossed_book_detected_and_rejected(self):
        tracker = L2BookTracker("BTCUSD")
        bids = [["82000.0", "5.0"]]
        asks = [["82010.0", "3.0"]]
        tracker.process_snapshot(bids, asks, sequence=100, venue_timestamp_us=1700000000000000)

        # Update crossed book: bid at 82015 >= ask 82010
        update_ok = tracker.process_update(
            bids=[["82015.0", "2.0"]],
            asks=[],
            sequence=101,
            venue_timestamp_us=1700000001000000,
        )
        self.assertFalse(update_ok)
        self.assertEqual(tracker.state, BookValidityState.INVALID)
        self.assertEqual(tracker.metrics.crossed_book_count, 1)

    def test_staleness_transition(self):
        tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=2.0)
        now_mono = time.monotonic_ns()
        tracker.process_snapshot(
            bids=[["82000.0", "5.0"]],
            asks=[["82010.0", "3.0"]],
            sequence=100,
            venue_timestamp_us=1700000000000000,
            receipt_mono_ns=now_mono,
        )
        self.assertEqual(tracker.state, BookValidityState.VALID)

        # Check staleness at +1.0s (not stale)
        self.assertFalse(tracker.check_staleness(now_mono + 1_000_000_000))
        self.assertEqual(tracker.state, BookValidityState.VALID)

        # Check staleness at +2.5s (stale)
        self.assertTrue(tracker.check_staleness(now_mono + 2_500_000_000))
        self.assertEqual(tracker.state, BookValidityState.STALE)


class TestPhase187L2QualityAnalyzer(unittest.TestCase):
    """Test offline replay quality analyzer across genuine Delta testnet captures."""

    def test_analyze_historical_phase167_archive(self):
        archive_path = ROOT / "research" / "captures" / "phase167_recon" / "l2" / "delta_ob_updates_archive.json"
        if not archive_path.exists():
            self.skipTest("Phase 167 archive not present")

        analyzer = L2QualityAnalyzer()
        res = analyzer.analyze_archive_json(archive_path)

        self.assertEqual(res["total_records"], 113)
        self.assertIn("BTCUSD", res["symbols"])
        btc = res["symbols"]["BTCUSD"]
        self.assertEqual(btc["state"], "VALID")
        self.assertEqual(btc["gap_count"], 0)
        self.assertEqual(btc["crossed_book_count"], 0)
        self.assertEqual(btc["valid_coverage_pct"], 100.0)


class TestPhase187QueueCalibration(unittest.TestCase):
    """Test queue model calibration identifiability proofs and sensitivity bounds."""

    def test_identifiability_proof_confirms_uncalibrated_status(self):
        engine = QueueCalibrationEngine("BTCUSD")
        proof = engine.evaluate_identifiability()
        self.assertEqual(proof["calibration_status"], "UNCALIBRATED_PARTIALLY_OBSERVABLE")
        self.assertEqual(proof["scientific_conclusion"], "EMPIRICAL_CALIBRATION_BLOCKED_PENDING_ORDER_LABELS")

    def test_chronological_holdout_sensitivity_bounds(self):
        archive_path = ROOT / "research" / "captures" / "phase167_recon" / "l2" / "delta_ob_updates_archive.json"
        if not archive_path.exists():
            self.skipTest("Phase 167 archive not present")

        raw_frames = json.loads(archive_path.read_text(encoding="utf-8")).get("frames", [])
        engine = QueueCalibrationEngine("BTCUSD")
        res = engine.run_chronological_holdout_evaluation(raw_frames)

        self.assertIn("evaluation_grid_results", res)
        grid = res["evaluation_grid_results"]
        self.assertGreater(len(grid), 0)

        # Check bounds: front-of-queue (theta 0.1) fill prob >= tail-of-queue (theta 0.9)
        front_fill = next(g for g in grid if g["theta_priority"] == 0.10 and g["horizon_seconds"] == 60.0)
        tail_fill = next(g for g in grid if g["theta_priority"] == 0.90 and g["horizon_seconds"] == 60.0)
        self.assertGreaterEqual(front_fill["predicted_fill_probability"], tail_fill["predicted_fill_probability"])


class TestPhase187TimeoutPolicyOffline(unittest.TestCase):
    """Verify 120s timeout policy invariants without live trading."""

    def test_120s_timeout_cancels_without_market_conversion(self):
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        start_ns = 1_000_000_000_000

        order = engine.submit_candidate_trade(
            order_id="test_to_001",
            symbol="BTCUSD",
            side="BUY",
            entry_price="82000.0",
            stop_price="81800.0",
            target_price="82400.0",
            quantity="1",
            risk_budget="5.0",
            best_bid="82000.0",
            best_ask="82010.0",
            timeout_seconds=120.0,
            submission_mono_ns=start_ns,
        )
        self.assertEqual(order.state, PaperOrderState.RESTING)
        self.assertEqual(order.order_type, "LIMIT_POST_ONLY")

        # Advance clock to 119s -> still resting
        timed_out = engine.check_order_timeouts(current_mono_ns=start_ns + 119_000_000_000)
        self.assertEqual(len(timed_out), 0)
        self.assertEqual(order.state, PaperOrderState.RESTING)

        # Advance clock to 120s -> cancelled
        timed_out = engine.check_order_timeouts(current_mono_ns=start_ns + 120_000_000_000)
        self.assertEqual(len(timed_out), 1)
        self.assertEqual(order.state, PaperOrderState.CANCELLED)
        # CRUCIAL INVARIANT: Order was NOT converted to market order!
        self.assertEqual(order.order_type, "LIMIT_POST_ONLY")
        self.assertEqual(order.filled_quantity, Decimal("0"))


class TestPhase187SecurityHygiene(unittest.TestCase):
    """Verify release security boundaries, packaging rules, and synthetic secret canary tests."""

    def test_root_env_excluded_from_manifest(self):
        manifest = (ROOT / "BUILD_MANIFEST.sha256").read_text(encoding="utf-8")
        self.assertNotIn("\t.env\n", manifest)
        self.assertNotIn(" .env\n", manifest)

    def test_nested_env_detected_by_violations(self):
        """Proof that accidental nested .env is violently caught and not exempted."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            nested = p / "core" / ".env"
            nested.parent.mkdir(parents=True, exist_ok=True)
            nested.write_text("SOME_SECRET=123\n", encoding="utf-8")

            violations = _violations(p)
            self.assertIn("core/.env", violations)

    def test_synthetic_canary_secret_detected_by_scanner(self):
        """Synthetic negative test: scanner detects canary credential in temporary worktree."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            canary_file = p / "canary_script.py"
            # Dynamically construct canary secret assignment to avoid literal token in test source
            sec_var = "_".join(["DELTA", "INDIA", "TESTNET", "API", "SECRET"])
            canary_file.write_text(f'{sec_var} = "abcdef0123456789abcdef0123456789"\n', encoding="utf-8")

            findings = scan_worktree(p)
            self.assertGreater(len(findings), 0, "Scanner must detect canary secret")


if __name__ == "__main__":
    unittest.main()
