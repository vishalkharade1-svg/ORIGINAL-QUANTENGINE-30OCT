from __future__ import annotations

import pytest

from core.exchanges.delta.reconciliation_read_adapter import (
    DeltaReconciliationReadAdapter,
    DeltaReconciliationReadError,
)


class FakeREST:
    authenticated = True

    def __init__(self, responses=None, error_at=None):
        self.responses = responses or {}
        self.error_at = error_at
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if self.error_at == (path, params.get("state")):
            raise RuntimeError("simulated failure with secret-do-not-leak")
        key = (path, params.get("state"))
        return self.responses.get(key, {"success": True, "result": [], "meta": {"after": None}})


def test_read_adapter_uses_only_authenticated_gets_and_scoped_product():
    rest = FakeREST()
    snap = DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert len(rest.calls) == 5
    assert all(path in {"/v2/orders", "/v2/orders/history", "/v2/fills", "/v2/positions", "/v2/wallet/transactions"} for path, _ in rest.calls)
    assert all((params.get("product_ids") == "84" if path in {"/v2/orders", "/v2/orders/history", "/v2/fills"} else (params.get("product_id") == 84 if path == "/v2/positions" else "product_id" not in params)) for path, params in rest.calls)
    assert next(params for path, params in rest.calls if path == "/v2/wallet/transactions") == {"page_size": 50}
    assert snap.complete is True
    assert snap.endpoint_status == {"open_orders": "OK", "order_history": "OK", "fills": "OK", "positions": "OK", "wallet_transactions": "OK"}


