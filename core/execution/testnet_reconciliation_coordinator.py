"""Read-only coordinator joining the durable journal to Delta evidence.

This module never places, retries, modifies, or cancels orders. Any incomplete,
contradictory, or out-of-scope evidence produces HOLD.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from core.execution.historical_evidence_window import (
    HistoricalEvidenceError, audit_historical_evidence_window,
)
from core.execution.position_fill_reconciliation import (
    PositionFillReconciliationError,
    reconstruct_signed_position,
    compare_position_to_fills,
)
from core.execution.testnet_durable_recovery import (
    DurableRecoveryError,
    read_durable_order_journal,
    reconcile_order_journal,
)


class ReconciliationCoordinatorError(RuntimeError):
    """Coordinator cannot safely interpret reconciliation evidence."""


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _position_size(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _dedupe_orders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge identical open/history representations; reject ID collisions."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        oid = str(row.get("id", row.get("order_id", ""))).strip()
        if not oid:
            raise ReconciliationCoordinatorError("exchange order missing stable order ID")
        previous = by_id.get(oid)
        if previous is None:
            by_id[oid] = dict(row)
            continue
        # A differing representation for the same venue ID is not silently
        # resolved by choosing whichever endpoint happened to be read last.
        keys = {"product_id", "size", "side", "state", "client_order_id", "cl_ord_id"}
        for key in keys:
            left, right = previous.get(key), row.get(key)
            if left not in (None, "") and right not in (None, "") and str(left).lower() != str(right).lower():
                raise ReconciliationCoordinatorError("contradictory open-order/history evidence")
        by_id[oid].update({k: v for k, v in row.items() if v not in (None, "")})
    return list(by_id.values())


class TestnetReconciliationCoordinator:
    __test__ = False
    """Capture and reconcile one product against a durable local journal."""

    def __init__(self, exchange: Any, ledger_path: str | Path):
        self._exchange = exchange
        self._ledger_path = Path(ledger_path)

    def run(self, *, product_id: int) -> dict[str, Any]:
        if not _positive_int(product_id):
            raise ValueError("product_id must be a positive integer")
        try:
            journal = read_durable_order_journal(self._ledger_path)
            snapshot = self._exchange.get_reconciliation_snapshot(product_id=product_id)
            if getattr(snapshot, "product_id", None) != product_id:
                raise ReconciliationCoordinatorError("snapshot product scope mismatch")
            if not isinstance(getattr(snapshot, "complete", None), bool):
                raise ReconciliationCoordinatorError("snapshot completeness flag missing")
            endpoint_status = getattr(snapshot, "endpoint_status", None)
            required_endpoints = {"open_orders", "order_history", "fills", "positions", "wallet_transactions"}
            if not isinstance(endpoint_status, dict) or set(endpoint_status) != required_endpoints:
                raise ReconciliationCoordinatorError("endpoint status evidence incomplete")
            if snapshot.complete and any(value != "OK" for value in endpoint_status.values()):
                raise ReconciliationCoordinatorError("snapshot completeness contradicts endpoint status")
            orders = _dedupe_orders([*snapshot.open_orders, *snapshot.order_history])
            fills = list(snapshot.fills)
            positions = list(snapshot.positions)
            wallet_transactions = list(getattr(snapshot, "wallet_transactions", ()))
            window_start = getattr(snapshot, "window_start", None)
            window_end = getattr(snapshot, "window_end", None)
            historical_evidence = None
            if (window_start is None) != (window_end is None):
                raise ReconciliationCoordinatorError("historical evidence window bounds incomplete")
            if window_start is not None:
                try:
                    historical_evidence = audit_historical_evidence_window(
                        orders=orders, fills=fills, wallet_transactions=wallet_transactions,
                        window_start=window_start, window_end=window_end,
                        overlap_seconds=getattr(snapshot, "overlap_seconds", 60),
                        venue_time_filter=getattr(snapshot, "venue_time_filter", None),
                    )
                except HistoricalEvidenceError as exc:
                    raise ReconciliationCoordinatorError(str(exc)) from None
            for row in [*orders, *fills]:
                if not isinstance(row, dict) or str(row.get("product_id", "")) != str(product_id):
                    raise ReconciliationCoordinatorError("exchange evidence product scope mismatch")
            for position in positions:
                if not isinstance(position, dict):
                    raise ReconciliationCoordinatorError("invalid position evidence row")
                scoped_product = position.get("product_id", position.get("query_product_id"))
                if scoped_product is not None and str(scoped_product) != str(product_id):
                    raise ReconciliationCoordinatorError("position product scope mismatch")
                if _position_size(position.get("size")) is None:
                    raise ReconciliationCoordinatorError("invalid position size evidence")
            if any(not isinstance(row, dict) for row in wallet_transactions):
                raise ReconciliationCoordinatorError("invalid wallet transaction evidence")
            # Wallet transactions are account-wide. Only product-linked rows
            # can be attributed to this product. Position-affecting and
            # exceptional events are surfaced, never guessed into quantity.
            exceptional_types = {
                "funding", "settlement", "liquidation_fee", "fill_appropriation",
                "revert", "trading_credits_paid_liquidation_fee",
            }
            product_events = []
            unscoped_exceptional_events = []
            for txn in wallet_transactions:
                txn_type = str(txn.get("transaction_type", "")).strip().lower()
                scoped = txn.get("product_id")
                if scoped is not None and str(scoped) == str(product_id) and txn_type in exceptional_types:
                    product_events.append({"id": str(txn.get("id")), "type": txn_type,
                                           "amount": str(txn.get("amount")),
                                           "created_at": str(txn.get("created_at"))})
                elif scoped in (None, "") and txn_type in exceptional_types:
                    unscoped_exceptional_events.append({"id": str(txn.get("id")), "type": txn_type})
            fill_type_review = []
            for fill in fills:
                fill_type = str(fill.get("fill_type", "")).strip().lower()
                if not fill_type:
                    fill_type_review.append({"fill_id": str(fill.get("id", fill.get("fill_id", ""))),
                                             "fill_type": None, "reason": "FILL_TYPE_MISSING"})
                elif fill_type != "normal":
                    fill_type_review.append({"fill_id": str(fill.get("id", fill.get("fill_id", ""))),
                                             "fill_type": fill_type,
                                             "reason": "NON_NORMAL_FILL_REQUIRES_REVIEW"})
            order_report = reconcile_order_journal(
                journal, orders,
                exchange_snapshot_complete=snapshot.complete,
                exchange_fills=fills,
            )
            position_fill_report = None
            position_fill_error = None
            try:
                fill_reconstruction = reconstruct_signed_position(fills, product_id=product_id)
                position_fill_report = compare_position_to_fills(
                    fill_reconstruction, positions, product_id=product_id
                )
            except PositionFillReconciliationError as exc:
                # Ambiguous evidence is reported, never normalized into a match.
                position_fill_error = str(exc)
            nonzero_positions = [p for p in positions if _position_size(p.get("size")) != 0]
            unresolved = order_report["unresolved_count"] > 0
            complete = snapshot.complete
            hold_reasons = []
            if not complete:
                hold_reasons.append("EXCHANGE_SNAPSHOT_INCOMPLETE")
            if unresolved:
                hold_reasons.append("ORDER_RECONCILIATION_UNRESOLVED")
            if nonzero_positions:
                hold_reasons.append("NONZERO_POSITION_REQUIRES_OPERATOR_REVIEW")
            if fill_type_review:
                hold_reasons.append("NON_NORMAL_OR_UNCLASSIFIED_FILLS_REQUIRE_REVIEW")
            if product_events:
                hold_reasons.append("PRODUCT_LINKED_WALLET_ADJUSTMENTS_REQUIRE_REVIEW")
            if unscoped_exceptional_events:
                hold_reasons.append("UNSCOPED_WALLET_ADJUSTMENTS_AMBIGUOUS")
            if historical_evidence is not None:
                if any(historical_evidence["missing_timestamps"].values()):
                    hold_reasons.append("HISTORICAL_EVENTS_MISSING_TIMESTAMPS")
                if historical_evidence["orphan_fills"]:
                    hold_reasons.append("HISTORICAL_FILL_ORDER_LINKAGE_UNRESOLVED")
                if historical_evidence["duplicate_fill_ids"] or historical_evidence["duplicate_wallet_transaction_ids"]:
                    hold_reasons.append("HISTORICAL_DUPLICATE_EVENT_IDS")
                if historical_evidence["reversal_events"]:
                    hold_reasons.append("HISTORICAL_WALLET_REVERSALS_REQUIRE_REVIEW")
                position_statuses = {item["status"] for item in historical_evidence["new_position_observations"]}
                if "INVALID_NEW_POSITION" in position_statuses:
                    hold_reasons.append("HISTORICAL_NEW_POSITION_INVALID")
                if "MISMATCH" in position_statuses:
                    hold_reasons.append("HISTORICAL_NEW_POSITION_SEQUENCE_MISMATCH")
                if "FILL_SIDE_OR_SIZE_UNVERIFIABLE" in position_statuses:
                    hold_reasons.append("HISTORICAL_NEW_POSITION_SEQUENCE_UNVERIFIABLE")
            if position_fill_error is not None:
                hold_reasons.append("POSITION_FILL_EVIDENCE_AMBIGUOUS")
            elif position_fill_report is not None and not position_fill_report["matches"]:
                hold_reasons.append("POSITION_FILL_QUANTITY_MISMATCH")
            if journal and not hold_reasons:
                # Even corroborated terminal events require a fresh operator
                # decision before resuming submissions.
                hold_reasons.append("PRIOR_ORDER_HISTORY_REQUIRES_OPERATOR_RESUME")
            return {
                "schema": "quantengine.testnet-reconciliation-coordinator.v1",
                "mode": "READ_ONLY_NO_AUTOMATIC_ACTIONS",
                "product_id": product_id,
                "captured_at": snapshot.captured_at,
                "snapshot_complete": complete,
                "endpoint_status": dict(endpoint_status),
                "orders": order_report,
                "position_rows": len(positions),
                "nonzero_position_rows": len(nonzero_positions),
                "position_fill_reconciliation": position_fill_report,
                "position_fill_reconciliation_error": position_fill_error,
                "fill_type_review": fill_type_review,
                "historical_evidence_window": historical_evidence,
                "wallet_adjustment_evidence": {
                    "product_linked_events": product_events,
                    "unscoped_exceptional_events": unscoped_exceptional_events,
                    "quantity_adjustment_applied": False,
                },
                "decision": "HOLD" if hold_reasons else "NO_PRIOR_ORDERS_CLEAR",
                "hold_reasons": hold_reasons,
                "safe_to_resume_submissions": False,
                "automatic_action": "NONE",
            }
        except (DurableRecoveryError, ReconciliationCoordinatorError):
            raise
        except Exception as exc:
            # Avoid leaking REST URLs, headers, account identifiers, or secrets.
            raise ReconciliationCoordinatorError(
                f"reconciliation failed closed ({type(exc).__name__})"
            ) from None
