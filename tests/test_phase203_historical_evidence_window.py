from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.execution.historical_evidence_window import (
    HistoricalEvidenceError, audit_historical_evidence_window,
)
from core.execution.testnet_reconciliation_coordinator import TestnetReconciliationCoordinator


START = "2026-10-01T09:00:00Z"
END = "2026-10-01T10:00:00Z"


def test_window_is_timezone_aware_inclusive_and_applies_overlap():
    report = audit_historical_evidence_window(
        orders=[{"id": 1, "created_at": "2026-10-01T08:59:30Z"},
                {"id": 2, "created_at": "2026-10-01T11:00:01Z"}],
        fills=[], wallet_transactions=[], window_start=START, window_end=END,
        overlap_seconds=60,
    )
    assert report["counts"]["orders_in_window"] == 1
    assert report["counts"]["orders_outside_window"] == 1
    assert report["selection_semantics"].startswith("CLIENT_SIDE_FILTER")
    assert report["venue_window_exhaustiveness_certified"] is False


def test_naive_or_reversed_window_rejected():
    with pytest.raises(HistoricalEvidenceError, match="timezone"):
        audit_historical_evidence_window(orders=[], fills=[], wallet_transactions=[],
                                         window_start="2026-10-01T09:00:00", window_end=END)
    with pytest.raises(HistoricalEvidenceError, match="precede"):
        audit_historical_evidence_window(orders=[], fills=[], wallet_transactions=[],
                                         window_start=END, window_end=START)


def test_fill_order_linkage_duplicates_reversal_and_new_position_are_reported():
    report = audit_historical_evidence_window(
        orders=[{"id": 10, "created_at": START}],
        fills=[
            {"id": 1, "order_id": 10, "created_at": START, "new_position": "1"},
            {"id": 1, "order_id": 99, "created_at": END, "new_position": "NaN"},
        ],
        wallet_transactions=[
            {"id": 7, "created_at": START, "transaction_type": "revert", "meta_data": {"original_id": 6}},
            {"id": 7, "created_at": END, "transaction_type": "funding"},
        ],
        window_start=START, window_end=END, overlap_seconds=0,
    )
    assert report["duplicate_fill_ids"] == ["1"]
    assert report["duplicate_wallet_transaction_ids"] == ["7"]
    assert report["orphan_fills"][0]["reason"] == "ORDER_LINK_NOT_FOUND_IN_WINDOW"
    assert report["reversal_events"][0]["status"] == "REVERSAL_REQUIRES_OPERATOR_LINKAGE"
    assert any(x["status"] == "INVALID_NEW_POSITION" for x in report["new_position_observations"])
    assert report["wallet_amounts_applied_to_position"] is False


def test_missing_event_timestamps_are_explicitly_reported():
    report = audit_historical_evidence_window(
        orders=[{"id": 1}], fills=[{"id": 2}], wallet_transactions=[{"id": 3}],
        window_start=START, window_end=END,
    )
    assert report["missing_timestamps"] == {"orders": ["1"], "fills": ["2"], "wallet_transactions": ["3"]}


def test_coordinator_holds_for_window_linkage_and_reversal_findings(tmp_path):
    order = {"id": 10, "product_id": 84, "size": "1", "side": "buy", "created_at": START}
    fill = {"id": 11, "order_id": 999, "product_id": 84, "size": "1", "price": "100",
            "side": "buy", "fill_type": "normal", "created_at": START}
    txn = {"id": 12, "product_id": 84, "amount": "-0.1", "transaction_type": "revert",
           "created_at": START, "meta_data": {"original_id": 8}}
    snapshot = SimpleNamespace(
        product_id=84, captured_at=END, open_orders=(order,), order_history=(), fills=(fill,),
        positions=({"size": "1", "query_product_id": 84},), wallet_transactions=(txn,),
        complete=True, endpoint_status={"open_orders": "OK", "order_history": "OK", "fills": "OK", "positions": "OK", "wallet_transactions": "OK"},
        window_start=START, window_end=END, overlap_seconds=60,
    )
    class Exchange:
        def get_reconciliation_snapshot(self, *, product_id):
            return snapshot
    report = TestnetReconciliationCoordinator(Exchange(), tmp_path / "missing.jsonl").run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "HISTORICAL_FILL_ORDER_LINKAGE_UNRESOLVED" in report["hold_reasons"]
    assert "HISTORICAL_WALLET_REVERSALS_REQUIRE_REVIEW" in report["hold_reasons"]
    assert report["safe_to_resume_submissions"] is False
    assert report["automatic_action"] == "NONE"


def test_new_position_sequence_is_checked_against_next_fill_delta():
    report = audit_historical_evidence_window(
        orders=[{"id": 10, "created_at": START}],
        fills=[
            {"id": 1, "order_id": 10, "created_at": "2026-10-01T09:01:00Z",
             "side": "buy", "size": "1", "new_position": "1"},
            {"id": 2, "order_id": 10, "created_at": "2026-10-01T09:02:00Z",
             "side": "sell", "size": "0.25", "new_position": "0.75"},
            {"id": 3, "order_id": 10, "created_at": "2026-10-01T09:03:00Z",
             "side": "buy", "size": "0.5", "new_position": "2"},
        ], wallet_transactions=[], window_start=START, window_end=END, overlap_seconds=0,
    )
    statuses = [x["status"] for x in report["new_position_observations"]]
    assert statuses == ["BASELINE_REQUIRED", "MATCH", "MISMATCH"]


def test_report_distinguishes_documented_venue_filter_from_client_only_selection():
    base = dict(orders=[], fills=[], wallet_transactions=[],
                window_start="2026-10-01T09:00:00Z", window_end="2026-10-01T10:00:00Z")
    client_only = audit_historical_evidence_window(**base)
    venue_filtered = audit_historical_evidence_window(**base, venue_time_filter={"start_time": 1, "end_time": 2})
    assert client_only["selection_semantics"].startswith("CLIENT_SIDE_FILTER")
    assert venue_filtered["selection_semantics"] == "VENUE_START_END_TIME_FILTER_PLUS_CLIENT_SIDE_AUDIT"
    assert venue_filtered["venue_window_exhaustiveness_certified"] is False
