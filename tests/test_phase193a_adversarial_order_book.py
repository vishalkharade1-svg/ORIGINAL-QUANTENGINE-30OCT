"""
Phase 193A — Deterministic Adversarial Order Book Test Suite.

Audits explicit order-book validity conditions and state machine transitions:
- Valid snapshot followed by valid updates.
- Delta received before snapshot.
- Missing sequence.
- Duplicate update.
- Out-of-order update.
- Reconnect with a new snapshot.
- Partial snapshot or malformed payload.
- Crossed book from inconsistent local state.
- Genuine transient crossed-book observation.
- Stale bid side with fresh ask side.
- Invalid or missing price fields.
- Decimal precision and tick-size edge cases.
- Timestamp clock jump.
- No messages during configured freshness interval.
- Repeated invalid updates.
- Recovery after a validity failure.
- Execution signal generated while book is invalid.

ALL SYNTHETIC SCENARIOS ARE LABELED: SIMULATED.
"""

from decimal import Decimal
import pytest
import time
from typing import List

from core.research.l2_book_tracker import L2BookTracker, BookValidityState


class StrictNoWriteMockExchange:
    """Mock exchange adapter that raises immediately if any write method is invoked."""
    def place_order(self, *args, **kwargs):
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: place_order called on strict mock!")

    def cancel_order(self, *args, **kwargs):
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: cancel_order called on strict mock!")

    def modify_order(self, *args, **kwargs):
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: modify_order called on strict mock!")


