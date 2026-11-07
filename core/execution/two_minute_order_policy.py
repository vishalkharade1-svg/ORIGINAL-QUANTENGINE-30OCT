"""
====================================================
QuantEngine - Two-Minute Order Fill & Timeout Policy
Phase 185 Implementation

Deterministic execution policy enforcing a 120-second timeout
on resting limit orders, with:
  * High-resolution monotonic clock measurement.
  * Partial-fill quantity accounting and remaining-only cancellation.
  * Strict race-condition handling (fill vs cancel).
  * Fail-closed unknown-order isolation & symbol-level halt.
  * Complete lifecycle timestamping (submit, ack, cancel, fill, reconcile).
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import time
from typing import Callable, Dict, List, Optional, Set

from core.common.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS: float = 120.0
NANOS_PER_SECOND: int = 1_000_000_000


class OrderTimeoutState(str, Enum):
    """Lifecycle states for timed limit orders."""
    SUBMITTED = "SUBMITTED"
    RESTING = "RESTING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    TIMED_OUT = "TIMED_OUT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    FILLED = "FILLED"
    UNKNOWN_RECONCILING = "UNKNOWN_RECONCILING"
    REJECTED = "REJECTED"


@dataclass
class MonotonicOrderTracker:
    """Tracks one limit order's monotonic lifecycle and timestamps."""
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    limit_price: Decimal
    total_quantity: Decimal
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    filled_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    remaining_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    state: OrderTimeoutState = OrderTimeoutState.SUBMITTED
    submission_mono_ns: int = field(default_factory=time.monotonic_ns)
    submission_utc_ts: float = field(default_factory=time.time)
    ack_utc_ts: Optional[float] = None
    cancel_request_mono_ns: Optional[int] = None
    cancel_ack_utc_ts: Optional[float] = None
    fill_utc_ts: Optional[float] = None
    reconciled_utc_ts: Optional[float] = None
    stop_price: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    average_fill_price: Optional[Decimal] = None
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.remaining_quantity <= Decimal("0"):
            self.remaining_quantity = self.total_quantity

    def is_terminal(self) -> bool:
        """True if order has reached a definitive terminal state."""
        return self.state in (
            OrderTimeoutState.CANCELLED,
            OrderTimeoutState.FILLED,
            OrderTimeoutState.REJECTED,
        )

    def is_timed_out(self, current_mono_ns: Optional[int] = None) -> bool:
        """Check if monotonic timeout deadline has elapsed."""
        if self.is_terminal():
            return False
        now_ns = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        elapsed_ns = now_ns - self.submission_mono_ns
        timeout_ns = int(self.timeout_seconds * NANOS_PER_SECOND)
        return elapsed_ns >= timeout_ns

    def elapsed_seconds(self, current_mono_ns: Optional[int] = None) -> float:
        """Compute monotonic seconds elapsed since submission."""
        now_ns = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        return (now_ns - self.submission_mono_ns) / NANOS_PER_SECOND

    def record_ack(self, ack_utc_ts: Optional[float] = None) -> None:
        """Record exchange order acknowledgement."""
        self.ack_utc_ts = ack_utc_ts if ack_utc_ts is not None else time.time()
        if self.state == OrderTimeoutState.SUBMITTED:
            self.state = OrderTimeoutState.RESTING
            self.notes.append(f"Acknowledged at UTC {self.ack_utc_ts}")

    def record_fill(
        self,
        qty: Decimal,
        fill_price: Decimal,
        fill_utc_ts: Optional[float] = None,
    ) -> None:
        """Record an execution fill, updating cumulative and remaining quantities."""
        now_ts = fill_utc_ts if fill_utc_ts is not None else time.time()
        self.filled_quantity += qty
        self.remaining_quantity = max(Decimal("0"), self.total_quantity - self.filled_quantity)
        self.average_fill_price = fill_price
        self.fill_utc_ts = now_ts

        if self.remaining_quantity == Decimal("0"):
            self.state = OrderTimeoutState.FILLED
            self.notes.append(f"Fully filled ({self.filled_quantity}) at price {fill_price}")
        else:
            self.state = OrderTimeoutState.PARTIALLY_FILLED
            self.notes.append(f"Partially filled (+{qty}, total={self.filled_quantity}, remaining={self.remaining_quantity})")

    def record_cancel_request(self, current_mono_ns: Optional[int] = None) -> None:
        """Record cancellation request dispatch."""
        self.cancel_request_mono_ns = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        self.state = OrderTimeoutState.CANCEL_REQUESTED
        self.notes.append("Cancel requested")

    def record_cancel_confirmed(self, cancel_utc_ts: Optional[float] = None) -> None:
        """Record exchange confirmation of order cancellation."""
        self.cancel_ack_utc_ts = cancel_utc_ts if cancel_utc_ts is not None else time.time()
        self.state = OrderTimeoutState.CANCELLED
        self.notes.append(f"Cancellation confirmed at UTC {self.cancel_ack_utc_ts}")

    def record_unknown_state(self, reason: str) -> None:
        """Mark order in unknown/ambiguous state requiring reconciliation."""
        self.state = OrderTimeoutState.UNKNOWN_RECONCILING
        self.notes.append(f"UNKNOWN_STATE: {reason}")


