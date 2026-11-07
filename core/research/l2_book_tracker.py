"""
QuantEngine Phase 190 — Deterministic L2 Order Book Tracker & State Machine.

Maintains an explicit L2 book validity state machine:
  INITIALIZING -> VALID -> STALE / SEQUENCE_GAP / INVALID -> RESYNCING -> VALID

Rules:
  1. Monotonic sequence gap detection: seq == expected_seq, else SEQUENCE_GAP.
  2. Duplicate and out-of-order sequence detection.
  3. Crossed book detection: best_bid >= best_ask invalidates the book.
  4. Strict decimal pricing and size preservation.
  5. Timestamp tracking: venue event time vs local receive time (latency distribution).
  6. Top-of-book depth and spread distribution tracking.
  7. Explicit denominators for all coverage, gap, and quality metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple


class BookValidityState(str, Enum):
    INITIALIZING = "INITIALIZING"
    VALID = "VALID"
    STALE = "STALE"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    DISCONNECTED = "DISCONNECTED"
    RESYNCING = "RESYNCING"
    INVALID = "INVALID"


@dataclass
class L2GapRecord:
    symbol: str
    expected_seq: int
    received_seq: int
    gap_size: int
    timestamp_utc_ns: int
    receipt_mono_ns: int


@dataclass
class L2BookMetrics:
    total_messages: int = 0
    valid_updates: int = 0
    gap_count: int = 0
    duplicate_count: int = 0
    out_of_order_count: int = 0
    resync_count: int = 0
    stale_count: int = 0
    crossed_book_count: int = 0
    malformed_count: int = 0
    rejected_count: int = 0
    first_observed_utc_ns: Optional[int] = None
    last_observed_utc_ns: Optional[int] = None
    first_observed_mono_ns: Optional[int] = None
    last_observed_mono_ns: Optional[int] = None
    min_spread_usd: Optional[Decimal] = None
    max_spread_usd: Optional[Decimal] = None
    sum_spread_usd: Decimal = Decimal("0")
    spread_samples: int = 0
    sum_top_bid_depth: Decimal = Decimal("0")
    sum_top_ask_depth: Decimal = Decimal("0")
    depth_samples: int = 0
    min_receive_latency_ms: Optional[float] = None
    max_receive_latency_ms: Optional[float] = None
    sum_receive_latency_ms: float = 0.0
    latency_samples: int = 0
    latency_history: List[float] = field(default_factory=list)
    raw_clock_diff_history: List[float] = field(default_factory=list)
    inter_arrival_mono_ms_history: List[float] = field(default_factory=list)
    inter_arrival_exchange_ms_history: List[float] = field(default_factory=list)


def _calc_percentile(data: List[float], p: float) -> Optional[float]:
    """Calculate exact empirical percentile from list."""
    if not data:
        return None
    sorted_d = sorted(data)
    idx = int(round(p * (len(sorted_d) - 1)))
    return round(sorted_d[idx], 3)


class L2BookTracker:
    """Deterministic, sequence-validated L2 order book tracker."""

    def __init__(
        self,
        symbol: str,
        stale_threshold_seconds: float = 5.0,
        tick_size: Optional[Decimal] = None,
        price_precision: Optional[int] = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.stale_threshold_seconds = stale_threshold_seconds
        self.tick_size = tick_size
        self.price_precision = price_precision
        
        self.state: BookValidityState = BookValidityState.INITIALIZING
        self.bids: Dict[Decimal, Decimal] = {}  # price -> size
        self.asks: Dict[Decimal, Decimal] = {}  # price -> size
        
        self.last_sequence: Optional[int] = None
        self.last_venue_timestamp_us: Optional[int] = None
        self.last_receipt_mono_ns: Optional[int] = None
        self.last_receipt_utc_ns: Optional[int] = None
        self.last_bid_mono_ns: Optional[int] = None
        self.last_ask_mono_ns: Optional[int] = None
        
        self.gaps: List[L2GapRecord] = []
        self.metrics = L2BookMetrics()
        self.state_history: List[Tuple[float, BookValidityState, str]] = []
        self._record_state_change(BookValidityState.INITIALIZING, "Tracker created")

    def _record_state_change(self, new_state: BookValidityState, reason: str) -> None:
        if self.state != new_state:
            self.state = new_state
            self.state_history.append((time.time(), new_state, reason))

    def reset(self, reason: str = "Manual reset") -> None:
        """Reset book to initializing state upon disconnect or unrecoverable gap."""
        self.bids.clear()
        self.asks.clear()
        self.last_sequence = None
        self.last_bid_mono_ns = None
        self.last_ask_mono_ns = None
        self.metrics.resync_count += 1
        self._record_state_change(BookValidityState.RESYNCING, reason)

    def process_snapshot(
        self,
        bids: List[List[Any]],
        asks: List[List[Any]],
        sequence: int,
        venue_timestamp_us: int,
        receipt_mono_ns: Optional[int] = None,
        receipt_utc_ns: Optional[int] = None,
    ) -> bool:
        """Initialize or resynchronize book from full L2 snapshot."""
        now_mono = receipt_mono_ns if receipt_mono_ns is not None else time.monotonic_ns()
        now_utc = receipt_utc_ns if receipt_utc_ns is not None else time.time_ns()
        
        self._record_timestamps(now_utc, now_mono)
        self.metrics.total_messages += 1
        self.metrics.resync_count += 1

        self.bids.clear()
        self.asks.clear()
        if bids:
            self.last_bid_mono_ns = now_mono
        if asks:
            self.last_ask_mono_ns = now_mono
        
        try:
            for p_str, q_str in bids:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if q > Decimal("0"):
                    self.bids[p] = q
                    
            for p_str, q_str in asks:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if q > Decimal("0"):
                    self.asks[p] = q
        except Exception:
            self.metrics.malformed_count += 1
            self.metrics.rejected_count += 1
            self._record_state_change(BookValidityState.INVALID, "Malformed snapshot price/size")
            return False

        self.last_sequence = sequence
        self.last_venue_timestamp_us = venue_timestamp_us
        self.last_receipt_mono_ns = now_mono
        self.last_receipt_utc_ns = now_utc

        # Validate book integrity
        if not self._validate_book_integrity():
            self.metrics.rejected_count += 1
            return False

        self._record_state_change(BookValidityState.VALID, f"Snapshot loaded at seq {sequence}")
        self.metrics.valid_updates += 1
        self._update_telemetry(now_utc, venue_timestamp_us, now_mono)
        return True

    def process_update(
        self,
        bids: List[List[Any]],
        asks: List[List[Any]],
        sequence: int,
        venue_timestamp_us: int,
        receipt_mono_ns: Optional[int] = None,
        receipt_utc_ns: Optional[int] = None,
    ) -> bool:
        """Apply incremental L2 book delta with strict sequence validation."""
        now_mono = receipt_mono_ns if receipt_mono_ns is not None else time.monotonic_ns()
        now_utc = receipt_utc_ns if receipt_utc_ns is not None else time.time_ns()
        self._record_timestamps(now_utc, now_mono)
        self.metrics.total_messages += 1

        # Check if initialized
        if self.last_sequence is None or self.state in (BookValidityState.INITIALIZING, BookValidityState.RESYNCING):
            if len(bids) > 5 and len(asks) > 5:
                return self.process_snapshot(bids, asks, sequence, venue_timestamp_us, now_mono, now_utc)
            self.metrics.rejected_count += 1
            self._record_state_change(
                BookValidityState.INVALID,
                f"Delta update received at seq {sequence} before initial snapshot"
            )
            return False

        # Duplicate check
        if sequence == self.last_sequence:
            self.metrics.duplicate_count += 1
            self.metrics.rejected_count += 1
            return False

        # Out-of-order check
        if sequence < self.last_sequence:
            self.metrics.out_of_order_count += 1
            self.metrics.rejected_count += 1
            self._record_state_change(
                BookValidityState.SEQUENCE_GAP,
                f"Out-of-order update received: got {sequence} < last {self.last_sequence}"
            )
            return False

        # Sequence gap check
        expected_seq = self.last_sequence + 1
        if sequence != expected_seq:
            gap_size = sequence - expected_seq
            self.metrics.gap_count += 1
            self.metrics.rejected_count += 1
            gap_rec = L2GapRecord(
                symbol=self.symbol,
                expected_seq=expected_seq,
                received_seq=sequence,
                gap_size=gap_size,
                timestamp_utc_ns=now_utc,
                receipt_mono_ns=now_mono,
            )
            self.gaps.append(gap_rec)
            self._record_state_change(
                BookValidityState.SEQUENCE_GAP,
                f"Sequence gap detected: expected {expected_seq}, got {sequence} (delta={gap_size})"
            )
            return False

        # Apply updates
        try:
            for p_str, q_str in bids:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if q <= Decimal("0"):
                    self.bids.pop(p, None)
                else:
                    self.bids[p] = q
            if bids:
                self.last_bid_mono_ns = now_mono

            for p_str, q_str in asks:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if q <= Decimal("0"):
                    self.asks.pop(p, None)
                else:
                    self.asks[p] = q
            if asks:
                self.last_ask_mono_ns = now_mono
        except Exception:
            self.metrics.malformed_count += 1
            self.metrics.rejected_count += 1
            self._record_state_change(BookValidityState.INVALID, "Malformed update price/size")
            return False

        self.last_sequence = sequence
        self.last_venue_timestamp_us = venue_timestamp_us
        self.last_receipt_mono_ns = now_mono
        self.last_receipt_utc_ns = now_utc

        # Validate book integrity
        if not self._validate_book_integrity():
            self.metrics.rejected_count += 1
            return False

        if self.state != BookValidityState.VALID:
            self._record_state_change(BookValidityState.VALID, "Incremental update validated")

        self.metrics.valid_updates += 1
        self._update_telemetry(now_utc, venue_timestamp_us, now_mono)
        return True

    def _record_timestamps(self, utc_ns: int, mono_ns: int) -> None:
        if self.metrics.first_observed_utc_ns is None:
            self.metrics.first_observed_utc_ns = utc_ns
            self.metrics.first_observed_mono_ns = mono_ns
        self.metrics.last_observed_utc_ns = utc_ns
        self.metrics.last_observed_mono_ns = mono_ns

    def _validate_book_integrity(self) -> bool:
        """Check for crossed books, non-positive levels, empty sides, or tick-size violations."""
        bb = self.best_bid()
        ba = self.best_ask()
        
        if bb is None or ba is None:
            self._record_state_change(BookValidityState.INVALID, "Empty bid or ask book")
            return False

        if bb <= Decimal("0") or ba <= Decimal("0"):
            self._record_state_change(BookValidityState.INVALID, f"Non-positive touch prices: bid={bb}, ask={ba}")
            return False

        if bb >= ba:
            self.metrics.crossed_book_count += 1
            self._record_state_change(
                BookValidityState.INVALID,
                f"Crossed book detected: best_bid ({bb}) >= best_ask ({ba})"
            )
            return False

        if self.tick_size is not None and self.tick_size > Decimal("0"):
            if (bb % self.tick_size != Decimal("0")) or (ba % self.tick_size != Decimal("0")):
                self._record_state_change(
                    BookValidityState.INVALID,
                    f"Price level does not align with tick size {self.tick_size}: bid={bb}, ask={ba}"
                )
                return False

        if self.best_bid_size() <= Decimal("0") or self.best_ask_size() <= Decimal("0"):
            self._record_state_change(BookValidityState.INVALID, "Zero size at top of book")
            return False

        return True

    def check_staleness(self, current_mono_ns: Optional[int] = None) -> bool:
        """Evaluate if book has become stale based on elapsed monotonic time."""
        if self.last_receipt_mono_ns is None:
            return True
        now_mono = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        elapsed_sec = (now_mono - self.last_receipt_mono_ns) / 1_000_000_000.0
        
        if elapsed_sec > self.stale_threshold_seconds:
            if self.state == BookValidityState.VALID:
                self.metrics.stale_count += 1
                self._record_state_change(
                    BookValidityState.STALE,
                    f"No updates received for {elapsed_sec:.2f}s (threshold={self.stale_threshold_seconds}s)"
                )
            return True

        # Side-specific staleness (e.g. stale bid side with fresh ask side)
        if self.last_bid_mono_ns is not None:
            bid_elapsed = (now_mono - self.last_bid_mono_ns) / 1_000_000_000.0
            if bid_elapsed > self.stale_threshold_seconds:
                if self.state == BookValidityState.VALID:
                    self.metrics.stale_count += 1
                    self._record_state_change(
                        BookValidityState.STALE,
                        f"Bid side is stale (no bid updates for {bid_elapsed:.2f}s > {self.stale_threshold_seconds}s)"
                    )
                return True

        if self.last_ask_mono_ns is not None:
            ask_elapsed = (now_mono - self.last_ask_mono_ns) / 1_000_000_000.0
            if ask_elapsed > self.stale_threshold_seconds:
                if self.state == BookValidityState.VALID:
                    self.metrics.stale_count += 1
                    self._record_state_change(
                        BookValidityState.STALE,
                        f"Ask side is stale (no ask updates for {ask_elapsed:.2f}s > {self.stale_threshold_seconds}s)"
                    )
                return True

        return False

    def is_execution_eligible(self, current_mono_ns: Optional[int] = None) -> Tuple[bool, List[str]]:
        """Evaluate explicit execution eligibility conditions for the order book.
        
        Guarantees:
          - Initial snapshot received and successfully parsed (last_sequence is not None).
          - Book state is strictly VALID (not INITIALIZING, STALE, SEQUENCE_GAP, RESYNCING, INVALID, or DISCONNECTED).
          - Freshness verified using local monotonic time (not stale).
          - Valid, non-empty bid and ask levels with positive prices.
          - Strictly positive spread (best_ask > best_bid); crossed and locked books rejected.
          - Depth presence at touch (best_bid_size > 0 and best_ask_size > 0).
          - No unresolved sequence gaps.
        """
        reasons: List[str] = []
        if self.state != BookValidityState.VALID:
            reasons.append(f"Book validity state is {self.state.value} (must be VALID)")
        if self.last_sequence is None:
            reasons.append("No valid snapshot or sequence initialized")
        
        # Staleness check
        if self.check_staleness(current_mono_ns):
            reasons.append(f"Book is stale (elapsed > {self.stale_threshold_seconds}s)")
            
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            reasons.append("Order book has empty bid or ask side")
        else:
            if bb <= Decimal("0") or ba <= Decimal("0"):
                reasons.append(f"Non-positive top of book: bid={bb}, ask={ba}")
            if bb >= ba:
                reasons.append(f"Crossed or locked book: best_bid ({bb}) >= best_ask ({ba})")
                
        bbs = self.best_bid_size()
        bas = self.best_ask_size()
        if bbs <= Decimal("0") or bas <= Decimal("0"):
            reasons.append(f"Zero liquidity at touch: bid_size={bbs}, ask_size={bas}")
            
        if self.metrics.gap_count > 0 and self.state != BookValidityState.VALID:
            reasons.append(f"Unresolved sequence gaps: {self.metrics.gap_count}")
            
        return len(reasons) == 0, reasons

    @property
    def execution_eligible(self) -> bool:
        eligible, _ = self.is_execution_eligible()
        return eligible

    def _update_telemetry(self, receipt_utc_ns: int, venue_ts_us: int, receipt_mono_ns: Optional[int] = None) -> None:
        """Update latency, spread, and top-of-book depth running statistics."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            spread = ba - bb
            self.metrics.sum_spread_usd += spread
            self.metrics.spread_samples += 1
            if self.metrics.min_spread_usd is None or spread < self.metrics.min_spread_usd:
                self.metrics.min_spread_usd = spread
            if self.metrics.max_spread_usd is None or spread > self.metrics.max_spread_usd:
                self.metrics.max_spread_usd = spread

            # Top depth
            self.metrics.sum_top_bid_depth += self.best_bid_size()
            self.metrics.sum_top_ask_depth += self.best_ask_size()
            self.metrics.depth_samples += 1

        # Unfiltered raw clock difference (host UTC minus venue event time; exposes clock skew)
        venue_ns = venue_ts_us * 1000
        raw_clock_diff_ms = (receipt_utc_ns - venue_ns) / 1_000_000.0
        if len(self.metrics.raw_clock_diff_history) < 50_000:
            self.metrics.raw_clock_diff_history.append(raw_clock_diff_ms)

        # Monotonic inter-arrival time (local socket reading interval, unaffected by clock skew)
        if receipt_mono_ns is not None and self.last_receipt_mono_ns is not None:
            inter_mono_ms = (receipt_mono_ns - self.last_receipt_mono_ns) / 1_000_000.0
            if 0.0 <= inter_mono_ms <= 60_000.0 and len(self.metrics.inter_arrival_mono_ms_history) < 50_000:
                self.metrics.inter_arrival_mono_ms_history.append(inter_mono_ms)

        # Venue inter-event delta
        if self.last_venue_timestamp_us is not None:
            venue_delta_ms = (venue_ts_us - self.last_venue_timestamp_us) / 1_000.0
            if venue_delta_ms >= 0.0 and len(self.metrics.inter_arrival_exchange_ms_history) < 50_000:
                self.metrics.inter_arrival_exchange_ms_history.append(venue_delta_ms)

        # Filtered positive transit latency (only populated when local clock >= venue clock)
        if 0.0 <= raw_clock_diff_ms <= 60_000.0:
            self.metrics.sum_receive_latency_ms += raw_clock_diff_ms
            self.metrics.latency_samples += 1
            if len(self.metrics.latency_history) < 50_000:
                self.metrics.latency_history.append(raw_clock_diff_ms)
            if self.metrics.min_receive_latency_ms is None or raw_clock_diff_ms < self.metrics.min_receive_latency_ms:
                self.metrics.min_receive_latency_ms = raw_clock_diff_ms
            if self.metrics.max_receive_latency_ms is None or raw_clock_diff_ms > self.metrics.max_receive_latency_ms:
                self.metrics.max_receive_latency_ms = raw_clock_diff_ms

    def best_bid(self) -> Optional[Decimal]:
        return max(self.bids.keys()) if self.bids else None

    def best_ask(self) -> Optional[Decimal]:
        return min(self.asks.keys()) if self.asks else None

    def best_bid_size(self) -> Decimal:
        bb = self.best_bid()
        return self.bids.get(bb, Decimal("0")) if bb else Decimal("0")

    def best_ask_size(self) -> Decimal:
        ba = self.best_ask()
        return self.asks.get(ba, Decimal("0")) if ba else Decimal("0")

    def spread(self) -> Optional[Decimal]:
        bb = self.best_bid()
        ba = self.best_ask()
        return (ba - bb) if (bb is not None and ba is not None) else None

    def depth_top_n(self, n: int = 5) -> Dict[str, List[Tuple[str, str]]]:
        """Return top N price levels for bids and asks."""
        sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:n]
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return {
            "bids": [(str(p), str(q)) for p, q in sorted_bids],
            "asks": [(str(p), str(q)) for p, q in sorted_asks],
        }

    def summary_dict(self) -> Dict[str, Any]:
        """Return comprehensive machine-readable summary of book state and quality metrics."""
        avg_spread = (
            str((self.metrics.sum_spread_usd / Decimal(str(self.metrics.spread_samples))).quantize(Decimal("0.0001")))
            if self.metrics.spread_samples > 0 else None
        )
        avg_latency = (
            round(self.metrics.sum_receive_latency_ms / self.metrics.latency_samples, 2)
            if self.metrics.latency_samples > 0 else None
        )
        valid_coverage_pct = (
            round((self.metrics.valid_updates / self.metrics.total_messages) * 100.0, 2)
            if self.metrics.total_messages > 0 else 0.0
        )
        avg_top_bid_depth = (
            str((self.metrics.sum_top_bid_depth / Decimal(str(self.metrics.depth_samples))).quantize(Decimal("0.0001")))
            if self.metrics.depth_samples > 0 else None
        )
        avg_top_ask_depth = (
            str((self.metrics.sum_top_ask_depth / Decimal(str(self.metrics.depth_samples))).quantize(Decimal("0.0001")))
            if self.metrics.depth_samples > 0 else None
        )

        first_utc_iso = (
            datetime.fromtimestamp(self.metrics.first_observed_utc_ns / 1_000_000_000.0, tz=timezone.utc).isoformat()
            if self.metrics.first_observed_utc_ns else None
        )
        last_utc_iso = (
            datetime.fromtimestamp(self.metrics.last_observed_utc_ns / 1_000_000_000.0, tz=timezone.utc).isoformat()
            if self.metrics.last_observed_utc_ns else None
        )

        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "last_sequence": self.last_sequence,
            "first_observed_utc": first_utc_iso,
            "last_observed_utc": last_utc_iso,
            "total_messages": self.metrics.total_messages,
            "valid_updates": self.metrics.valid_updates,
            "valid_coverage_pct": valid_coverage_pct,
            "gap_count": self.metrics.gap_count,
            "duplicate_count": self.metrics.duplicate_count,
            "out_of_order_count": self.metrics.out_of_order_count,
            "resync_count": self.metrics.resync_count,
            "stale_count": self.metrics.stale_count,
            "crossed_book_count": self.metrics.crossed_book_count,
            "malformed_count": self.metrics.malformed_count,
            "rejected_count": self.metrics.rejected_count,
            "best_bid": str(self.best_bid()) if self.best_bid() else None,
            "best_ask": str(self.best_ask()) if self.best_ask() else None,
            "spread": str(self.spread()) if self.spread() else None,
            "avg_spread_usd": avg_spread,
            "min_spread_usd": str(self.metrics.min_spread_usd) if self.metrics.min_spread_usd else None,
            "max_spread_usd": str(self.metrics.max_spread_usd) if self.metrics.max_spread_usd else None,
            "avg_top_bid_depth": avg_top_bid_depth,
            "avg_top_ask_depth": avg_top_ask_depth,
            "avg_latency_ms": avg_latency,
            "min_latency_ms": self.metrics.min_receive_latency_ms,
            "max_latency_ms": self.metrics.max_receive_latency_ms,
            "median_latency_ms": _calc_percentile(self.metrics.latency_history, 0.50),
            "p95_latency_ms": _calc_percentile(self.metrics.latency_history, 0.95),
            "p99_latency_ms": _calc_percentile(self.metrics.latency_history, 0.99),
            "clock_offset_median_ms": _calc_percentile(self.metrics.raw_clock_diff_history, 0.50),
            "clock_offset_p95_ms": _calc_percentile(self.metrics.raw_clock_diff_history, 0.95),
            "clock_offset_p99_ms": _calc_percentile(self.metrics.raw_clock_diff_history, 0.99),
            "clock_diff_samples": len(self.metrics.raw_clock_diff_history),
            "inter_arrival_mono_median_ms": _calc_percentile(self.metrics.inter_arrival_mono_ms_history, 0.50),
            "inter_arrival_mono_p95_ms": _calc_percentile(self.metrics.inter_arrival_mono_ms_history, 0.95),
            "inter_arrival_mono_p99_ms": _calc_percentile(self.metrics.inter_arrival_mono_ms_history, 0.99),
            "clock_domain_notes": "raw_clock_diff reflects host UTC minus venue event time including clock skew. True network arrival dynamics are measured by monotonic inter-arrival times.",
            "metric_denominators": {
                "valid_coverage_pct": "valid_updates / total_messages * 100.0",
                "avg_spread_usd": "sum_spread_usd / spread_samples",
                "avg_top_bid_depth": "sum_top_bid_depth / depth_samples",
                "avg_top_ask_depth": "sum_top_ask_depth / depth_samples",
                "avg_latency_ms": "sum_receive_latency_ms / latency_samples",
                "continuity_claim_scope": "Valid strictly for observed frames in stream. A zero-gap count does NOT infer continuous venue-side coverage across unobserved disconnects.",
            }
        }
