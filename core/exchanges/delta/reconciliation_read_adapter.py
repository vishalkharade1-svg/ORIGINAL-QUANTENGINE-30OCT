"""Read-only Delta REST evidence adapter for durable order reconciliation.

This module performs authenticated GETs only. It never places, cancels, or
retries orders. A snapshot is marked complete only when every endpoint has a
valid response envelope and the venue response does not indicate additional
pages. Any ambiguity raises DeltaReconciliationReadError so callers cannot
mistake partial evidence for a clean reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping


class DeltaReconciliationReadError(RuntimeError):
    """Authenticated reconciliation evidence is unavailable or malformed."""


@dataclass(frozen=True)
class DeltaReconciliationSnapshot:
    captured_at: str
    product_id: int
    open_orders: tuple[dict[str, Any], ...]
    order_history: tuple[dict[str, Any], ...]
    fills: tuple[dict[str, Any], ...]
    positions: tuple[dict[str, Any], ...]
    wallet_transactions: tuple[dict[str, Any], ...]
    complete: bool
    endpoint_status: Mapping[str, str]
    window_start: str | None = None
    window_end: str | None = None
    overlap_seconds: int = 60
    venue_time_filter: Mapping[str, int] | None = None
    page_provenance: tuple[Mapping[str, Any], ...] = ()

    def as_reconciler_inputs(self) -> dict[str, Any]:
        """Return normalized inputs without claiming missing orders are cancelled."""
        return {
            "exchange_orders": [*self.open_orders, *self.order_history],
            "exchange_fills": list(self.fills),
            "exchange_positions": list(self.positions),
            "wallet_transactions": list(self.wallet_transactions),
            "exchange_snapshot_complete": self.complete,
            "captured_at": self.captured_at,
            "endpoint_status": dict(self.endpoint_status),
            "window_start": self.window_start,
            "window_end": self.window_end,
            "overlap_seconds": self.overlap_seconds,
            "venue_time_filter": dict(self.venue_time_filter or {}),
            "page_provenance": [dict(page) for page in self.page_provenance],
        }


class DeltaReconciliationReadAdapter:
    """Read authenticated Delta order/fill/position evidence for one product.

    `rest` must expose `authenticated` and `get(path, params=...)`. No public
    fallback is permitted because unauthenticated data cannot prove account
    order ownership or fills.
    """

    def __init__(self, rest: Any):
        self._rest = rest

    @staticmethod
    def _envelope(response: Any, endpoint: str) -> tuple[list[dict[str, Any]], str | None]:
        if not isinstance(response, dict):
            raise DeltaReconciliationReadError(f"{endpoint}: response must be an object")
        if response.get("success") is not True:
            raise DeltaReconciliationReadError(f"{endpoint}: success flag missing or false")
        rows = response.get("result")
        if isinstance(rows, dict) and endpoint == "/v2/positions":
            # Delta documents GET /v2/positions as a single scoped position object.
            rows = [rows]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise DeltaReconciliationReadError(f"{endpoint}: result must be a list of objects")
        meta = response.get("meta")
        if not isinstance(meta, dict) or "after" not in meta:
            if endpoint == "/v2/positions":
                # This endpoint is a single scoped position response, not a
                # cursor-paginated collection.
                return rows, None
            # Do not assume a first page is complete when pagination metadata
            # is absent. The caller may use the data diagnostically, but the
            # snapshot cannot be treated as complete.
            return rows, "__PAGINATION_METADATA_MISSING__"
        after = meta.get("after")
        if after in (None, "", False):
            return rows, None
        return rows, str(after)

    @staticmethod
    def _require_fields(rows: list[dict[str, Any]], fields: tuple[str, ...], endpoint: str) -> None:
        for index, row in enumerate(rows):
            missing = [field for field in fields if row.get(field) in (None, "")]
            if missing:
                raise DeltaReconciliationReadError(
                    f"{endpoint}: row {index} missing required fields: {','.join(missing)}"
                )

    def _read_all(
        self,
        endpoint: str,
        params: dict[str, Any],
        required: tuple[str, ...],
        *,
        paginated: bool = True,
        max_pages: int = 100,
        page_budget: dict[str, int] | None = None,
        page_provenance: list[dict[str, Any]] | None = None,
        request_timeout_seconds: int = 20,
        retry_budget: int = 2,
        allow_partial: bool = False,
        max_records_per_endpoint: int = 100000,
        record_budget: dict[str, int] | None = None,
    ) -> tuple[list[dict[str, Any]], bool, str]:
        rows: list[dict[str, Any]] = []
        seen_cursors: set[str] = set()
        seen_pages: set[str] = set()
        query = dict(params)
        for page_number in range(max_pages):
            endpoint_remaining = max_records_per_endpoint - len(rows)
            total_remaining = (
                record_budget["max"] - record_budget["used"]
                if record_budget is not None else endpoint_remaining
            )
            remaining_records = min(endpoint_remaining, total_remaining)
            if remaining_records <= 0:
                status = "MAX_TOTAL_RECORDS_REACHED" if total_remaining <= 0 else "MAX_RECORDS_PER_ENDPOINT_REACHED"
                return rows, False, status
            if paginated and "page_size" in query:
                try:
                    query["page_size"] = min(int(query["page_size"]), remaining_records)
                except (TypeError, ValueError):
                    return rows, False, "INVALID_PAGE_SIZE"
            if page_budget is not None and page_budget["used"] >= page_budget["max"]:
                return rows, False, "PAGE_BUDGET_REACHED"
            if page_budget is not None:
                page_budget["used"] += 1
            request_cursor = query.get("after")
            request_started_at = datetime.now(timezone.utc).isoformat()
            request_started_mono = time.monotonic()
            try:
                policy_get = getattr(self._rest, "get_with_policy", None)
                if callable(policy_get):
                    response, retry_count, http_status_code = policy_get(
                        endpoint, params=query,
                        timeout_seconds=request_timeout_seconds,
                        retry_budget=retry_budget,
                    )
                    policy_enforced = True
                else:
                    response = self._rest.get(endpoint, params=query)
                    retry_count, http_status_code = None, None
                    policy_enforced = False
            except Exception as exc:
                if page_provenance is not None:
                    page_provenance.append({
                        "endpoint": endpoint, "page_index": page_number,
                        "request_cursor": request_cursor, "response_cursor": None,
                        "response_status": "REQUEST_FAILED", "record_count": 0,
                        "request_started_at": request_started_at,
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                        "request_duration_ms": round((time.monotonic() - request_started_mono) * 1000, 3),
                        "content_sha256": None, "retry_count": getattr(exc, "retry_count", None),
                        "http_status_code": getattr(getattr(exc, "response", None), "status_code", None),
                        "request_policy_enforced": callable(getattr(self._rest, "get_with_policy", None)),
                        "error_type": type(exc).__name__,
                    })
                # Do not propagate request URLs, headers, or exception strings
                # that might contain credentials.
                if allow_partial:
                    return rows, False, "REQUEST_FAILED"
                raise DeltaReconciliationReadError(
                    f"{endpoint}: authenticated read failed ({type(exc).__name__})"
                ) from None
            try:
                page_rows, after = self._envelope(response, endpoint)
                self._require_fields(page_rows, required, endpoint)
            except Exception as exc:
                if page_provenance is not None:
                    page_provenance.append({
                        "endpoint": endpoint, "page_index": page_number,
                        "request_cursor": request_cursor, "response_cursor": None,
                        "response_status": "INVALID_RESPONSE", "record_count": 0,
                        "request_started_at": request_started_at,
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                        "request_duration_ms": round((time.monotonic() - request_started_mono) * 1000, 3),
                        "content_sha256": None, "retry_count": retry_count,
                        "http_status_code": http_status_code,
                        "request_policy_enforced": policy_enforced,
                        "error_type": type(exc).__name__,
                    })
                if allow_partial:
                    return rows, False, "INVALID_RESPONSE"
                raise
            page_bytes = json.dumps(
                page_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
            page_hash = hashlib.sha256(page_bytes).hexdigest()
            collected_at = datetime.now(timezone.utc).isoformat()
            request_duration_ms = round((time.monotonic() - request_started_mono) * 1000, 3)
            if page_provenance is not None:
                page_provenance.append({
                    "endpoint": endpoint, "page_index": page_number,
                    "request_cursor": request_cursor,
                    "response_cursor": after,
                    "response_status": "SUCCESS", "record_count": len(page_rows),
                    "pagination_metadata_present": after != "__PAGINATION_METADATA_MISSING__",
                    "request_started_at": request_started_at, "collected_at": collected_at,
                    "request_duration_ms": request_duration_ms, "content_sha256": page_hash,
                    "retry_count": retry_count, "http_status_code": http_status_code,
                    "request_policy_enforced": policy_enforced,
                })
            if len(page_rows) > remaining_records:
                accepted = page_rows[:remaining_records]
                rows.extend(accepted)
                if record_budget is not None:
                    record_budget["used"] += len(accepted)
                if page_provenance is not None:
                    page_provenance[-1]["response_status"] = "RECORD_BUDGET_OVERRUN"
                    page_provenance[-1]["records_not_persisted"] = len(page_rows) - len(accepted)
                    page_provenance[-1]["record_budget_remaining"] = remaining_records
                return rows, False, "RECORD_BUDGET_OVERRUN"
            if page_rows and page_hash in seen_pages:
                if page_provenance is not None:
                    page_provenance[-1]["response_status"] = "REPEATED_PAGE"
                if allow_partial:
                    return rows, False, "REPEATED_PAGE"
                raise DeltaReconciliationReadError(f"{endpoint}: repeated response page")
            if page_rows:
                seen_pages.add(page_hash)
            rows.extend(page_rows)
            if record_budget is not None:
                record_budget["used"] += len(page_rows)
            if not paginated:
                return rows, after is None, "OK" if after is None else "INCOMPLETE_PAGINATION"
            if after == "__PAGINATION_METADATA_MISSING__":
                return rows, False, "INCOMPLETE_PAGINATION"
            if after is None:
                return rows, True, "OK"
            if after in seen_cursors:
                if page_provenance is not None:
                    page_provenance[-1]["pagination_status"] = "REPEATED_CURSOR"
                if allow_partial:
                    return rows, False, "REPEATED_CURSOR"
                raise DeltaReconciliationReadError(f"{endpoint}: repeated pagination cursor")
            seen_cursors.add(after)
            query["after"] = after
        # Hitting the per-endpoint hard cap is not a complete snapshot.
        return rows, False, "ENDPOINT_PAGE_LIMIT_REACHED"

    @staticmethod
    def _epoch_microseconds(value: str, label: str) -> int:
        """Convert timezone-aware ISO-8601 to Delta's documented epoch microseconds."""
        from core.execution.historical_evidence_window import _utc
        stamp = _utc(value, label)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = stamp - epoch
        return ((delta.days * 86400 + delta.seconds) * 1_000_000) + delta.microseconds

    @classmethod
    def _window_query(cls, window_start: str | None, window_end: str | None,
                      overlap_seconds: int) -> dict[str, int]:
        if window_start is None:
            return {}
        from core.execution.historical_evidence_window import _utc
        start = _utc(window_start, "window_start") - timedelta(seconds=overlap_seconds)
        end = _utc(window_end, "window_end") + timedelta(seconds=overlap_seconds)
        return {
            "start_time": cls._epoch_microseconds(start.isoformat(), "effective_window_start"),
            "end_time": cls._epoch_microseconds(end.isoformat(), "effective_window_end"),
        }

    def capture(
        self, *, product_id: int, window_start: str | None = None,
        window_end: str | None = None, overlap_seconds: int = 60,
        endpoints: tuple[str, ...] | None = None,
        max_pages_per_endpoint: int = 100,
        max_total_pages: int = 500,
        request_timeout_seconds: int = 20,
        retry_budget: int = 2,
        allow_partial: bool = False,
        max_records_per_endpoint: int = 100000,
        max_total_records: int = 1000000,
    ) -> DeltaReconciliationSnapshot:
        """Read only selected allowlisted endpoint categories.

        Omitting endpoints preserves the Phase 199 all-endpoint behavior.
        Selection is validated before the first authenticated GET.
        """
        if not bool(getattr(self._rest, "authenticated", False)):
            raise DeltaReconciliationReadError("authenticated Delta REST client required")
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
            raise ValueError("product_id must be a positive integer")
        if (window_start is None) != (window_end is None):
            raise ValueError("window_start and window_end must be supplied together")
        if isinstance(overlap_seconds, bool) or not isinstance(overlap_seconds, int) or not 0 <= overlap_seconds <= 3600:
            raise ValueError("overlap_seconds must be an integer from 0 to 3600")
        supported = ("open_orders", "order_history", "fills", "positions", "wallet_transactions")
        selected = supported if endpoints is None else endpoints
        if (not isinstance(selected, tuple) or not selected
                or any(not isinstance(item, str) or item not in supported for item in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError("endpoints must be a non-empty tuple of unique supported endpoint names")
        if (isinstance(max_pages_per_endpoint, bool) or not isinstance(max_pages_per_endpoint, int)
                or not 1 <= max_pages_per_endpoint <= 100):
            raise ValueError("max_pages_per_endpoint must be between 1 and 100")
        if (isinstance(max_total_pages, bool) or not isinstance(max_total_pages, int)
                or not 1 <= max_total_pages <= 2500):
            raise ValueError("max_total_pages must be between 1 and 2500")
        if (isinstance(request_timeout_seconds, bool) or not isinstance(request_timeout_seconds, int)
                or not 1 <= request_timeout_seconds <= 60):
            raise ValueError("request_timeout_seconds must be between 1 and 60")
        if (isinstance(retry_budget, bool) or not isinstance(retry_budget, int)
                or not 0 <= retry_budget <= 5):
            raise ValueError("retry_budget must be between 0 and 5")
        if not isinstance(allow_partial, bool):
            raise ValueError("allow_partial must be a boolean")
        if (isinstance(max_records_per_endpoint, bool) or not isinstance(max_records_per_endpoint, int)
                or not 1 <= max_records_per_endpoint <= 100000):
            raise ValueError("max_records_per_endpoint must be between 1 and 100000")
        if (isinstance(max_total_records, bool) or not isinstance(max_total_records, int)
                or not 1 <= max_total_records <= 1000000):
            raise ValueError("max_total_records must be between 1 and 1000000")
        if window_start is not None:
            from core.execution.historical_evidence_window import _utc
            start = _utc(window_start, "window_start")
            end = _utc(window_end, "window_end")
            if start >= end:
                raise ValueError("window_start must precede window_end")
        time_query = self._window_query(window_start, window_end, overlap_seconds)

        # Endpoint paths are a fixed read-only allowlist. Calls remain sequential
        # GETs; an unselected endpoint is never contacted. The shared page budget
        # applies across all selected endpoint reads in this capture.
        page_budget = {"max": max_total_pages, "used": 0}
        record_budget = {"max": max_total_records, "used": 0}
        page_provenance: list[dict[str, Any]] = []
        open_orders, open_complete, open_status = ([], True, "NOT_REQUESTED")
        order_history, history_complete, history_status = ([], True, "NOT_REQUESTED")
        fills, fills_complete, fills_status = ([], True, "NOT_REQUESTED")
        positions, positions_complete, positions_status = ([], True, "NOT_REQUESTED")
        wallet_transactions, wallet_complete, wallet_status = ([], True, "NOT_REQUESTED")
        if "open_orders" in selected:
            open_orders, open_complete, open_status = self._read_all(
                "/v2/orders", {"product_ids": str(product_id), "state": "open", "page_size": 50, **time_query},
                ("id", "product_id", "size"), max_pages=max_pages_per_endpoint,
                page_budget=page_budget, page_provenance=page_provenance,
                request_timeout_seconds=request_timeout_seconds, retry_budget=retry_budget,
                allow_partial=allow_partial, max_records_per_endpoint=max_records_per_endpoint,
                record_budget=record_budget,
            )
        if "order_history" in selected:
            order_history, history_complete, history_status = self._read_all(
                "/v2/orders/history", {"product_ids": str(product_id), "page_size": 50, **time_query},
                ("id", "product_id", "size"), max_pages=max_pages_per_endpoint,
                page_budget=page_budget, page_provenance=page_provenance,
                request_timeout_seconds=request_timeout_seconds, retry_budget=retry_budget,
                allow_partial=allow_partial,
            )
        if "fills" in selected:
            fills, fills_complete, fills_status = self._read_all(
                "/v2/fills", {"product_ids": str(product_id), "page_size": 50, **time_query},
                ("id", "order_id", "product_id", "size", "price", "side"),
                max_pages=max_pages_per_endpoint, page_budget=page_budget,
                page_provenance=page_provenance,
                request_timeout_seconds=request_timeout_seconds, retry_budget=retry_budget,
                allow_partial=allow_partial,
            )
        if "positions" in selected:
            positions, positions_complete, positions_status = self._read_all(
                "/v2/positions", {"product_id": product_id}, ("size",), paginated=False,
                max_pages=max_pages_per_endpoint, page_budget=page_budget,
                page_provenance=page_provenance,
                request_timeout_seconds=request_timeout_seconds, retry_budget=retry_budget,
                allow_partial=allow_partial,
            )
            # Delta positions are current snapshots, not a historical event stream.
            positions = [
                (dict(row) if row.get("product_id") is not None else {**row, "query_product_id": product_id})
                for row in positions
            ]
        if "wallet_transactions" in selected:
            # Wallet transactions are account-wide; product_id is not sent.
            wallet_transactions, wallet_complete, wallet_status = self._read_all(
                "/v2/wallet/transactions", {"page_size": 50, **time_query},
                ("id", "amount", "transaction_type", "created_at"),
                max_pages=max_pages_per_endpoint, page_budget=page_budget,
                page_provenance=page_provenance,
                request_timeout_seconds=request_timeout_seconds, retry_budget=retry_budget,
                allow_partial=allow_partial,
            )

        endpoint_complete = {
            "open_orders": (open_complete, open_status),
            "order_history": (history_complete, history_status),
            "fills": (fills_complete, fills_status),
            "positions": (positions_complete, positions_status),
            "wallet_transactions": (wallet_complete, wallet_status),
        }
        complete = all(endpoint_complete[name][0] for name in selected)
        return DeltaReconciliationSnapshot(
            captured_at=datetime.now(timezone.utc).isoformat(),
            product_id=product_id,
            open_orders=tuple(open_orders),
            order_history=tuple(order_history),
            fills=tuple(fills),
            positions=tuple(positions),
            wallet_transactions=tuple(wallet_transactions),
            complete=complete,
            page_provenance=tuple(page_provenance),
            window_start=window_start,
            window_end=window_end,
            overlap_seconds=overlap_seconds,
            venue_time_filter=dict(time_query),
            endpoint_status={
                name: endpoint_complete[name][1]
                for name in selected
            },
        )