class TwoMinuteOrderPolicyManager:
    """Manages order timeouts, cancellations, and reconciliation fail-closed isolation."""

    def __init__(self, default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.default_timeout_seconds = default_timeout_seconds
        self._orders: Dict[str, MonotonicOrderTracker] = {}
        self._halted_symbols: Set[str] = set()

    def register_order(
        self,
        order_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        limit_price: Decimal,
        quantity: Decimal,
        stop_price: Optional[Decimal] = None,
        target_price: Optional[Decimal] = None,
        timeout_seconds: Optional[float] = None,
        submission_mono_ns: Optional[int] = None,
        submission_utc_ts: Optional[float] = None,
    ) -> MonotonicOrderTracker:
        """Register and begin tracking an order lifecycle."""
        sym_clean = symbol.upper()
        if sym_clean in self._halted_symbols:
            raise RuntimeError(f"Cannot submit order for halted symbol {sym_clean} (pending reconciliation)")

        t_sec = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        tracker = MonotonicOrderTracker(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=sym_clean,
            side=side.upper(),
            limit_price=limit_price,
            total_quantity=quantity,
            timeout_seconds=t_sec,
            submission_mono_ns=submission_mono_ns if submission_mono_ns is not None else time.monotonic_ns(),
            submission_utc_ts=submission_utc_ts if submission_utc_ts is not None else time.time(),
            stop_price=stop_price,
            target_price=target_price,
        )
        self._orders[order_id] = tracker
        log.info("Registered order %s for symbol %s (timeout: %.1fs)", order_id, sym_clean, t_sec)
        return tracker

    def get_order(self, order_id: str) -> Optional[MonotonicOrderTracker]:
        """Lookup order tracker by ID."""
        return self._orders.get(order_id)

    def is_symbol_halted(self, symbol: str) -> bool:
        """Return True if symbol is halted due to execution ambiguity."""
        return symbol.upper() in self._halted_symbols

    def halt_symbol(self, symbol: str, reason: str) -> None:
        """Halt new entries for symbol fail-closed."""
        sym_clean = symbol.upper()
        self._halted_symbols.add(sym_clean)
        log.warning("HALTED symbol %s: %s", sym_clean, reason)

    def clear_symbol_halt(self, symbol: str, reason: str) -> None:
        """Clear symbol halt after successful reconciliation."""
        sym_clean = symbol.upper()
        self._halted_symbols.discard(sym_clean)
        log.info("Cleared halt for symbol %s: %s", sym_clean, reason)

    def check_expired_orders(
        self,
        current_mono_ns: Optional[int] = None,
    ) -> List[MonotonicOrderTracker]:
        """Scan for resting/partial orders that have exceeded their timeout deadline."""
        now_ns = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        expired: List[MonotonicOrderTracker] = []
        for order in self._orders.values():
            if not order.is_terminal() and order.state not in (
                OrderTimeoutState.CANCEL_REQUESTED,
                OrderTimeoutState.UNKNOWN_RECONCILING,
            ):
                if order.is_timed_out(now_ns):
                    order.state = OrderTimeoutState.TIMED_OUT
                    expired.append(order)
        return expired

    def process_timeout(
        self,
        order_id: str,
        cancel_adapter_func: Optional[Callable[[str, Decimal], bool]] = None,
        current_mono_ns: Optional[int] = None,
    ) -> MonotonicOrderTracker:
        """Execute timeout cancellation procedure with safe partial fill handling."""
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"Order {order_id} not found in policy manager")

        now_ns = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        order.record_cancel_request(now_ns)

        if cancel_adapter_func is not None:
            try:
                # Cancel only the remaining unfilled quantity
                success = cancel_adapter_func(order.order_id, order.remaining_quantity)
                if success:
                    order.record_cancel_confirmed()
                else:
                    order.record_unknown_state("Adapter returned cancel failure / unknown")
                    self.halt_symbol(order.symbol, f"Order {order_id} cancel failed")
            except Exception as exc:
                order.record_unknown_state(f"Exception during cancel: {exc}")
                self.halt_symbol(order.symbol, f"Order {order_id} cancel error: {exc}")
        else:
            # Deterministic simulation / paper mode without network adapter
            order.record_cancel_confirmed()

        return order

    def reconcile_fill_and_cancel_race(
        self,
        order_id: str,
        exchange_cumulative_filled: Decimal,
        exchange_fill_price: Decimal,
        exchange_status: str,
    ) -> MonotonicOrderTracker:
        """Handle race condition where a fill occurred concurrently with or after cancel request."""
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"Order {order_id} not found")

        order.reconciled_utc_ts = time.time()
        qty_diff = exchange_cumulative_filled - order.filled_quantity

        if qty_diff > Decimal("0"):
            log.info("Reconciling fill race for %s: +%s executed at %s", order_id, qty_diff, exchange_fill_price)
            order.record_fill(qty_diff, exchange_fill_price)

        if exchange_status.upper() in ("CANCELLED", "CANCELED"):
            if order.remaining_quantity > Decimal("0"):
                order.record_cancel_confirmed()
        elif exchange_status.upper() in ("CLOSED", "FILLED") and order.remaining_quantity == Decimal("0"):
            order.state = OrderTimeoutState.FILLED

        return order
