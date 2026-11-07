"""Read-only Delta REST evidence adapter for durable order reconciliation.

This module performs authenticated GETs only. It never places, cancels, or
retries orders. A snapshot is marked complete only when every endpoint has a
valid response envelope and the venue response does not indicate additional
pages. Any ambiguity raises DeltaReconciliationReadError so callers cannot
mistake partial evidence for a clean reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    ) -> tuple[list[dict[str, Any]], bool]:
        rows: list[dict[str, Any]] = []
        seen_cursors: set[str] = set()
        query = dict(params)
        for _page_number in range(max_pages):
            try:
                response = self._rest.get(endpoint, params=query)
            except Exception as exc:
                # Do not propagate request URLs, headers, or exception strings
                # that might contain credentials.
                raise DeltaReconciliationReadError(
                    f"{endpoint}: authenticated read failed ({type(exc).__name__})"
                ) from None
            page_rows, after = self._envelope(response, endpoint)
            self._require_fields(page_rows, required, endpoint)
            rows.extend(page_rows)
            if not paginated:
                return rows, after is None
            if after == "__PAGINATION_METADATA_MISSING__":
                return rows, False
            if after is None:
                return rows, True
            if after in seen_cursors:
                raise DeltaReconciliationReadError(f"{endpoint}: repeated pagination cursor")
            seen_cursors.add(after)
            query["after"] = after
        # Hitting the hard cap is not a complete snapshot. Never silently
        # declare it complete or keep querying indefinitely.
        return rows, False

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
        if window_start is not None:
            from core.execution.historical_evidence_window import _utc
            start = _utc(window_start, "window_start")
            end = _utc(window_end, "window_end")
            if start >= end:
                raise ValueError("window_start must precede window_end")
        time_query = self._window_query(window_start, window_end, overlap_seconds)

        # Endpoint paths are a fixed read-only allowlist. Calls remain sequential
        # GETs; an unselected endpoint is never contacted.
        open_orders, open_complete = ([], True)
        order_history, history_complete = ([], True)
        fills, fills_complete = ([], True)
        positions, positions_complete = ([], True)
        wallet_transactions, wallet_complete = ([], True)
        if "open_orders" in selected:
            open_orders, open_complete = self._read_all(
                "/v2/orders", {"product_ids": str(product_id), "state": "open", "page_size": 50, **time_query},
                ("id", "product_id", "size"),
            )
        if "order_history" in selected:
            order_history, history_complete = self._read_all(
                "/v2/orders/history", {"product_ids": str(product_id), "page_size": 50, **time_query},
                ("id", "product_id", "size"),
            )
        if "fills" in selected:
            fills, fills_complete = self._read_all(
                "/v2/fills", {"product_ids": str(product_id), "page_size": 50, **time_query},
                ("id", "order_id", "product_id", "size", "price", "side"),
            )
        if "positions" in selected:
            positions, positions_complete = self._read_all(
                "/v2/positions", {"product_id": product_id}, ("size",), paginated=False,
            )
            # Delta positions are current snapshots, not a historical event stream.
            positions = [
                (dict(row) if row.get("product_id") is not None else {**row, "query_product_id": product_id})
                for row in positions
            ]
        if "wallet_transactions" in selected:
            # Wallet transactions are account-wide; product_id is not sent.
            wallet_transactions, wallet_complete = self._read_all(
                "/v2/wallet/transactions", {"page_size": 50, **time_query},
                ("id", "amount", "transaction_type", "created_at"),
            )

        endpoint_complete = {
            "open_orders": open_complete,
            "order_history": history_complete,
            "fills": fills_complete,
            "positions": positions_complete,
            "wallet_transactions": wallet_complete,
        }
        complete = all(endpoint_complete[name] for name in selected)
        return DeltaReconciliationSnapshot(
            captured_at=datetime.now(timezone.utc).isoformat(),
            product_id=product_id,
            open_orders=tuple(open_orders),
            order_history=tuple(order_history),
            fills=tuple(fills),
            positions=tuple(positions),
            wallet_transactions=tuple(wallet_transactions),
            complete=complete,
            window_start=window_start,
            window_end=window_end,
            overlap_seconds=overlap_seconds,
            venue_time_filter=dict(time_query),
            endpoint_status={
                name: "OK" if endpoint_complete[name] else "INCOMPLETE_PAGINATION"
                for name in selected
            },
        )
