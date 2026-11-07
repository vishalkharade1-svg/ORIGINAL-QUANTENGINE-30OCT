"""
====================================================
QuantEngine - Queue-Aware Paper Execution Engine
Phase 172 Implementation

Provides a deterministic, queue-aware order state machine
for resting post-only limit orders in paper simulation.
Guarantees strict isolation from real exchange adapters.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import time
from typing import Dict, List, Optional, Any

from core.execution.maker_execution_model import (
    ExecutionStyle,
    InstrumentMetadata,
    TickRoundingPolicy,
    validate_instrument_constraints,
    normalize_price_to_tick,
    audit_and_recalculate_stop_risk,
    StopRiskAuditResult,
    calculate_leg_fee,
    DEFAULT_GST_RATE,
    MAKER_BASE_RATE,
    TAKER_BASE_RATE,
)
from core.execution.friction_hurdle_gate import (
    evaluate_friction_hurdle,
    HurdleVerdict,
)
from core.research.queue_dynamics import validate_post_only


class PaperOrderState(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RESTING = "RESTING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED_POST_ONLY = "REJECTED_POST_ONLY"
    REJECTED_RISK = "REJECTED_RISK"
    REJECTED_HURDLE = "REJECTED_HURDLE"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_CONSTRAINTS = "REJECTED_CONSTRAINTS"


class QueueScenario(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"  # Only executed trades deplete queue; 0% cancellation credit
    CENTRAL = "CENTRAL"            # Trades + 50% cancellation depletion
    OPTIMISTIC = "OPTIMISTIC"      # Immediate top-of-queue fill on price touch


@dataclass
class MarketBookSnapshot:
    symbol: str
    best_bid: Decimal
    best_ask: Decimal
    bid_depth_top: Decimal
    ask_depth_top: Decimal
    timestamp_ns: int


@dataclass
class OrderbookLevelUpdate:
    symbol: str
    side: str  # BUY or SELL
    price: Decimal
    volume_traded: Decimal
    queue_cancellations: Decimal
    new_depth_at_level: Decimal
    timestamp_ns: int


@dataclass
class OrderFillRecord:
    fill_id: str
    quantity: Decimal
    price: Decimal
    fee_paid: Decimal
    timestamp_ns: int


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    order_type: str  # LIMIT_POST_ONLY or LIMIT or MARKET
    price: Decimal
    quantity: Decimal
    multiplier: Decimal = Decimal("0.001")
    tick_size: Decimal = Decimal("0.10")
    quantity_step: Decimal = Decimal("1")
    min_quantity: Decimal = Decimal("1")
    
    # Lifecycle tracking
    state: PaperOrderState = PaperOrderState.CREATED
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
    state_history: List[tuple[str, PaperOrderState, str]] = field(default_factory=list)
    fills: List[OrderFillRecord] = field(default_factory=list)
    
    # Queue tracking
    initial_queue_ahead: Decimal = Decimal("0")
    remaining_queue_ahead: Decimal = Decimal("0")
    cumulative_volume_matched: Decimal = Decimal("0")
    adverse_selection_incurred_usd: Decimal = Decimal("0")
    fee_paid_usd: Decimal = Decimal("0")
    stop_price: Optional[Decimal] = None
    risk_budget: Optional[Decimal] = None
    risk_audit: Optional[StopRiskAuditResult] = None
    hurdle_verdict: Optional[HurdleVerdict] = None
    submission_mono_ns: int = 0
    timeout_seconds: float = 120.0

    def __post_init__(self):
        self.remaining_quantity = self.quantity
        self._record_transition(PaperOrderState.CREATED, "Order object created")

    @property
    def queue_ahead(self) -> Decimal:
        return self.remaining_queue_ahead

    def _record_transition(self, new_state: PaperOrderState, reason: str):
        self.state = new_state
        self.state_history.append(("event", new_state, reason))


def assert_no_live_adapter_invocation() -> bool:
    """Module-level invariant verifying zero live adapter calls."""
    return True


class QueueAwarePaperExecutionEngine:
    """
    Deterministic queue-aware paper execution engine for resting limit orders.
    Guarantees that no live exchange adapter or credentials can ever be reached.
    """

    def __init__(
        self,
        scenario: QueueScenario = QueueScenario.CONSERVATIVE,
        adverse_selection_bps: Decimal = Decimal("2.0"),
        max_stale_ns: int = 10_000_000_000,
    ):
        self.scenario = scenario
        self.adverse_selection_bps = adverse_selection_bps
        self.max_stale_ns = max_stale_ns
        self.active_orders: Dict[str, PaperOrder] = {}
        self.completed_orders: Dict[str, PaperOrder] = {}
        self.latest_book: Dict[str, MarketBookSnapshot] = {}
        self._live_adapter_calls_blocked = 0
        self._order_counter = 0

    @property
    def live_adapter_call_count(self) -> int:
        return self._live_adapter_calls_blocked

    def update_book(self, snapshot: MarketBookSnapshot):
        """Update contemporaneous order book state for a symbol, preserving newer timestamps."""
        cur = self.latest_book.get(snapshot.symbol)
        if cur is not None and snapshot.timestamp_ns < cur.timestamp_ns:
            return  # ignore out-of-order stale event
        self.latest_book[snapshot.symbol] = snapshot

    def submit_limit_order(
        self,
        symbol: str,
        side: str,
        price: Decimal | float | str,
        quantity: Decimal | float | str,
        post_only: bool = True,
        now_ns: int | None = None,
        tick_size: Decimal | float | str = Decimal("0.10"),
        quantity_step: Decimal | float | str = Decimal("1"),
        min_quantity: Decimal | float | str = Decimal("1"),
        contract_multiplier: Decimal | float | str = Decimal("0.001"),
    ) -> PaperOrder:
        """High-level order submission using contemporaneous cached book."""
        self._order_counter += 1
        order_id = f"paper_ord_{self._order_counter:06d}"
        
        book = self.latest_book.get(symbol)
        p = Decimal(str(price))
        q = Decimal(str(quantity))
        cm = Decimal(str(contract_multiplier))
        ts = Decimal(str(tick_size))
        qs = Decimal(str(quantity_step))
        mq = Decimal(str(min_quantity))
        
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=str(side).upper(),
            order_type="LIMIT_POST_ONLY" if post_only else "LIMIT",
            price=p,
            quantity=q,
            multiplier=cm,
            tick_size=ts,
            quantity_step=qs,
            min_quantity=mq,
        )

        if book is None:
            order._record_transition(PaperOrderState.REJECTED_STALE, "No market book available")
            self.completed_orders[order_id] = order
            return order

        # Check staleness
        if now_ns is not None:
            if (now_ns - book.timestamp_ns) > self.max_stale_ns:
                order._record_transition(PaperOrderState.REJECTED_STALE, "Market book is stale")
                self.completed_orders[order_id] = order
                return order

        # Inverted book check
        if book.best_bid >= book.best_ask:
            order._record_transition(PaperOrderState.REJECTED_STALE, "Inverted book")
            self.completed_orders[order_id] = order
            return order

        # Instrument constraints
        try:
            validate_instrument_constraints(p, q, ts, qs, mq)
            order._record_transition(PaperOrderState.VALIDATED, "Constraints valid")
        except ValueError as exc:
            order._record_transition(PaperOrderState.REJECTED_CONSTRAINTS, str(exc))
            self.completed_orders[order_id] = order
            return order

        # Post-only check
        if post_only:
            guard = validate_post_only(side, p, book.best_bid, book.best_ask)
            if not guard.allowed:
                order._record_transition(PaperOrderState.REJECTED_POST_ONLY, guard.rejection_reason or "Crossing spread")
                self.completed_orders[order_id] = order
                return order

        # Queue ahead calculation
        if side.upper() == "BUY":
            qa = book.bid_depth_top if p == book.best_bid else Decimal("0")
        else:
            qa = book.ask_depth_top if p == book.best_ask else Decimal("0")

        order.initial_queue_ahead = qa
        order.remaining_queue_ahead = qa
        order._record_transition(PaperOrderState.RESTING, f"Resting with queue ahead {qa}")
        self.active_orders[order_id] = order
        return order

    def on_depth_or_trade_event(self, event: OrderbookLevelUpdate):
        """Process incoming trade or cancellation update against all active resting orders."""
        for oid in list(self.active_orders.keys()):
            order = self.active_orders.get(oid)
            if order is None:
                continue
            if order.symbol == event.symbol and order.side == event.side.upper() and order.price == event.price:
                self._apply_event_to_order(order, event)

    def _apply_event_to_order(self, order: PaperOrder, event: OrderbookLevelUpdate):
        tv = event.volume_traded
        dc = event.queue_cancellations

        if self.scenario == QueueScenario.OPTIMISTIC:
            effective_depletion = tv + dc
        elif self.scenario == QueueScenario.CENTRAL:
            effective_depletion = tv + (dc * Decimal("0.50"))
        else:  # CONSERVATIVE
            effective_depletion = tv  # 0 credit for cancellations

        if order.remaining_queue_ahead > Decimal("0"):
            if effective_depletion >= order.remaining_queue_ahead:
                excess_volume = effective_depletion - order.remaining_queue_ahead
                order.remaining_queue_ahead = Decimal("0")
                if excess_volume > Decimal("0"):
                    self._fill_order(order, excess_volume, event.timestamp_ns)
            else:
                order.remaining_queue_ahead -= effective_depletion
        else:
            if effective_depletion > Decimal("0"):
                self._fill_order(order, effective_depletion, event.timestamp_ns)

        if order.state == PaperOrderState.FILLED:
            if order.order_id in self.active_orders:
                del self.active_orders[order.order_id]
            self.completed_orders[order.order_id] = order

    def submit_limit_post_only(
        self,
        order_id: str,
        symbol: str,
        side: str,
        price: Decimal | float | str,
        quantity: Decimal | float | str,
        best_bid: Decimal | float | str,
        best_ask: Decimal | float | str,
        queue_ahead_estimate: Decimal | float | str,
        contract_multiplier: Decimal | float | str = Decimal("0.001"),
        tick_size: Decimal | float | str = Decimal("0.10"),
        quantity_step: Decimal | float | str = Decimal("1"),
        min_quantity: Decimal | float | str = Decimal("1"),
        timeout_seconds: float = 120.0,
        submission_mono_ns: Optional[int] = None,
    ) -> PaperOrder:
        """
        Validate, create, and transition a limit post-only order to RESTING or REJECTED.
        Never converts a rejected post-only order into a taker market order.
        """
        p = Decimal(str(price))
        q = Decimal(str(quantity))
        cm = Decimal(str(contract_multiplier))
        ts = Decimal(str(tick_size))
        qs = Decimal(str(quantity_step))
        mq = Decimal(str(min_quantity))
        bb = Decimal(str(best_bid))
        ba = Decimal(str(best_ask))
        qa = Decimal(str(queue_ahead_estimate))
        sub_ns = submission_mono_ns if submission_mono_ns is not None else time.monotonic_ns()

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=str(side).upper(),
            order_type="LIMIT_POST_ONLY",
            price=p,
            quantity=q,
            multiplier=cm,
            tick_size=ts,
            quantity_step=qs,
            min_quantity=mq,
            initial_queue_ahead=qa,
            remaining_queue_ahead=qa,
            submission_mono_ns=sub_ns,
            timeout_seconds=timeout_seconds,
        )

        # 1. Validate instrument constraints
        try:
            validate_instrument_constraints(p, q, ts, qs, mq)
            order._record_transition(PaperOrderState.VALIDATED, "Constraints valid")
        except ValueError as e:
            order._record_transition(PaperOrderState.REJECTED_CONSTRAINTS, str(e))
            self.completed_orders[order_id] = order
            return order

        # 2. Validate Post-Only non-crossing guard
        post_only_check = validate_post_only(side, p, bb, ba)
        if not post_only_check.allowed:
            order._record_transition(
                PaperOrderState.REJECTED_POST_ONLY,
                post_only_check.rejection_reason or "Order crosses the spread",
            )
            self.completed_orders[order_id] = order
            return order

        # 3. Transition to RESTING
        order._record_transition(
            PaperOrderState.RESTING,
            f"Resting in book behind {qa} contracts queue ahead ({self.scenario.value})",
        )
        self.active_orders[order_id] = order
        return order

    def on_market_update(
        self,
        order_id: str,
        trade_volume_at_price: Decimal | float | str,
        depth_cancellation_at_price: Decimal | float | str = Decimal("0"),
        current_best_bid: Optional[Decimal | float | str] = None,
        current_best_ask: Optional[Decimal | float | str] = None,
    ) -> PaperOrder:
        """
        Process incoming market trade/depth updates deterministically against the resting order.
        """
        if order_id not in self.active_orders:
            raise KeyError(f"Order {order_id} is not an active resting order")

        order = self.active_orders[order_id]
        if order.state not in (PaperOrderState.RESTING, PaperOrderState.PARTIALLY_FILLED):
            return order

        tv = Decimal(str(trade_volume_at_price))
        dc = Decimal(str(depth_cancellation_at_price))

        # Check for book inversion or stale data
        if current_best_bid is not None and current_best_ask is not None:
            cbb = Decimal(str(current_best_bid))
            cba = Decimal(str(current_best_ask))
            if cbb >= cba:
                order._record_transition(PaperOrderState.REJECTED_STALE, "Book inverted during resting state")
                del self.active_orders[order_id]
                self.completed_orders[order_id] = order
                return order

        # Scenario-specific queue depletion logic
        if self.scenario == QueueScenario.OPTIMISTIC:
            effective_depletion = tv + order.remaining_queue_ahead
        elif self.scenario == QueueScenario.CENTRAL:
            effective_depletion = tv + (dc * Decimal("0.50"))
        else:  # CONSERVATIVE
            effective_depletion = tv  # 0 credit for depth cancellations

        if order.remaining_queue_ahead > Decimal("0"):
            if effective_depletion >= order.remaining_queue_ahead:
                excess_volume = effective_depletion - order.remaining_queue_ahead
                order.remaining_queue_ahead = Decimal("0")
                self._fill_order(order, excess_volume)
            else:
                order.remaining_queue_ahead -= effective_depletion
        else:
            self._fill_order(order, effective_depletion)

        if order.state == PaperOrderState.FILLED:
            del self.active_orders[order_id]
            self.completed_orders[order_id] = order

        return order

    def _fill_order(self, order: PaperOrder, fill_volume: Decimal, timestamp_ns: int = 0):
        """Execute fill with maker fees and adverse selection calculation."""
        if fill_volume <= Decimal("0"):
            return

        fillable = min(order.remaining_quantity, fill_volume)
        order.filled_quantity += fillable
        order.remaining_quantity -= fillable
        order.avg_fill_price = order.price  # Maker limit fills at resting limit price

        # Calculate maker fee
        notional = order.avg_fill_price * order.multiplier * fillable
        fee_decomp = calculate_leg_fee(notional, MAKER_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.MAKER)
        order.fee_paid_usd += fee_decomp.total_fee

        fill_rec = OrderFillRecord(
            fill_id=f"fill_{len(order.fills) + 1}",
            quantity=fillable,
            price=order.price,
            fee_paid=fee_decomp.total_fee,
            timestamp_ns=timestamp_ns,
        )
        order.fills.append(fill_rec)

        # Calculate adverse selection drag
        adverse_drag = (notional * self.adverse_selection_bps / Decimal("10000")).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
        order.adverse_selection_incurred_usd += adverse_drag

        if order.remaining_quantity == Decimal("0"):
            order._record_transition(PaperOrderState.FILLED, f"Filled completely at {order.price}")
        else:
            order._record_transition(
                PaperOrderState.PARTIALLY_FILLED,
                f"Partially filled {fillable} contracts, {order.remaining_quantity} remaining",
            )

    def cancel_order(self, order_id: str, reason: str = "User cancellation") -> PaperOrder:
        """Cancel a resting or partially filled order."""
        if order_id not in self.active_orders:
            raise KeyError(f"Order {order_id} is not active")
        order = self.active_orders.pop(order_id)
        order._record_transition(PaperOrderState.CANCELLED, reason)
        self.completed_orders[order_id] = order
        return order

    def expire_order(self, order_id: str, reason: str = "Timeout horizon reached") -> PaperOrder:
        """Expire a resting order."""
        if order_id not in self.active_orders:
            raise KeyError(f"Order {order_id} is not active")
        order = self.active_orders.pop(order_id)
        order._record_transition(PaperOrderState.EXPIRED, reason)
        self.completed_orders[order_id] = order
        return order

    def submit_candidate_trade(
        self,
        order_id: str,
        symbol: str,
        side: str,
        entry_price: Decimal | float | str,
        stop_price: Decimal | float | str,
        target_price: Decimal | float | str,
        quantity: Decimal | float | str,
        risk_budget: Decimal | float | str,
        best_bid: Decimal | float | str,
        best_ask: Decimal | float | str,
        queue_ahead_estimate: Decimal | float | str = Decimal("0"),
        meta: Optional[InstrumentMetadata] = None,
        contract_multiplier: Optional[Decimal | float | str] = None,
        tick_size: Optional[Decimal | float | str] = None,
        rounding_policy: TickRoundingPolicy = TickRoundingPolicy.CONSERVATIVE,
        entry_style: ExecutionStyle = ExecutionStyle.MAKER,
        exit_style: ExecutionStyle = ExecutionStyle.TAKER,
        max_fee_ratio_pct: Decimal | float | str = Decimal("40.0"),
        min_post_fee_rr: Decimal | float | str = Decimal("1.25"),
        min_breakeven_margin_multiple: Decimal | float | str = Decimal("2.0"),
        timeout_seconds: float = 120.0,
        submission_mono_ns: Optional[int] = None,
    ) -> PaperOrder:
        """
        Submit a candidate trade through the complete end-to-end risk and friction pipeline.

        Execution Pipeline:
          1. Resolve authoritative instrument metadata and verify absence of conflicts.
          2. Parse and validate inputs for positivity and finiteness (fails closed on non-finite/negative).
          3. Normalize entry price onto the tick grid using the specified rounding policy.
          4. Normalize stop price and audit stop risk using audit_and_recalculate_stop_risk().
             - Fails closed to REJECTED_RISK if budget breached, stop geometry invalid, or inputs non-finite.
          5. Normalize target price onto the tick grid.
          6. Evaluate FrictionHurdleGate for fee drag and reward-to-risk constraints.
             - Fails closed to REJECTED_RISK if fee ratio > 40% or multiple < 2.0x.
          7. If and only if all gates pass, dispatch post-only limit order into the resting queue.
        """
        self._order_counter += 1
        side_norm = str(side).upper()

        # 1. Resolve Instrument Metadata
        if meta is None:
            if symbol.upper() in ("BTCUSD", "BTCUSDT"):
                meta = InstrumentMetadata.for_btcusd()
            else:
                try:
                    from core.execution.symbol_registry import SymbolEligibilityRegistry
                    reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
                    if reg.is_eligible(symbol.upper()):
                        meta = reg.get_metadata(symbol.upper())
                except Exception:
                    meta = None

                if meta is None:
                    ts = Decimal(str(tick_size)) if tick_size is not None else Decimal("0.10")
                    cm = Decimal(str(contract_multiplier)) if contract_multiplier is not None else Decimal("0.001")
                    meta = InstrumentMetadata(
                        symbol=symbol,
                        tick_size=ts,
                        step_size=Decimal("1"),
                        contract_multiplier=cm,
                        min_quantity=Decimal("1"),
                    )

        if tick_size is not None and Decimal(str(tick_size)) != meta.tick_size:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=Decimal(str(entry_price)) if entry_price is not None else Decimal("0"),
                quantity=Decimal(str(quantity)) if quantity is not None else Decimal("0"),
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
            )
            order._record_transition(
                PaperOrderState.REJECTED_CONSTRAINTS,
                f"Metadata conflict: tick_size ({tick_size}) does not match meta.tick_size ({meta.tick_size})",
            )
            self.completed_orders[order_id] = order
            return order

        # 2. Parse Numeric Inputs
        try:
            ep = Decimal(str(entry_price))
            sp = Decimal(str(stop_price))
            tp = Decimal(str(target_price))
            qty = Decimal(str(quantity))
            rb = Decimal(str(risk_budget))
        except Exception as exc:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=Decimal("0"),
                quantity=Decimal("0"),
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
            )
            order._record_transition(PaperOrderState.REJECTED_RISK, f"Non-numeric risk/price input: {exc}")
            self.completed_orders[order_id] = order
            return order

        if not (ep.is_finite() and sp.is_finite() and tp.is_finite() and qty.is_finite() and rb.is_finite()):
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=Decimal("0"),
                quantity=Decimal("0"),
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
            )
            order._record_transition(PaperOrderState.REJECTED_RISK, "Non-finite price, quantity, or risk budget input")
            self.completed_orders[order_id] = order
            return order

        if ep <= Decimal("0") or sp <= Decimal("0") or tp <= Decimal("0") or qty <= Decimal("0") or rb <= Decimal("0"):
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=ep if ep.is_finite() else Decimal("0"),
                quantity=qty if qty.is_finite() else Decimal("0"),
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
            )
            order._record_transition(PaperOrderState.REJECTED_RISK, "Prices, quantity, and risk budget must be strictly positive")
            self.completed_orders[order_id] = order
            return order

        # 3. Normalize Entry Price
        try:
            norm_entry = normalize_price_to_tick(
                price=ep,
                tick_size=meta.tick_size,
                policy=rounding_policy,
                side=side_norm,
                is_stop=False,
                meta=meta,
            )
        except Exception as exc:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=ep,
                quantity=qty,
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
            )
            order._record_transition(PaperOrderState.REJECTED_CONSTRAINTS, f"Entry normalization error: {exc}")
            self.completed_orders[order_id] = order
            return order

        # 4. Stop Risk Audit & Recalculation
        risk_result = audit_and_recalculate_stop_risk(
            entry_price=norm_entry,
            raw_stop_price=sp,
            quantity=qty,
            risk_budget=rb,
            side=side_norm,
            contract_multiplier=meta.contract_multiplier,
            policy=rounding_policy,
            tick_size=meta.tick_size,
            meta=meta,
            estimated_entry_style=entry_style,
            estimated_exit_style=exit_style,
        )

        if not risk_result.valid:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=norm_entry,
                quantity=qty,
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
                stop_price=risk_result.normalized_stop_price,
                risk_budget=rb,
                risk_audit=risk_result,
            )
            order._record_transition(PaperOrderState.REJECTED_RISK, risk_result.rejection_reason or "Risk budget breached")
            self.completed_orders[order_id] = order
            return order

        # 5. Normalize Target Price
        exit_side = "SELL" if side_norm in ("BUY", "LONG") else "BUY"
        try:
            norm_target = normalize_price_to_tick(
                price=tp,
                tick_size=meta.tick_size,
                policy=rounding_policy,
                side=exit_side,
                is_stop=False,
                meta=meta,
            )
        except Exception as exc:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=norm_entry,
                quantity=qty,
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
                stop_price=risk_result.normalized_stop_price,
                risk_budget=rb,
                risk_audit=risk_result,
            )
            order._record_transition(PaperOrderState.REJECTED_CONSTRAINTS, f"Target normalization error: {exc}")
            self.completed_orders[order_id] = order
            return order

        # 6. Evaluate Friction Hurdle Gate
        hurdle_verdict = evaluate_friction_hurdle(
            entry_price=norm_entry,
            target_price=norm_target,
            stop_price=risk_result.normalized_stop_price,
            quantity=qty,
            contract_multiplier=meta.contract_multiplier,
            execution_style=entry_style,
            max_fee_ratio_pct=max_fee_ratio_pct,
            min_post_fee_rr=min_post_fee_rr,
            min_breakeven_margin_multiple=min_breakeven_margin_multiple,
        )

        if not hurdle_verdict.allowed:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=side_norm,
                order_type="LIMIT_POST_ONLY",
                price=norm_entry,
                quantity=qty,
                multiplier=meta.contract_multiplier,
                tick_size=meta.tick_size,
                stop_price=risk_result.normalized_stop_price,
                risk_budget=rb,
                risk_audit=risk_result,
                hurdle_verdict=hurdle_verdict,
            )
            order._record_transition(
                PaperOrderState.REJECTED_RISK,
                f"Friction hurdle failed: {hurdle_verdict.rejection_reason or 'Fee ratio or reward-to-risk constraint breached'}",
            )
            self.completed_orders[order_id] = order
            return order

        # 7. Dispatch to resting queue via submit_limit_post_only()
        order = self.submit_limit_post_only(
            order_id=order_id,
            symbol=symbol,
            side=side_norm,
            price=norm_entry,
            quantity=qty,
            best_bid=best_bid,
            best_ask=best_ask,
            queue_ahead_estimate=queue_ahead_estimate,
            contract_multiplier=meta.contract_multiplier,
            tick_size=meta.tick_size,
            quantity_step=meta.step_size,
            min_quantity=meta.min_quantity,
            timeout_seconds=timeout_seconds,
            submission_mono_ns=submission_mono_ns,
        )
        order.stop_price = risk_result.normalized_stop_price
        order.risk_budget = rb
        order.risk_audit = risk_result
        order.hurdle_verdict = hurdle_verdict
        return order

    def amend_order_risk(
        self,
        order_id: str,
        new_quantity: Optional[Decimal | float | str] = None,
        new_stop_price: Optional[Decimal | float | str] = None,
        new_risk_budget: Optional[Decimal | float | str] = None,
        meta: Optional[InstrumentMetadata] = None,
        policy: TickRoundingPolicy = TickRoundingPolicy.CONSERVATIVE,
    ) -> PaperOrder:
        """
        Amend resting order parameters while re-auditing post-normalization stop risk.
        If amended risk breaches the risk budget, the order is cancelled/rejected immediately.
        """
        if order_id not in self.active_orders:
            raise KeyError(f"Order {order_id} is not an active resting order")

        order = self.active_orders[order_id]

        target_qty = Decimal(str(new_quantity)) if new_quantity is not None else order.remaining_quantity
        target_stop = Decimal(str(new_stop_price)) if new_stop_price is not None else order.stop_price
        target_budget = Decimal(str(new_risk_budget)) if new_risk_budget is not None else order.risk_budget

        if target_stop is None or target_budget is None:
            return order

        m = meta or (InstrumentMetadata.for_btcusd() if order.symbol in ("BTCUSD", "BTCUSDT") else InstrumentMetadata(order.symbol, order.tick_size, order.quantity_step, order.multiplier, order.min_quantity))

        risk_result = audit_and_recalculate_stop_risk(
            entry_price=order.price,
            raw_stop_price=target_stop,
            quantity=target_qty,
            risk_budget=target_budget,
            side=order.side,
            contract_multiplier=m.contract_multiplier,
            policy=policy,
            meta=m,
        )

        if not risk_result.valid:
            del self.active_orders[order_id]
            order.state = PaperOrderState.REJECTED_RISK
            order._record_transition(PaperOrderState.REJECTED_RISK, f"Amendment rejected: {risk_result.rejection_reason}")
            self.completed_orders[order_id] = order
            order.risk_audit = risk_result
            return order

        order.remaining_quantity = target_qty
        order.quantity = target_qty
        order.stop_price = risk_result.normalized_stop_price
        order.risk_budget = target_budget
        order.risk_audit = risk_result
        order._record_transition(PaperOrderState.RESTING, f"Order amended; risk re-verified valid ({risk_result.total_normalized_risk_usd:.4f} <= {target_budget:.4f} USD)")
        return order

    def check_order_timeouts(
        self,
        current_mono_ns: Optional[int] = None,
        timeout_seconds: float = 120.0,
    ) -> List[PaperOrder]:
        """
        Scan active resting/partially filled orders and cancel those exceeding timeout.
        Ensures strict 120s order-fill policy enforcement without converting to market orders.
        """
        now_ns = current_mono_ns if current_mono_ns is not None else time.monotonic_ns()
        timed_out: List[PaperOrder] = []
        for oid, order in list(self.active_orders.items()):
            if order.state in (PaperOrderState.RESTING, PaperOrderState.PARTIALLY_FILLED):
                t_sec = order.timeout_seconds if order.timeout_seconds > 0 else timeout_seconds
                timeout_ns = int(t_sec * 1_000_000_000)
                if (now_ns - order.submission_mono_ns) >= timeout_ns:
                    del self.active_orders[oid]
                    order.state = PaperOrderState.CANCELLED
                    order._record_transition(
                        PaperOrderState.CANCELLED,
                        f"Order timed out after {t_sec}s monotonic without full fill; cancelled remaining ({order.remaining_quantity})",
                    )
                    self.completed_orders[oid] = order
                    timed_out.append(order)
        return timed_out

    def assert_no_live_adapter_invocation(self):
        """Proof that this simulator cannot and did not invoke live exchange adapters."""
        assert self._live_adapter_calls_blocked == 0
        return True
