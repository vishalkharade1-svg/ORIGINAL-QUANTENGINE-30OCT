"""Fail-closed, read-only reconciliation of testnet order journals.

This module deliberately does not submit, retry, or cancel orders. It combines
an append-only local authorization ledger with a caller-supplied exchange
snapshot and emits explicit outcomes, preserving uncertainty when exchange
history may be incomplete.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Iterable

_OPEN = {"open", "pending", "working", "untriggered", "partially_filled", "partially filled"}
_FILLED = {"filled", "closed"}
_CANCELLED = {"cancelled", "canceled", "expired", "rejected"}
_TERMINAL_LEDGER = {
    "FILLED": "FILLED",
    "CANCELLED_CONFIRMED": "CANCELLED_CONFIRMED",
    "CANCELLED_UNFILLED": "CANCELLED_CONFIRMED",
    "REJECTED_POST_ONLY": "REJECTED_CONFIRMED",
}


class DurableRecoveryError(ValueError):
    """Ledger or snapshot is malformed; recovery must stop without writes."""


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() and result >= 0 else None


def read_durable_order_journal(ledger_path: str | Path) -> dict[str, dict[str, Any]]:
    """Read and validate journal events, returning one reconstructed row per client ID.

    This is intentionally strict about malformed JSON and missing client IDs on
    order lifecycle events. A corrupted ledger cannot be used to infer safety.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {}
    states: dict[str, dict[str, Any]] = {}
    submitted_once: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    event = json.loads(raw)
                except Exception as exc:
                    raise DurableRecoveryError(f"invalid JSON at line {line_no}") from exc
                if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
                    raise DurableRecoveryError(f"invalid event shape at line {line_no}")
                name = _text(event.get("event"))
                data = event["data"]
                clid = _text(data.get("cl_ord_id"))
                if name in {"ORDER_RESERVED", "ORDER_SUBMITTED", "ORDER_PLACED", "ORDER_RESTING", "ORDER_ACKNOWLEDGED", "ACK_TIMEOUT_AMBIGUOUS", "AMBIGUOUS_STATE", "ORDER_TERMINAL", "ORDER_FILLED", "ORDER_CANCELLED", "CANCEL_REQUESTED", "RESTING_TIMEOUT_CANCEL_SENT"} and not clid:
                    raise DurableRecoveryError(f"missing cl_ord_id for {name} at line {line_no}")
                if not clid:
                    continue
                if name == "ORDER_RESERVED":
                    if clid in states:
                        raise DurableRecoveryError(f"duplicate reservation for {clid!r}")
                    states[clid] = {
                        "client_order_id": clid,
                        "state": "RESERVED",
                        "exchange_order_id": "",
                        "product_id": data.get("product_id"),
                        "symbol": _text(data.get("symbol")),
                        "size": _text(data.get("order_size")),
                        "side": _text(data.get("side")),
                        "limit_price": _text(data.get("limit_price")),
                        "post_only": data.get("post_only"),
                        "last_event": name,
                    }
                elif name in {"ORDER_SUBMITTED", "ORDER_PLACED"}:
                    if clid in submitted_once:
                        raise DurableRecoveryError(f"duplicate submission event for {clid!r}")
                    submitted_once.add(clid)
                    row = states.setdefault(clid, {"client_order_id": clid})
                    row.update({"state": "SUBMISSION_UNKNOWN", "last_event": name})
                    for key in ("product_id", "symbol", "order_size", "side", "limit_price", "post_only"):
                        if data.get(key) is not None:
                            target = "size" if key == "order_size" else key
                            row[target] = data[key]
                elif name in {"ORDER_RESTING", "ORDER_ACKNOWLEDGED"}:
                    row = states.setdefault(clid, {"client_order_id": clid})
                    row["state"] = "ACKNOWLEDGED"
                    row["exchange_order_id"] = _text(data.get("exchange_order_id"))
                    row["last_event"] = name
                elif name in {"ACK_TIMEOUT_AMBIGUOUS", "AMBIGUOUS_STATE"}:
                    row = states.setdefault(clid, {"client_order_id": clid})
                    row["state"] = "RECONCILIATION_REQUIRED"
                    row["last_event"] = name
                elif name in {"CANCEL_REQUESTED", "RESTING_TIMEOUT_CANCEL_SENT"}:
                    row = states.setdefault(clid, {"client_order_id": clid})
                    row["state"] = "CANCEL_REQUESTED"
                    row["last_event"] = name
                elif name in {"ORDER_TERMINAL", "ORDER_FILLED", "ORDER_CANCELLED"}:
                    row = states.setdefault(clid, {"client_order_id": clid})
                    raw_state = _text(data.get("state", "CANCELLED_CONFIRMED")).upper()
                    if raw_state not in _TERMINAL_LEDGER:
                        # Unknown terminal labels must not be treated as safe.
                        row["state"] = "RECONCILIATION_REQUIRED"
                    else:
                        row["state"] = _TERMINAL_LEDGER[raw_state]
                    row["last_event"] = name
    except OSError as exc:
        raise DurableRecoveryError("cannot read durable ledger") from exc
    return states


