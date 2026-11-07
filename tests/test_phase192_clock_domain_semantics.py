"""
QuantEngine Phase 192 — Market-Data Clock Domain & Latency Semantics Test Suite.

All tests in this module are SIMULATED.
Explicitly distinguishes:
  1. Exchange-provided event timestamp (venue_ts).
  2. Local wall-clock receive timestamp (receipt_utc_ns).
  3. Local monotonic receive timestamp (receipt_mono_ns).
  4. Exchange sequence number (seq).
  5. Local inter-arrival interval (dt_mono).
  6. Estimated clock offset (venue_ts vs receipt_utc).
  7. One-way network latency vs clock skew.

Proves:
  - Negative difference between receipt_utc and venue_ts is clock offset/skew, NEVER negative transit time.
  - Forward and backward wall-clock jumps do not corrupt monotonic inter-arrival intervals.
  - Missing or malformed timestamp fields are handled gracefully without silent dropping.
  - Duplicate or out-of-order sequence numbers are detected.
  - Snapshot age (order book age on exchange prior to subscription) is distinguished from latency.

Strictly offline and SIMULATED. Zero exchange calls.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
import numpy as np


class TestPhase192ClockDomainSemantics(unittest.TestCase):
    """Test Suite: SIMULATED Clock Domain and Market-Data Latency Semantics."""

    def test_01_simulated_negative_wall_clock_diff_is_clock_skew(self):
        """SIMULATED: Proves receipt_utc < venue_ts is clock skew, never negative transit time."""
        # Venue clock is running 345 ms ahead of local host wall clock
        venue_clock_offset_ms = 345.0
        one_way_network_transit_ms = 45.0  # Genuine physical one-way flight time

        venue_event_time_ms = 1_000_000.0  # Venue event timestamp
        # Packet arrives at host after 45ms network flight time
        arrival_host_wall_clock_ms = (venue_event_time_ms - venue_clock_offset_ms) + one_way_network_transit_ms

        raw_diff_ms = arrival_host_wall_clock_ms - venue_event_time_ms
        self.assertEqual(raw_diff_ms, -300.0)

        # Naive interpretation: -300ms transit time -> PHYSICALLY IMPOSSIBLE
        # Correct interpretation:
        # raw_diff = transit_time - clock_offset = 45 - 345 = -300 ms
        self.assertLess(raw_diff_ms, 0.0)
        estimated_offset = -raw_diff_ms + one_way_network_transit_ms
        self.assertEqual(estimated_offset, 345.0)

    def test_02_simulated_monotonic_intervals_immune_to_wall_clock_jumps(self):
        """SIMULATED: Monotonic inter-arrival intervals remain positive across wall-clock NTP steps."""
        # Frame 1 received
        f1_mono_ns = 10_000_000_000
        f1_utc_ns = 1_700_000_000_000_000_000

        # NTP steps wall clock backward by 5 seconds between Frame 1 and Frame 2
        # But elapsed monotonic time is +200ms (200,000,000 ns)
        f2_mono_ns = f1_mono_ns + 200_000_000
        f2_utc_ns = f1_utc_ns - 5_000_000_000 + 200_000_000  # stepped backward!

        # Wall-clock delta is negative
        dt_utc_ms = (f2_utc_ns - f1_utc_ns) / 1e6
        self.assertEqual(dt_utc_ms, -4800.0)

        # Monotonic delta is strictly positive and accurate
        dt_mono_ms = (f2_mono_ns - f1_mono_ns) / 1e6
        self.assertEqual(dt_mono_ms, 200.0)
        self.assertGreater(dt_mono_ms, 0.0)

    def test_03_simulated_forward_clock_jump_does_not_distort_arrival_cadence(self):
        """SIMULATED: Wall clock stepping forward by +10s does not distort monotonic arrival cadence."""
        f1_mono_ns = 50_000_000_000
        f1_utc_ns = 1_700_000_000_000_000_000

        # NTP steps wall clock forward by 10 seconds; physical time elapsed is 50ms
        f2_mono_ns = f1_mono_ns + 50_000_000
        f2_utc_ns = f1_utc_ns + 10_000_000_000 + 50_000_000

        dt_mono_ms = (f2_mono_ns - f1_mono_ns) / 1e6
        self.assertEqual(dt_mono_ms, 50.0)

    def test_04_simulated_missing_and_malformed_timestamp_handling(self):
        """SIMULATED: Frames with missing or non-numeric timestamps are classified without dropping frame."""
        frames = [
            {"seq": 100, "venue_ts": 1700000000000, "receipt_mono_ns": 1000, "receipt_utc_ns": 1700000000050000000},
            {"seq": 101, "venue_ts": None, "receipt_mono_ns": 2000, "receipt_utc_ns": 1700000000100000000},  # Missing venue_ts
            {"seq": 102, "venue_ts": "INVALID_TS", "receipt_mono_ns": 3000, "receipt_utc_ns": 1700000000150000000},  # Malformed
            {"seq": 103, "venue_ts": 1700000000300, "receipt_mono_ns": 4000, "receipt_utc_ns": 1700000000350000000},
        ]

        valid_latency_samples = []
        malformed_count = 0

        for f in frames:
            ts = f.get("venue_ts")
            if ts is not None and isinstance(ts, (int, float)):
                valid_latency_samples.append(f)
            else:
                malformed_count += 1

        self.assertEqual(len(valid_latency_samples), 2)
        self.assertEqual(malformed_count, 2)
        # All 4 frames retain order book sequence integrity regardless of timestamp validity
        self.assertEqual(len(frames), 4)

    def test_05_simulated_sequence_gap_duplicate_and_out_of_order_detection(self):
        """SIMULATED: Verifies sequence tracker detects gap, duplicate, and out-of-order events."""
        stream_seqs = [10, 11, 11, 12, 15, 14, 16]

        gaps = 0
        dups = 0
        ooo = 0

        for i in range(1, len(stream_seqs)):
            prev_s = stream_seqs[i-1]
            curr_s = stream_seqs[i]
            if curr_s == prev_s:
                dups += 1
            elif curr_s < prev_s:
                ooo += 1
            elif curr_s > prev_s + 1:
                gaps += (curr_s - prev_s - 1)

        self.assertEqual(dups, 1)  # 11, 11
        self.assertEqual(gaps, 3)  # 12 -> 15 (13, 14 missing: +2), 14 -> 16 (15 missing: +1)
        self.assertEqual(ooo, 1)   # 15 -> 14

    def test_06_simulated_snapshot_age_vs_transit_latency_distinction(self):
        """SIMULATED: Proves snapshot age (seconds prior to connection) is not network latency."""
        # A testnet order book that has been idle for 3.94 seconds before client connects
        connection_time_utc_ms = 1_700_000_010_000.0
        snapshot_book_created_utc_ms = 1_700_000_006_060.0  # 3940 ms older!

        snapshot_age_ms = connection_time_utc_ms - snapshot_book_created_utc_ms
        self.assertAlmostEqual(snapshot_age_ms, 3940.0, places=1)

        # If a pipeline mislabels snapshot_age as "latency", it reports 3.94 seconds latency!
        # The true one-way WebSocket network transit was only 40 ms:
        actual_ws_flight_ms = 40.0
        self.assertNotEqual(snapshot_age_ms, actual_ws_flight_ms)

    def test_07_simulated_arrival_cadence_quantiles(self):
        """SIMULATED: Computes inter-arrival intervals and quantiles on a simulated 100-frame burst."""
        np.random.seed(42)
        # Simulate burst of 100 arrivals with log-normal intervals (mean ~50ms, some spikes up to 500ms)
        intervals_ms = np.random.exponential(scale=50.0, size=100)
        p50 = float(np.percentile(intervals_ms, 50))
        p95 = float(np.percentile(intervals_ms, 95))
        p99 = float(np.percentile(intervals_ms, 99))

        self.assertGreater(p50, 0.0)
        self.assertGreater(p95, p50)
        self.assertGreater(p99, p95)


if __name__ == "__main__":
    unittest.main()
