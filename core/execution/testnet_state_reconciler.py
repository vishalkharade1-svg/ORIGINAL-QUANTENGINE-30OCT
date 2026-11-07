"""
====================================================
QuantEngine - Testnet State Reconciliation Engine
Phase 191 Implementation

Audits and reconciles local persistent ledger state against authoritative
exchange REST/WebSocket order and fill records.

Enforces fail-closed posture:
  - Detects unknown exchange orders, missing records, contradictions, and late fills.
  - Guarantees risk is NEVER released for unresolved orders.
  - Sanitizes credentials from all traces and audit records.
  - Zero exchange order writes permitted.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.common.logging_config import get_logger
from core.execution.testnet_authorization_gate import (
    OrderLifecycleState,
    ORDER_STATE_CANONICAL_MAP,
)
from core.execution.testnet_safety_gate import TestnetSafetyError

log = get_logger(__name__)


class ReconciliationAnomalyType(str, Enum):
    """Specific categories of state divergence between local ledger and exchange."""
    NONE = "NONE"
    MISSING_FROM_EXCHANGE = "MISSING_FROM_EXCHANGE"
    UNKNOWN_EXCHANGE_ORDER = "UNKNOWN_EXCHANGE_ORDER"
    CONTRADICTORY_RECORD = "CONTRADICTORY_RECORD"
    DELAYED_FILL_POST_CANCEL = "DELAYED_FILL_POST_CANCEL"
    PARTIAL_FILL_DETECTED = "PARTIAL_FILL_DETECTED"
    ENDPOINT_UNAVAILABLE = "ENDPOINT_UNAVAILABLE"
    DUPLICATE_EXCHANGE_RECORD = "DUPLICATE_EXCHANGE_RECORD"
    UNRESOLVED_LOCAL_RESERVATION = "UNRESOLVED_LOCAL_RESERVATION"
    OVERFILL_DETECTED = "OVERFILL_DETECTED"
    INCOMPLETE_QUERY_RESPONSE = "INCOMPLETE_QUERY_RESPONSE"
    DUPLICATE_FILL_EVENT = "DUPLICATE_FILL_EVENT"


class ReconciliationStatus(str, Enum):
    """Aggregate verdict of the reconciliation engine."""
    CLEAN = "CLEAN"
    AMBIGUOUS = "AMBIGUOUS"
    DIVERGENT = "DIVERGENT"
    BLOCKED = "BLOCKED"


@dataclass
class ReconciledOrderRecord:
    """Detailed reconciliation verdict for an individual order."""
    cl_ord_id: str
    exchange_order_id: Optional[int | str]
    local_state: OrderLifecycleState
    exchange_state: Optional[str]
    local_qty: Decimal
    exchange_filled_qty: Decimal
    exchange_remaining_qty: Decimal
    reconciled_state: OrderLifecycleState
    anomalies: List[ReconciliationAnomalyType] = field(default_factory=list)
    risk_released: bool = False
    unfilled_quota_released: bool = False
    position_exposure_held: bool = False
    position_exposure_qty: Decimal = Decimal("0.0")
    notes: List[str] = field(default_factory=list)


@dataclass
class ReconciliationReport:
    """Comprehensive, verifiable reconciliation audit report."""
    status: ReconciliationStatus
    timestamp_utc: float
    total_local_orders: int
    total_exchange_orders: int
    total_exchange_fills: int
    reconciled_orders: Dict[str, ReconciledOrderRecord]
    anomalies: List[Dict[str, Any]]
    execution_permitted: bool
    reasons: List[str]

    def is_clean(self) -> bool:
        return self.status == ReconciliationStatus.CLEAN and self.execution_permitted


def redact_sensitive_data(text: str) -> str:
    """Sanitize API keys, secrets, auth headers, and signature tokens."""
    if not isinstance(text, str):
        text = str(text)
    patterns = [
        (r"(api[_-]?key[\"'\s:=]+)[a-zA-Z0-9_\-\.]{8,}", r"\1[REDACTED_KEY]"),
        (r"(api[_-]?secret[\"'\s:=]+)[a-zA-Z0-9_\-\.]{8,}", r"\1[REDACTED_SECRET]"),
        (r"(signature[\"'\s:=]+)[a-fA-F0-9]{16,}", r"\1[REDACTED_SIGNATURE]"),
        (r"(authorization[\"'\s:=]+Bearer\s+)[a-zA-Z0-9_\-\.]{16,}", r"\1[REDACTED_TOKEN]"),
    ]
    redacted = text
    for pat, repl in patterns:
        redacted = re.sub(pat, repl, redacted, flags=re.IGNORECASE)
    return redacted


class TestnetStateReconciler:
    """Deterministic bidirectional reconciler between local ledger and exchange state."""
    __test__ = False

    def __init__(self, reservation_grace_period_seconds: float = 30.0):
        self.reservation_grace_period_seconds = float(reservation_grace_period_seconds)

    def reconcile(
        self,
        local_orders: Dict[str, Dict[str, Any]],
        exchange_orders: Optional[List[Dict[str, Any]]] = None,
        exchange_fills: Optional[List[Dict[str, Any]]] = None,
        endpoint_error: Optional[Exception | str] = None,
        query_is_authoritative: bool = True,
    ) -> ReconciliationReport:
        """Perform full bidirectional reconciliation between local state and exchange records.

        Guarantees:
          - If endpoint_error is present (e.g. REST timeout, 503, connection dropped),
            reconciliation fails closed with BLOCKED status and allows zero orders.
          - If query_is_authoritative is False (e.g. paginated, filtered, or partial response),
            missing orders remain in RECONCILIATION_REQUIRED and execution is BLOCKED.
          - Detects missing orders, unknown exchange orders, contradictions, late fills, overfills.
          - Deduplicates duplicate REST/stream fill events, preventing double-counting of volume.
          - Ensures risk and position exposures are accounted for independently.
        """
        now = time.time()
        reasons: List[str] = []
        anomalies_list: List[Dict[str, Any]] = []
        reconciled_dict: Dict[str, ReconciledOrderRecord] = {}

        # 1. Endpoint availability check
        if endpoint_error is not None:
            err_msg = redact_sensitive_data(str(endpoint_error))
            reasons.append(f"Exchange REST endpoint unavailable or timed out: {err_msg}")
            anomalies_list.append({
                "type": ReconciliationAnomalyType.ENDPOINT_UNAVAILABLE.value,
                "error": err_msg,
            })
            # Mark all unresolved local orders as RECONCILIATION_REQUIRED, never releasing risk
            for cl_id, l_data in local_orders.items():
                l_state = l_data.get("state", OrderLifecycleState.SUBMISSION_UNKNOWN)
                if isinstance(l_state, str):
                    try:
                        l_state = OrderLifecycleState(l_state)
                    except ValueError:
                        l_state = OrderLifecycleState.RECONCILIATION_REQUIRED
                reconciled_dict[cl_id] = ReconciledOrderRecord(
                    cl_ord_id=cl_id,
                    exchange_order_id=l_data.get("exchange_order_id"),
                    local_state=l_state,
                    exchange_state=None,
                    local_qty=Decimal(str(l_data.get("order_size", l_data.get("qty", "1.0")))),
                    exchange_filled_qty=Decimal("0.0"),
                    exchange_remaining_qty=Decimal("0.0"),
                    reconciled_state=OrderLifecycleState.RECONCILIATION_REQUIRED,
                    anomalies=[ReconciliationAnomalyType.ENDPOINT_UNAVAILABLE],
                    risk_released=False,
                    unfilled_quota_released=False,
                    position_exposure_held=False,
                    position_exposure_qty=Decimal("0.0"),
                    notes=["Blocked by endpoint failure"],
                )
            return ReconciliationReport(
                status=ReconciliationStatus.BLOCKED,
                timestamp_utc=now,
                total_local_orders=len(local_orders),
                total_exchange_orders=0,
                total_exchange_fills=0,
                reconciled_orders=reconciled_dict,
                anomalies=anomalies_list,
                execution_permitted=False,
                reasons=reasons,
            )

        if not query_is_authoritative:
            anomalies_list.append({
                "type": ReconciliationAnomalyType.INCOMPLETE_QUERY_RESPONSE.value,
                "notes": "Query response is non-authoritative or paginated; cannot infer absence from venue",
            })
            reasons.append("Exchange query response is non-authoritative/incomplete; cannot infer absence")

        ex_orders = exchange_orders or []
        ex_fills = exchange_fills or []

        # Index exchange orders by cl_ord_id and exchange_order_id
        ex_by_clid: Dict[str, Dict[str, Any]] = {}
        ex_by_exid: Dict[str, Dict[str, Any]] = {}
        seen_ex_clids: Set[str] = set()

        for eo in ex_orders:
            clid = str(eo.get("cl_ord_id") or "").strip()
            exid = str(eo.get("id") or eo.get("order_id") or "").strip()

            if clid:
                if clid in seen_ex_clids:
                    anomalies_list.append({
                        "type": ReconciliationAnomalyType.DUPLICATE_EXCHANGE_RECORD.value,
                        "cl_ord_id": clid,
                        "details": redact_sensitive_data(str(eo)),
                    })
                    reasons.append(f"Exchange returned duplicate record for cl_ord_id {clid!r}")
                seen_ex_clids.add(clid)
                ex_by_clid[clid] = eo

            if exid:
                ex_by_exid[exid] = eo

        # Index fills by cl_ord_id and order_id, deduplicating identical fill IDs/records
        fills_by_clid: Dict[str, List[Dict[str, Any]]] = {}
        seen_fill_ids: Set[str] = set()
        for f in ex_fills:
            f_clid = str(f.get("cl_ord_id") or "").strip()
            f_exid = str(f.get("order_id") or "").strip()
            f_fill_id = str(f.get("id") or f.get("fill_id") or f.get("trade_id") or "").strip()
            if f_fill_id:
                if f_fill_id in seen_fill_ids:
                    anomalies_list.append({
                        "type": ReconciliationAnomalyType.DUPLICATE_FILL_EVENT.value,
                        "fill_id": f_fill_id,
                        "details": redact_sensitive_data(str(f)),
                    })
                    reasons.append(f"Duplicate fill record {f_fill_id!r} received from venue/stream")
                    continue
                seen_fill_ids.add(f_fill_id)

            key = f_clid or (ex_by_exid.get(f_exid, {}).get("cl_ord_id") if f_exid else None)
            if key:
                fills_by_clid.setdefault(key, []).append(f)

        # 2. Check local orders against exchange
        for cl_id, l_data in local_orders.items():
            l_state_raw = l_data.get("state", OrderLifecycleState.SUBMISSION_UNKNOWN)
            if isinstance(l_state_raw, str):
                try:
                    l_state = OrderLifecycleState(l_state_raw)
                except ValueError:
                    l_state = OrderLifecycleState.RECONCILIATION_REQUIRED
            else:
                l_state = l_state_raw

            l_qty = Decimal(str(l_data.get("order_size", l_data.get("qty", "1.0"))))
            ex_order = ex_by_clid.get(cl_id)
            order_anomalies: List[ReconciliationAnomalyType] = []
            order_notes: List[str] = []

            if ex_order is None:
                # Order not found in query response
                if not query_is_authoritative:
                    order_anomalies.append(ReconciliationAnomalyType.INCOMPLETE_QUERY_RESPONSE)
                    reconciled_state = OrderLifecycleState.RECONCILIATION_REQUIRED
                    risk_released = False
                    unfilled_quota_released = False
                    position_exposure_held = False
                    position_exposure_qty = Decimal("0.0")
                    order_notes.append("Missing from non-authoritative response; must reconcile via authoritative query")
                    reasons.append(f"Order {cl_id!r} missing from non-authoritative query response")
                else:
                    elapsed_since_res = now - float(l_data.get("timestamp_utc", l_data.get("reservation_time", now)))
                    if l_state in (OrderLifecycleState.RESERVED, OrderLifecycleState.PENDING_SUBMISSION):
                        if elapsed_since_res > self.reservation_grace_period_seconds:
                            order_anomalies.append(ReconciliationAnomalyType.UNRESOLVED_LOCAL_RESERVATION)
                            reconciled_state = OrderLifecycleState.RECONCILIATION_REQUIRED
                            risk_released = False
                            unfilled_quota_released = False
                            position_exposure_held = False
                            position_exposure_qty = Decimal("0.0")
                            order_notes.append("Local reservation expired without exchange dispatch")
                            reasons.append(f"Local reservation {cl_id!r} has no exchange record after {elapsed_since_res:.1f}s")
                        else:
                            reconciled_state = OrderLifecycleState.RESERVED
                            risk_released = False
                            unfilled_quota_released = False
                            position_exposure_held = False
                            position_exposure_qty = Decimal("0.0")
                            order_notes.append("Within reservation grace period")
                    elif l_state in (OrderLifecycleState.SUBMISSION_UNKNOWN, OrderLifecycleState.SUBMITTED, OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.RESTING):
                        order_anomalies.append(ReconciliationAnomalyType.MISSING_FROM_EXCHANGE)
                        reconciled_state = OrderLifecycleState.RECONCILIATION_REQUIRED
                        risk_released = False
                        unfilled_quota_released = False
                        position_exposure_held = False
                        position_exposure_qty = Decimal("0.0")
                        reasons.append(f"Dispatched order {cl_id!r} (local state {l_state.value}) missing from exchange")
                    else:
                        # Already locally terminal
                        reconciled_state = ORDER_STATE_CANONICAL_MAP.get(l_state, OrderLifecycleState.CANCELLED_CONFIRMED)
                        risk_released = True
                        unfilled_quota_released = True
                        position_exposure_held = False
                        position_exposure_qty = Decimal("0.0")

                reconciled_dict[cl_id] = ReconciledOrderRecord(
                    cl_ord_id=cl_id,
                    exchange_order_id=l_data.get("exchange_order_id"),
                    local_state=l_state,
                    exchange_state=None,
                    local_qty=l_qty,
                    exchange_filled_qty=Decimal("0.0"),
                    exchange_remaining_qty=Decimal("0.0"),
                    reconciled_state=reconciled_state,
                    anomalies=order_anomalies,
                    risk_released=risk_released,
                    unfilled_quota_released=unfilled_quota_released,
                    position_exposure_held=position_exposure_held,
                    position_exposure_qty=position_exposure_qty,
                    notes=order_notes,
                )

            else:
                # Order found on exchange
                ex_state = str(ex_order.get("state", "")).lower()
                ex_filled = Decimal(str(ex_order.get("size_filled", ex_order.get("filled_qty", "0.0"))))
                ex_unfilled = Decimal(str(ex_order.get("unfilled_size", ex_order.get("unfilled_qty", "0.0"))))
                ex_total = Decimal(str(ex_order.get("size", ex_order.get("qty", l_qty))))
                ex_order_id = ex_order.get("id") or ex_order.get("order_id")

                # Check quantity contradiction
                if ex_total != l_qty:
                    order_anomalies.append(ReconciliationAnomalyType.CONTRADICTORY_RECORD)
                    reasons.append(
                        f"Order {cl_id!r} size contradiction: local={l_qty} vs exchange={ex_total}"
                    )

                # Check fills
                order_fills = fills_by_clid.get(cl_id, [])
                sum_fill_qty = sum(Decimal(str(f.get("size", f.get("qty", "0.0")))) for f in order_fills)
                if sum_fill_qty > Decimal("0.0") and sum_fill_qty != ex_filled:
                    order_anomalies.append(ReconciliationAnomalyType.CONTRADICTORY_RECORD)
                    reasons.append(
                        f"Order {cl_id!r} fill quantity contradiction: fills_sum={sum_fill_qty} vs order_filled={ex_filled}"
                    )

                # Check overfill against locally expected size
                if ex_filled > l_qty or sum_fill_qty > l_qty:
                    order_anomalies.append(ReconciliationAnomalyType.OVERFILL_DETECTED)
                    order_anomalies.append(ReconciliationAnomalyType.CONTRADICTORY_RECORD)
                    reasons.append(
                        f"Order {cl_id!r} overfilled: filled={ex_filled} (fills_sum={sum_fill_qty}) > local_qty={l_qty}"
                    )

                # Reconcile state
                position_exposure_held = ex_filled > Decimal("0.0")
                position_exposure_qty = ex_filled

                if ex_state in ("open", "pending", "untriggered"):
                    if ex_filled > Decimal("0.0"):
                        reconciled_state = OrderLifecycleState.PARTIALLY_FILLED
                        order_anomalies.append(ReconciliationAnomalyType.PARTIAL_FILL_DETECTED)
                    else:
                        reconciled_state = OrderLifecycleState.ACKNOWLEDGED
                    risk_released = False  # order is still active!
                    unfilled_quota_released = False

                elif ex_state in ("filled", "closed"):
                    if l_state in (OrderLifecycleState.CANCEL_REQUESTED, OrderLifecycleState.CANCELLED_CONFIRMED, OrderLifecycleState.CANCELLED_UNFILLED):
                        order_anomalies.append(ReconciliationAnomalyType.DELAYED_FILL_POST_CANCEL)
                        order_notes.append("Late fill occurred after cancellation request")
                    reconciled_state = OrderLifecycleState.FILLED
                    risk_released = True
                    unfilled_quota_released = True

                elif ex_state in ("cancelled", "rejected"):
                    if ex_filled > Decimal("0.0"):
                        # Partially filled before cancellation
                        reconciled_state = OrderLifecycleState.PARTIALLY_FILLED
                        order_anomalies.append(ReconciliationAnomalyType.PARTIAL_FILL_DETECTED)
                        order_notes.append(f"Order cancelled with partial fill: {ex_filled} filled")
                        unfilled_quota_released = True
                    else:
                        reconciled_state = OrderLifecycleState.CANCELLED_CONFIRMED
                        unfilled_quota_released = True
                    risk_released = True

                else:
                    reconciled_state = OrderLifecycleState.RECONCILIATION_REQUIRED
                    order_anomalies.append(ReconciliationAnomalyType.CONTRADICTORY_RECORD)
                    risk_released = False
                    unfilled_quota_released = False
                    reasons.append(f"Unrecognized exchange state {ex_state!r} for order {cl_id!r}")

                reconciled_dict[cl_id] = ReconciledOrderRecord(
                    cl_ord_id=cl_id,
                    exchange_order_id=ex_order_id,
                    local_state=l_state,
                    exchange_state=ex_state,
                    local_qty=l_qty,
                    exchange_filled_qty=ex_filled,
                    exchange_remaining_qty=ex_unfilled,
                    reconciled_state=reconciled_state,
                    anomalies=order_anomalies,
                    risk_released=risk_released,
                    unfilled_quota_released=unfilled_quota_released,
                    position_exposure_held=position_exposure_held,
                    position_exposure_qty=position_exposure_qty,
                    notes=order_notes,
                )

        # 3. Detect unknown exchange orders (orders on exchange not known to local ledger)
        for eo in ex_orders:
            eo_clid = str(eo.get("cl_ord_id") or "").strip()
            if not eo_clid or eo_clid not in local_orders:
                eo_id = eo.get("id") or eo.get("order_id")
                anomalies_list.append({
                    "type": ReconciliationAnomalyType.UNKNOWN_EXCHANGE_ORDER.value,
                    "exchange_order_id": eo_id,
                    "cl_ord_id": eo_clid,
                    "details": redact_sensitive_data(str(eo)),
                })
                reasons.append(
                    f"Unknown exchange order detected (id={eo_id}, cl_ord_id={eo_clid!r}) not present in local ledger"
                )

        # Collect anomalies from all orders
        for ro in reconciled_dict.values():
            for a in ro.anomalies:
                anomalies_list.append({
                    "type": a.value,
                    "cl_ord_id": ro.cl_ord_id,
                    "local_state": ro.local_state.value,
                    "reconciled_state": ro.reconciled_state.value,
                    "notes": ro.notes,
                })

        # Determine aggregate status
        has_blocking_anomalies = any(
            a["type"] in (
                ReconciliationAnomalyType.UNKNOWN_EXCHANGE_ORDER.value,
                ReconciliationAnomalyType.CONTRADICTORY_RECORD.value,
                ReconciliationAnomalyType.DUPLICATE_EXCHANGE_RECORD.value,
                ReconciliationAnomalyType.ENDPOINT_UNAVAILABLE.value,
                ReconciliationAnomalyType.OVERFILL_DETECTED.value,
                ReconciliationAnomalyType.INCOMPLETE_QUERY_RESPONSE.value,
                ReconciliationAnomalyType.DUPLICATE_FILL_EVENT.value,
            )
            for a in anomalies_list
        )
        has_unresolved_local = any(
            ro.reconciled_state in (
                OrderLifecycleState.RECONCILIATION_REQUIRED,
                OrderLifecycleState.SUBMISSION_UNKNOWN,
            )
            for ro in reconciled_dict.values()
        )

        if has_blocking_anomalies:
            status = ReconciliationStatus.BLOCKED
            permitted = False
        elif has_unresolved_local:
            status = ReconciliationStatus.AMBIGUOUS
            permitted = False
        elif len(anomalies_list) > 0:
            status = ReconciliationStatus.DIVERGENT
            # If all anomalies are clean partial fills or expected graceful resolutions, execution may be evaluated
            permitted = len(reasons) == 0
        else:
            status = ReconciliationStatus.CLEAN
            permitted = True

        return ReconciliationReport(
            status=status,
            timestamp_utc=now,
            total_local_orders=len(local_orders),
            total_exchange_orders=len(ex_orders),
            total_exchange_fills=len(ex_fills),
            reconciled_orders=reconciled_dict,
            anomalies=anomalies_list,
            execution_permitted=permitted,
            reasons=reasons,
        )