def test_valid_snapshot_followed_by_valid_updates():
    """Verify normal lifecycle: snapshot -> updates -> execution eligible."""
    tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=5.0)
    assert tracker.state == BookValidityState.INITIALIZING
    assert not tracker.execution_eligible

    # 1. Snapshot
    snap_ok = tracker.process_snapshot(
        bids=[["80000.0", "1.5"], ["79990.0", "2.0"]],
        asks=[["80010.0", "1.2"], ["80020.0", "3.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=100_000_000,
        receipt_utc_ns=1_000_000_000,
    )
    assert snap_ok
    assert tracker.state == BookValidityState.VALID
    eligible, reasons = tracker.is_execution_eligible(current_mono_ns=100_000_000)
    assert eligible
    assert len(reasons) == 0
    assert tracker.best_bid() == Decimal("80000.0")
    assert tracker.best_ask() == Decimal("80010.0")
    assert tracker.spread() == Decimal("10.0")

    # 2. Incremental update
    upd_ok = tracker.process_update(
        bids=[["80005.0", "0.5"]],
        asks=[["80015.0", "1.0"]],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=200_000_000,
        receipt_utc_ns=1_100_000_000,
    )
    assert upd_ok
    assert tracker.state == BookValidityState.VALID
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=200_000_000)
    assert eligible
    assert tracker.best_bid() == Decimal("80005.0")
    assert tracker.best_ask() == Decimal("80010.0")


def test_delta_received_before_snapshot():
    """SIMULATED: Incremental delta arriving before snapshot must be rejected and invalidate book."""
    tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=5.0)
    assert tracker.state == BookValidityState.INITIALIZING

    # Attempt incremental delta without initial snapshot
    ok = tracker.process_update(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=50,
        venue_timestamp_us=1_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.INVALID
    assert not tracker.execution_eligible
    eligible, reasons = tracker.is_execution_eligible()
    assert not eligible
    assert any("must be VALID" in r or "No valid snapshot" in r for r in reasons)


def test_missing_sequence_triggers_gap_and_ineligibility():
    """SIMULATED: Sequence jump from 100 to 105 must trigger SEQUENCE_GAP and refuse execution."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0)
    assert eligible

    # Gap: jump to 105
    ok = tracker.process_update(
        bids=[["80001.0", "1.0"]],
        asks=[],
        sequence=105,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 100_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.SEQUENCE_GAP
    assert tracker.metrics.gap_count == 1
    eligible, reasons = tracker.is_execution_eligible(current_mono_ns=t0 + 100_000_000)
    assert not eligible
    assert any("SEQUENCE_GAP" in r for r in reasons)


def test_duplicate_update_rejected():
    """SIMULATED: Receiving same sequence twice must reject duplicate without corrupting book."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    # Valid update
    ok1 = tracker.process_update(
        bids=[["80002.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
    )
    assert ok1
    assert tracker.best_bid() == Decimal("80002.0")

    # Duplicate sequence 101 with conflicting price
    ok2 = tracker.process_update(
        bids=[["80009.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_150_000,
        receipt_mono_ns=t0 + 60_000_000,
    )
    assert not ok2
    assert tracker.metrics.duplicate_count == 1
    # Book must retain original 80002.0, not the duplicate 80009.0
    assert tracker.best_bid() == Decimal("80002.0")


def test_out_of_order_update_triggers_gap_and_ineligibility():
    """SIMULATED: Sequence decreasing must trigger SEQUENCE_GAP and block execution."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    tracker.process_update(
        bids=[["80001.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
    )
    # Out of order: seq 99 arrives after 101
    ok = tracker.process_update(
        bids=[["80003.0", "1.0"]],
        asks=[],
        sequence=99,
        venue_timestamp_us=1_200_000,
        receipt_mono_ns=t0 + 100_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.SEQUENCE_GAP
    assert tracker.metrics.out_of_order_count == 1
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0 + 100_000_000)
    assert not eligible


def test_reconnect_with_new_snapshot_recovers_validity():
    """SIMULATED: Transport disconnect -> reset() -> new snapshot successfully restores VALID state."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0)
    assert eligible

    # Transport disconnect event
    tracker.reset(reason="Transport reconnect")
    assert tracker.state == BookValidityState.RESYNCING
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0)
    assert not eligible
    assert len(tracker.bids) == 0
    assert len(tracker.asks) == 0

    # New snapshot on reconnected socket
    ok = tracker.process_snapshot(
        bids=[["80050.0", "2.0"]],
        asks=[["80060.0", "1.5"]],
        sequence=200,
        venue_timestamp_us=2_000_000,
        receipt_mono_ns=t0 + 500_000_000,
    )
    assert ok
    assert tracker.state == BookValidityState.VALID
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0 + 500_000_000)
    assert eligible
    assert tracker.best_bid() == Decimal("80050.0")


def test_partial_snapshot_or_malformed_payload_rejected():
    """SIMULATED: Empty bid side or unparseable price string must transition to INVALID."""
    tracker = L2BookTracker("BTCUSD")
    # Empty asks in snapshot
    ok = tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.INVALID
    assert not tracker.execution_eligible

    # Malformed price string
    tracker2 = L2BookTracker("BTCUSD")
    ok2 = tracker2.process_snapshot(
        bids=[["NOT_A_PRICE", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    assert not ok2
    assert tracker2.state == BookValidityState.INVALID
    assert tracker2.metrics.malformed_count == 1
    assert not tracker2.execution_eligible


def test_crossed_book_from_inconsistent_local_state():
    """SIMULATED: Bid submitted >= best ask must trigger crossed book INVALID state immediately."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    # Bid update crosses the ask (80015.0 > 80010.0)
    ok = tracker.process_update(
        bids=[["80015.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.INVALID
    assert tracker.metrics.crossed_book_count == 1
    eligible, reasons = tracker.is_execution_eligible(current_mono_ns=t0 + 50_000_000)
    assert not eligible
    assert any("Crossed or locked book" in r or "must be VALID" in r for r in reasons)


def test_transient_crossed_book_blocks_execution_until_cleared():
    """SIMULATED: Transient crossed state blocks execution; clearing update restores VALID."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0)
    assert eligible

    # 1. Update crosses book
    ok1 = tracker.process_update(
        bids=[["80012.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
    )
    assert not ok1
    assert tracker.state == BookValidityState.INVALID
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0 + 50_000_000)
    assert not eligible

    # 2. Subsequent update cancels the crossed bid level (qty='0')
    ok2 = tracker.process_update(
        bids=[["80012.0", "0"]],
        asks=[],
        sequence=102,
        venue_timestamp_us=1_200_000,
        receipt_mono_ns=t0 + 100_000_000,
    )
    assert ok2
    assert tracker.state == BookValidityState.VALID
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0 + 100_000_000)
    assert eligible
    assert tracker.best_bid() == Decimal("80000.0")
    assert tracker.best_ask() == Decimal("80010.0")


def test_stale_bid_side_with_fresh_ask_side_blocks_execution():
    """SIMULATED: If bids receive no updates for > stale_threshold, book must report STALE and block."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=2.0)
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )

    # Continually update only asks up to t=2.5s later (bid timestamp remains at t0)
    t_later = t0 + 2_500_000_000  # 2.5s later
    tracker.process_update(
        bids=[],
        asks=[["80012.0", "1.0"]],
        sequence=101,
        venue_timestamp_us=2_000_000,
        receipt_mono_ns=t_later,
    )
    # Check at t_later: bid side has elapsed 2.5s > 2.0s
    eligible, reasons = tracker.is_execution_eligible(current_mono_ns=t_later)
    assert not eligible
    assert any("stale" in r.lower() for r in reasons)


def test_invalid_or_missing_price_fields_rejected():
    """SIMULATED: Negative or zero touch prices fail closed."""
    tracker = L2BookTracker("BTCUSD")
    ok = tracker.process_snapshot(
        bids=[["-500.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.INVALID
    assert not tracker.execution_eligible


def test_decimal_precision_and_tick_size_edge_cases():
    """SIMULATED: Prices not aligning with instrument tick size are rejected."""
    # BTCUSD tick size is 0.5
    tracker = L2BookTracker("BTCUSD", tick_size=Decimal("0.5"))
    # 80000.23 is not a multiple of 0.5
    ok = tracker.process_snapshot(
        bids=[["80000.23", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    assert not ok
    assert tracker.state == BookValidityState.INVALID
    assert not tracker.execution_eligible


def test_timestamp_clock_jump_handling_simulated():
    """SIMULATED: Host clock jumps forward or backward must not corrupt monotonic sequence tracking."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
        receipt_utc_ns=1_000_000_000,
    )
    # Wall clock jumps backward by 100 seconds, but monotonic clock increments normally
    ok = tracker.process_update(
        bids=[["80001.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
        receipt_utc_ns=900_000_000,  # wall clock stepped backwards
    )
    assert ok
    assert tracker.state == BookValidityState.VALID
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0 + 50_000_000)
    assert eligible


def test_no_messages_during_freshness_interval_triggers_stale():
    """SIMULATED: Book with no updates beyond stale_threshold transitions to STALE."""
    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=1.0)
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    eligible, _ = tracker.is_execution_eligible(current_mono_ns=t0)
    assert eligible

    # Query at t = t0 + 1.5s
    eligible, reasons = tracker.is_execution_eligible(current_mono_ns=t0 + 1_500_000_000)
    assert not eligible
    assert tracker.state == BookValidityState.STALE
    assert any("stale" in r.lower() for r in reasons)


def test_repeated_invalid_updates_fail_closed():
    """SIMULATED: Multiple consecutive malformed updates do not cause crash or state leak."""
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    for i in range(5):
        ok = tracker.process_update(
            bids=[["BAD_DATA", "1.0"]],
            asks=[],
            sequence=101,
            venue_timestamp_us=1_100_000 + i * 1000,
        )
        assert not ok
        assert tracker.state == BookValidityState.INVALID
        assert not tracker.execution_eligible
    assert tracker.metrics.malformed_count == 5


def test_recovery_after_validity_failure():
    """SIMULATED: A book invalidated by crossed delta recovers cleanly upon receiving a fresh snapshot."""
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    # Cross it
    tracker.process_update(
        bids=[["80020.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
    )
    assert tracker.state == BookValidityState.INVALID
    assert not tracker.execution_eligible

    # Reset and feed new clean snapshot
    tracker.reset(reason="Re-synchronizing after cross")
    assert tracker.state == BookValidityState.RESYNCING
    ok = tracker.process_snapshot(
        bids=[["80010.0", "1.0"]],
        asks=[["80025.0", "1.0"]],
        sequence=200,
        venue_timestamp_us=2_000_000,
    )
    assert ok
    assert tracker.state == BookValidityState.VALID
    assert tracker.execution_eligible


def test_execution_signal_blocked_when_book_invalid():
    """SIMULATED: Synthetic execution signal cannot proceed if book tracker is invalid or crossed."""
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
    )
    # Book is crossed
    tracker.process_update(
        bids=[["80015.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
    )
    assert not tracker.execution_eligible

    mock_exchange = StrictNoWriteMockExchange()
    # Attempting to execute an order signal when book is ineligible must fail closed
    def try_execute_order():
        if not tracker.execution_eligible:
            raise RuntimeError("EXECUTION_REFUSED: Market data book is invalid")
        mock_exchange.place_order({"symbol": "BTCUSD", "size": 1})

    with pytest.raises(RuntimeError, match="EXECUTION_REFUSED: Market data book is invalid"):
        try_execute_order()