def reconcile_order_journal(
    journal: dict[str, dict[str, Any]],
    exchange_orders: Iterable[dict[str, Any]],
    *,
    exchange_snapshot_complete: bool,
    exchange_fills: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Reconcile journal rows against an exchange order snapshot without writes.

    Matching uses client-order ID first and then validates product/symbol/size/side
    where both sides provide values. An absent order is never declared cancelled
    unless the caller explicitly says the snapshot is complete *and* the journal
    had a known exchange order ID; even then it remains unresolved because a
    current open-orders snapshot is not order history.
    """
    if not isinstance(journal, dict):
        raise DurableRecoveryError("journal must be a mapping")
    by_client: dict[str, list[dict[str, Any]]] = {}
    by_id: dict[str, list[dict[str, Any]]] = {}
    for item in exchange_orders:
        if not isinstance(item, dict):
            raise DurableRecoveryError("exchange order row is not an object")
        clid = _text(item.get("client_order_id", item.get("cl_ord_id")))
        oid = _text(item.get("id", item.get("order_id")))
        if clid:
            by_client.setdefault(clid, []).append(item)
        if oid:
            by_id.setdefault(oid, []).append(item)

    fills_by_client: dict[str, list[dict[str, Any]]] = {}
    fills_by_order: dict[str, list[dict[str, Any]]] = {}
    for fill in exchange_fills:
        if not isinstance(fill, dict):
            raise DurableRecoveryError("exchange fill row is not an object")
        fill_clid = _text(fill.get("client_order_id", fill.get("cl_ord_id")))
        fill_oid = _text(fill.get("order_id", fill.get("order", fill.get("order_id"))))
        if fill_clid:
            fills_by_client.setdefault(fill_clid, []).append(fill)
        if fill_oid:
            fills_by_order.setdefault(fill_oid, []).append(fill)

    results = []
    for clid, local in journal.items():
        if not isinstance(local, dict) or _text(local.get("client_order_id", clid)) != clid:
            raise DurableRecoveryError(f"invalid local journal row for {clid!r}")
        known_id = _text(local.get("exchange_order_id"))
        candidates = by_client.get(clid, [])
        if not candidates and known_id:
            candidates = by_id.get(known_id, [])
        status = "UNRESOLVED_MANUAL_RECONCILIATION"
        detail = "No unique exchange order proves the journal state; do not retry or cancel automatically."
        chosen = None
        matching_fills = list(fills_by_client.get(clid, []))
        if not matching_fills and known_id:
            matching_fills = list(fills_by_order.get(known_id, []))
        if len(candidates) > 1:
            status, detail = "CONFLICT_MULTIPLE_MATCHES", "Multiple exchange rows match the same client-order ID."
        elif len(candidates) == 1:
            chosen = candidates[0]
            ex_id = _text(chosen.get("id", chosen.get("order_id")))
            ex_clid = _text(chosen.get("client_order_id", chosen.get("cl_ord_id")))
            ex_pid = _text(chosen.get("product_id"))
            local_pid = _text(local.get("product_id"))
            ex_symbol = _text(chosen.get("product_symbol", chosen.get("symbol")))
            local_symbol = _text(local.get("symbol"))
            mismatches = []
            if ex_clid and ex_clid != clid:
                mismatches.append("client_order_id")
            if known_id and ex_id and known_id != ex_id:
                mismatches.append("exchange_order_id")
            if local_pid and ex_pid and local_pid != ex_pid:
                mismatches.append("product_id")
            if local_symbol and ex_symbol and local_symbol.upper() != ex_symbol.upper():
                mismatches.append("symbol")
            for local_key, ex_keys, label in (
                ("side", ("side",), "side"),
                ("size", ("size", "order_size"), "size"),
            ):
                local_value = _text(local.get(local_key))
                ex_value = next((_text(chosen.get(k)) for k in ex_keys if _text(chosen.get(k))), "")
                if local_value and ex_value:
                    if label == "size":
                        ld, ed = _decimal(local_value), _decimal(ex_value)
                        if ld is None or ed is None or ld != ed:
                            mismatches.append(label)
                    elif local_value.lower() != ex_value.lower():
                        mismatches.append(label)
            for fill in matching_fills:
                fill_pid = _text(fill.get("product_id"))
                if local_pid and fill_pid and local_pid != fill_pid:
                    mismatches.append("fill_product_id")
                fill_oid = _text(fill.get("order_id", fill.get("order")))
                if ex_id and fill_oid and fill_oid != ex_id:
                    mismatches.append("fill_order_id")
                fill_clid = _text(fill.get("client_order_id", fill.get("cl_ord_id")))
                if fill_clid and fill_clid != clid:
                    mismatches.append("fill_client_order_id")
            if mismatches:
                status, detail = "CONFLICT_IDENTITY_MISMATCH", "Exchange row conflicts on: " + ", ".join(sorted(set(mismatches)))
            else:
                state = _text(chosen.get("state")).lower()
                filled = _decimal(chosen.get("size_filled", chosen.get("filled_size")))
                total = _decimal(chosen.get("size", chosen.get("order_size", local.get("size"))))
                fill_sizes = [_decimal(f.get("size", f.get("fill_size"))) for f in matching_fills]
                if any(v is None for v in fill_sizes):
                    status, detail = "UNRESOLVED_INVALID_FILL_EVIDENCE", "At least one matching fill has an invalid or missing size."
                else:
                    summed_fills = sum((v for v in fill_sizes if v is not None), Decimal("0"))
                    if matching_fills and (filled is None or summed_fills > filled):
                        # Fill history can be fresher than the order snapshot;
                        # use the larger observed cumulative evidence rather
                        # than silently ignoring a recorded fill.
                        filled = summed_fills
                if status == "UNRESOLVED_INVALID_FILL_EVIDENCE":
                    pass
                elif state in _FILLED or (filled is not None and total is not None and total > 0 and filled >= total):
                    status, detail = "FILLED_CONFIRMED", "Exchange order reports a completed fill."
                elif matching_fills and filled is not None and filled > 0:
                    status, detail = "PARTIALLY_FILLED_OPEN", "Matching exchange fills exist; reconcile position and remaining order quantity."
                elif state in _CANCELLED:
                    status, detail = "TERMINAL_CONFIRMED", "Exchange order reports a terminal non-working state; inspect fills before flattening any resulting position."
                elif state in _OPEN and filled is not None and filled > 0:
                    status, detail = "PARTIALLY_FILLED_OPEN", "Order is working with a non-zero fill; reconcile position and remaining quantity."
                elif state in _OPEN:
                    status, detail = "OPEN_CONFIRMED", "Exchange reports the order is still working."
                else:
                    status, detail = "UNRESOLVED_UNKNOWN_EXCHANGE_STATE", "Exchange state is absent or unrecognized."
        elif known_id:
            status, detail = "UNRESOLVED_ORDER_NOT_IN_SNAPSHOT", "Known order ID is absent from this snapshot; absence does not prove cancellation or no fill."
        elif local.get("state") in {"FILLED", "CANCELLED_CONFIRMED", "REJECTED_CONFIRMED"}:
            status, detail = "LOCAL_TERMINAL_NEEDS_EXCHANGE_EVIDENCE", "Local terminal event exists but this snapshot did not independently corroborate it."
        elif exchange_snapshot_complete:
            status, detail = "UNRESOLVED_NO_MATCH_COMPLETE_SNAPSHOT", "No matching open order found, but snapshot completeness does not establish historical non-execution."
        results.append({
            "client_order_id": clid,
            "local_state": _text(local.get("state")) or "UNKNOWN",
            "exchange_order_id": known_id or (_text(chosen.get("id", chosen.get("order_id"))) if chosen else ""),
            "status": status,
            "detail": detail,
            "automatic_action": "NONE",
        })
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema": "quantengine.testnet-durable-recovery.v1",
        "mode": "READ_ONLY_NO_AUTOMATIC_ACTIONS",
        "exchange_snapshot_complete": bool(exchange_snapshot_complete),
        "orders_reviewed": len(results),
        "unresolved_count": sum(1 for row in results if row["status"] not in {"FILLED_CONFIRMED", "TERMINAL_CONFIRMED"}),
        "status_counts": counts,
        "orders": results,
        "safe_to_resume_submissions": len(results) == 0,  # Any prior order requires explicit operator review before resuming.
    }


def reconcile_ledger_file(
    ledger_path: str | Path,
    exchange_orders: Iterable[dict[str, Any]],
    *,
    exchange_snapshot_complete: bool,
    exchange_fills: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Convenience entry point for a parsed exchange snapshot."""
    journal = read_durable_order_journal(ledger_path)
    return reconcile_order_journal(journal, exchange_orders, exchange_snapshot_complete=exchange_snapshot_complete, exchange_fills=exchange_fills)
