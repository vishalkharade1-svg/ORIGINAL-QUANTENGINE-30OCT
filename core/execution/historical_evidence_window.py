"""Forensic audit of a bounded, read-only historical reconciliation window.

This module does not fetch data or infer missing venue records. It evaluates the
records supplied by the authenticated adapter, applies an explicit inclusive
window plus overlap margin, and reports linkage/duplication/reversal anomalies.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


class HistoricalEvidenceError(ValueError):
    """A requested historical evidence window is invalid or uninterpretable."""


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalEvidenceError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HistoricalEvidenceError(f"{label} must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalEvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _event_time(row: dict[str, Any]) -> datetime | None:
    for key in ("created_at", "updated_at", "timestamp", "fill_time"):
        if row.get(key) not in (None, ""):
            return _utc(str(row[key]), f"event {key}")
    return None


def audit_historical_evidence_window(
    *, orders: Iterable[dict[str, Any]], fills: Iterable[dict[str, Any]],
    wallet_transactions: Iterable[dict[str, Any]], window_start: str,
    window_end: str, overlap_seconds: int = 60,
    venue_time_filter: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Return a deterministic evidence report; never mutate or net wallet amounts."""
    start, end = _utc(window_start, "window_start"), _utc(window_end, "window_end")
    if start >= end:
        raise HistoricalEvidenceError("window_start must precede window_end")
    if isinstance(overlap_seconds, bool) or not isinstance(overlap_seconds, int) or not 0 <= overlap_seconds <= 3600:
        raise HistoricalEvidenceError("overlap_seconds must be an integer from 0 to 3600")
    lower, upper = start - timedelta(seconds=overlap_seconds), end + timedelta(seconds=overlap_seconds)

    orders, fills, wallet_transactions = list(orders), list(fills), list(wallet_transactions)

    def select(rows: Iterable[dict[str, Any]], label: str):
        inside, missing_time, outside = [], [], 0
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise HistoricalEvidenceError(f"{label} row {index} must be an object")
            stamp = _event_time(row)
            if stamp is None:
                missing_time.append(str(row.get("id", index)))
            elif lower <= stamp <= upper:
                inside.append(row)
            else:
                outside += 1
        return inside, missing_time, outside

    selected_orders, missing_order_times, orders_outside = select(orders, "order")
    selected_fills, missing_fill_times, fills_outside = select(fills, "fill")
    selected_wallet, missing_wallet_times, wallet_outside = select(wallet_transactions, "wallet")

    # Link fills against the complete paginated order set, not only orders
    # created inside this time window: a valid fill may belong to an older order.
    all_orders = orders
    order_ids = {str(row.get("id", row.get("order_id", ""))) for row in all_orders}
    order_ids.discard("")
    orphan_fills = []
    fill_ids: set[str] = set()
    duplicate_fill_ids = []
    new_position_checks = []
    ordered_fills = sorted(
        selected_fills,
        key=lambda row: _event_time(row) or datetime.min.replace(tzinfo=timezone.utc),
    )
    previous_position: Decimal | None = None
    for fill in ordered_fills:
        fid = str(fill.get("id", fill.get("fill_id", ""))).strip()
        if not fid:
            orphan_fills.append({"fill_id": None, "reason": "MISSING_FILL_ID"})
        elif fid in fill_ids:
            duplicate_fill_ids.append(fid)
        fill_ids.add(fid)
        oid = str(fill.get("order_id", "")).strip()
        if not oid or oid not in order_ids:
            orphan_fills.append({"fill_id": fid or None, "order_id": oid or None,
                                 "reason": "ORDER_LINK_NOT_FOUND_IN_WINDOW"})
        if fill.get("new_position") in (None, ""):
            previous_position = None
        else:
            try:
                position = Decimal(str(fill["new_position"]))
                if not position.is_finite():
                    raise InvalidOperation
                if previous_position is None:
                    status = "BASELINE_REQUIRED"
                    expected = None
                else:
                    try:
                        qty = Decimal(str(fill.get("size")))
                        side = str(fill.get("side", "")).strip().lower()
                        if not qty.is_finite() or qty <= 0 or side not in {"buy", "sell"}:
                            raise InvalidOperation
                        expected = previous_position + (qty if side == "buy" else -qty)
                        status = "MATCH" if position == expected else "MISMATCH"
                    except (InvalidOperation, TypeError, ValueError):
                        expected, status = None, "FILL_SIDE_OR_SIZE_UNVERIFIABLE"
                new_position_checks.append({"fill_id": fid or None,
                                            "reported_new_position": str(position),
                                            "expected_from_previous_snapshot": str(expected) if expected is not None else None,
                                            "status": status})
                previous_position = position
            except (InvalidOperation, TypeError, ValueError):
                new_position_checks.append({"fill_id": fid or None,
                                            "reported_new_position": str(fill.get("new_position")),
                                            "status": "INVALID_NEW_POSITION"})
                previous_position = None

    wallet_ids: set[str] = set()
    duplicate_wallet_ids, reversals = [], []
    for txn in selected_wallet:
        tid = str(txn.get("id", "")).strip()
        if tid and tid in wallet_ids:
            duplicate_wallet_ids.append(tid)
        wallet_ids.add(tid)
        if str(txn.get("transaction_type", "")).strip().lower() == "revert":
            metadata = txn.get("meta_data")
            reversals.append({"transaction_id": tid or None,
                              "metadata": metadata if isinstance(metadata, dict) else None,
                              "status": "REVERSAL_REQUIRES_OPERATOR_LINKAGE"})

    return {
        "schema": "quantengine.historical-evidence-window.v1",
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "overlap_seconds": overlap_seconds,
        "effective_inclusive_start": lower.isoformat(),
        "effective_inclusive_end": upper.isoformat(),
        "selection_semantics": (
            "VENUE_START_END_TIME_FILTER_PLUS_CLIENT_SIDE_AUDIT"
            if venue_time_filter else
            "CLIENT_SIDE_FILTER_OVER_PAGINATED_SNAPSHOT; NOT_VENUE_WINDOW_QUERY"
        ),
        "venue_time_filter": dict(venue_time_filter or {}),
        "counts": {"orders_in_window": len(selected_orders), "fills_in_window": len(selected_fills),
                   "wallet_transactions_in_window": len(selected_wallet),
                   "orders_outside_window": orders_outside, "fills_outside_window": fills_outside,
                   "wallet_transactions_outside_window": wallet_outside},
        "missing_timestamps": {"orders": missing_order_times, "fills": missing_fill_times,
                               "wallet_transactions": missing_wallet_times},
        "orphan_fills": orphan_fills,
        "duplicate_fill_ids": sorted(set(duplicate_fill_ids)),
        "duplicate_wallet_transaction_ids": sorted(set(duplicate_wallet_ids)),
        "reversal_events": reversals,
        "new_position_observations": new_position_checks,
        "wallet_amounts_applied_to_position": False,
        "venue_window_exhaustiveness_certified": False,
    }