def test_missing_authentication_fails_before_any_call():
    rest = FakeREST()
    rest.authenticated = False
    with pytest.raises(DeltaReconciliationReadError, match="authenticated"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert rest.calls == []


@pytest.mark.parametrize("product_id", [0, -1, True, "84", None])
def test_invalid_product_id_rejected(product_id):
    with pytest.raises(ValueError):
        DeltaReconciliationReadAdapter(FakeREST()).capture(product_id=product_id)


def test_bad_envelope_fails_closed():
    rest = FakeREST({("/v2/orders", "open"): {"success": False, "result": [], "meta": {"after": None}}})
    with pytest.raises(DeltaReconciliationReadError, match="success flag"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert len(rest.calls) == 1


def test_bad_row_schema_fails_closed():
    rest = FakeREST({("/v2/orders", "open"): {"success": True, "result": [{"id": 1}], "meta": {"after": None}}})
    with pytest.raises(DeltaReconciliationReadError, match="missing required fields"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)


def test_transport_error_is_redacted_and_aborts_partial_snapshot():
    rest = FakeREST(error_at=("/v2/orders/history", None))
    with pytest.raises(DeltaReconciliationReadError) as exc:
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert "secret-do-not-leak" not in str(exc.value)
    assert len(rest.calls) == 2


def test_pagination_indicator_marks_snapshot_incomplete():
    rest = FakeREST({("/v2/fills", None): {
        "success": True, "result": [], "meta": {"after": "cursor-2"}
    }})
    original_get = rest.get
    def one_page_only(path, params=None):
        if path == "/v2/fills" and params.get("after") == "cursor-2":
            rest.calls.append((path, dict(params or {})))
            return {"success": True, "result": [], "meta": {"after": "cursor-2"}}
        return original_get(path, params)
    rest.get = one_page_only
    with pytest.raises(DeltaReconciliationReadError, match="repeated pagination cursor"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)


def test_required_fields_enforced_for_fill_evidence():
    rest = FakeREST({("/v2/fills", None): {
        "success": True, "result": [{"id": 1, "order_id": 7, "product_id": 84, "size": "1", "side": "buy"}], "meta": {"after": None}
    }})
    with pytest.raises(DeltaReconciliationReadError, match="price"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)


def test_delta_exchange_exposes_read_only_snapshot_method():
    from core.exchanges.delta.delta_exchange import DeltaExchange
    rest = FakeREST()
    exchange = DeltaExchange(api_key="synthetic-key", api_secret="synthetic-secret", rest=rest)
    snapshot = exchange.get_reconciliation_snapshot(product_id=84)
    assert snapshot.complete is True
    assert len(rest.calls) == 5
    assert all(call[0] != "/v2/orders" or call[1].get("state") == "open" for call in rest.calls)
    assert any(call[0] == "/v2/orders/history" for call in rest.calls)


def test_cursor_pagination_fetches_every_page_and_uses_official_after_parameter():
    rest = FakeREST({
        ("/v2/orders", "open"): {"success": True, "result": [], "meta": {"after": "cursor-next"}},
    })
    # Fake the second open-order page and default all other endpoints to empty.
    original_get = rest.get
    def paged_get(path, params=None):
        if path == "/v2/orders" and params.get("after") == "cursor-next":
            rest.calls.append((path, dict(params or {})))
            return {"success": True, "result": [], "meta": {"after": None}}
        return original_get(path, params)
    rest.get = paged_get
    snap = DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert snap.complete is True
    assert any(path == "/v2/orders" and params.get("after") == "cursor-next" for path, params in rest.calls)


def test_missing_pagination_metadata_cannot_be_declared_complete():
    rest = FakeREST({("/v2/orders", "open"): {"success": True, "result": []}})
    snap = DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert snap.complete is False
    assert snap.endpoint_status["open_orders"] == "INCOMPLETE_PAGINATION"


def test_documented_position_object_shape_is_normalized_without_fabricating_product_id():
    rest = FakeREST({("/v2/positions", None): {
        "success": True, "result": {"size": 0, "entry_price": "0"}
    }})
    snap = DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert snap.complete is True
    assert snap.positions == ({"size": 0, "entry_price": "0", "query_product_id": 84},)
    assert "product_id" not in snap.positions[0]


def test_wallet_transactions_are_cursor_paginated_and_account_wide():
    rest = FakeREST({("/v2/wallet/transactions", None): {
        "success": True,
        "result": [{"id": 1, "amount": "-1", "transaction_type": "funding", "created_at": "2026-10-30T00:00:00Z", "product_id": 84}],
        "meta": {"after": "wallet-next"},
    }})
    original_get = rest.get
    def paged_get(path, params=None):
        if path == "/v2/wallet/transactions" and params.get("after") == "wallet-next":
            rest.calls.append((path, dict(params or {})))
            return {"success": True, "result": [], "meta": {"after": None}}
        return original_get(path, params)
    rest.get = paged_get
    snapshot = DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    assert snapshot.complete is True
    assert len(snapshot.wallet_transactions) == 1
    first = next(params for path, params in rest.calls if path == "/v2/wallet/transactions")
    assert first == {"page_size": 50}
    assert any(path == "/v2/wallet/transactions" and params.get("after") == "wallet-next" for path, params in rest.calls)


def test_wallet_transaction_missing_required_field_fails_closed():
    rest = FakeREST({("/v2/wallet/transactions", None): {
        "success": True, "result": [{"id": 1, "amount": "-1", "transaction_type": "funding"}],
        "meta": {"after": None},
    }})
    with pytest.raises(DeltaReconciliationReadError, match="created_at"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84)


def test_optional_historical_window_is_validated_and_preserved_without_claiming_venue_filter():
    rest = FakeREST()
    snapshot = DeltaReconciliationReadAdapter(rest).capture(
        product_id=84, window_start="2026-10-01T09:00:00Z",
        window_end="2026-10-01T10:00:00Z", overlap_seconds=120,
    )
    assert snapshot.window_start == "2026-10-01T09:00:00Z"
    assert snapshot.window_end == "2026-10-01T10:00:00Z"
    assert snapshot.overlap_seconds == 120
    assert snapshot.as_reconciler_inputs()["window_start"] == snapshot.window_start


def test_historical_window_requires_both_timezone_aware_ordered_bounds():
    rest = FakeREST()
    with pytest.raises(ValueError, match="supplied together"):
        DeltaReconciliationReadAdapter(rest).capture(product_id=84, window_start="2026-10-01T09:00:00Z")
    with pytest.raises(ValueError, match="timezone"):
        DeltaReconciliationReadAdapter(rest).capture(
            product_id=84, window_start="2026-10-01T09:00:00",
            window_end="2026-10-01T10:00:00Z",
        )
    assert rest.calls == []


def test_historical_window_uses_delta_documented_epoch_microsecond_filters_and_overlap():
    rest = FakeREST()
    snapshot = DeltaReconciliationReadAdapter(rest).capture(
        product_id=84,
        window_start="2026-10-01T09:00:00Z",
        window_end="2026-10-01T10:00:00Z",
        overlap_seconds=120,
    )
    # 08:58Z and 10:02Z, represented as epoch microseconds.
    expected_start = 1790845080000000
    expected_end = 1790848920000000
    for path in ("/v2/orders", "/v2/orders/history", "/v2/fills", "/v2/wallet/transactions"):
        params = next(params for called_path, params in rest.calls if called_path == path)
        assert params["start_time"] == expected_start
        assert params["end_time"] == expected_end
    assert snapshot.venue_time_filter == {"start_time": expected_start, "end_time": expected_end}
    assert snapshot.as_reconciler_inputs()["venue_time_filter"] == snapshot.venue_time_filter
    position_params = next(params for path, params in rest.calls if path == "/v2/positions")
    assert "start_time" not in position_params and "end_time" not in position_params


def test_no_window_omits_time_filters_and_uses_documented_product_ids_parameter():
    rest = FakeREST()
    DeltaReconciliationReadAdapter(rest).capture(product_id=84)
    for path, params in rest.calls:
        if path == "/v2/positions":
            continue
        assert "start_time" not in params and "end_time" not in params
        if path in {"/v2/orders", "/v2/orders/history", "/v2/fills"}:
            assert params["product_ids"] == "84"
            assert "product_id" not in params


def test_delta_window_filter_rejects_non_integer_or_excessive_overlap_before_io():
    rest = FakeREST()
    with pytest.raises(ValueError):
        DeltaReconciliationReadAdapter(rest).capture(
            product_id=84, window_start="2026-10-01T09:00:00Z",
            window_end="2026-10-01T10:00:00Z", overlap_seconds=True,
        )
    assert rest.calls == []



def test_selected_endpoint_scope_issues_only_allowlisted_get():
    rest = FakeREST()
    snapshot = DeltaReconciliationReadAdapter(rest).capture(
        product_id=84, endpoints=("fills",)
    )
    assert snapshot.complete is True
    assert snapshot.endpoint_status == {"fills": "OK"}
    assert rest.calls
    assert all(path == "/v2/fills" for path, _ in rest.calls)
    assert snapshot.open_orders == ()
    assert snapshot.order_history == ()
    assert snapshot.positions == ()
    assert snapshot.wallet_transactions == ()


def test_invalid_endpoint_selection_fails_before_any_authenticated_get():
    rest = FakeREST()
    with pytest.raises(ValueError, match="supported endpoint"):
        DeltaReconciliationReadAdapter(rest).capture(
            product_id=84, endpoints=("place_order",)
        )
    assert rest.calls == []



def test_page_provenance_records_cursor_count_and_content_hash():
    rows = [{"id": 11, "product_id": 84, "size": "1"}]
    rest = FakeREST({("/v2/orders", "open"): {
        "success": True, "result": rows, "meta": {"after": "orders-next"}
    }})
    original_get = rest.get

    def paged_get(path, params=None):
        if path == "/v2/orders" and params.get("after") == "orders-next":
            rest.calls.append((path, dict(params or {})))
            return {"success": True, "result": [], "meta": {"after": None}}
        return original_get(path, params)

    rest.get = paged_get
    snap = DeltaReconciliationReadAdapter(rest).capture(
        product_id=84, endpoints=("open_orders",)
    )
    pages = list(snap.page_provenance)
    assert len(pages) == 2
    assert pages[0]["page_index"] == 0
    assert pages[0]["response_cursor"] == "orders-next"
    assert pages[0]["record_count"] == 1
    assert len(pages[0]["content_sha256"]) == 64
    assert pages[1]["request_cursor"] == "orders-next"
    assert snap.complete is True


def test_shared_page_budget_prevents_calls_to_later_endpoints():
    rest = FakeREST()
    snap = DeltaReconciliationReadAdapter(rest).capture(
        product_id=84, endpoints=("open_orders", "fills"), max_total_pages=1
    )
    assert len(rest.calls) == 1
    assert rest.calls[0][0] == "/v2/orders"
    assert snap.endpoint_status == {
        "open_orders": "OK", "fills": "PAGE_BUDGET_REACHED"
    }
    assert snap.complete is False
    assert len(snap.page_provenance) == 1


def test_per_endpoint_page_limit_is_reported_as_incomplete():
    rest = FakeREST({("/v2/orders", "open"): {
        "success": True, "result": [], "meta": {"after": "next-page"}
    }})
    snap = DeltaReconciliationReadAdapter(rest).capture(
        product_id=84, endpoints=("open_orders",), max_pages_per_endpoint=1
    )
    assert len(rest.calls) == 1
    assert snap.complete is False
    assert snap.endpoint_status["open_orders"] == "ENDPOINT_PAGE_LIMIT_REACHED"


def test_repeated_nonempty_response_page_is_rejected():
    rows = [{"id": 11, "product_id": 84, "size": "1"}]
    rest = FakeREST({("/v2/orders", "open"): {
        "success": True, "result": rows, "meta": {"after": "next-page"}
    }})
    original_get = rest.get

    def repeated_get(path, params=None):
        if path == "/v2/orders" and params.get("after") == "next-page":
            rest.calls.append((path, dict(params or {})))
            return {"success": True, "result": rows, "meta": {"after": None}}
        return original_get(path, params)

    rest.get = repeated_get
    with pytest.raises(DeltaReconciliationReadError, match="repeated response page"):
        DeltaReconciliationReadAdapter(rest).capture(
            product_id=84, endpoints=("open_orders",)
        )
