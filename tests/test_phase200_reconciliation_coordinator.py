from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.execution.testnet_reconciliation_coordinator import (
    ReconciliationCoordinatorError,
    TestnetReconciliationCoordinator,
)


class FakeExchange:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def get_reconciliation_snapshot(self, *, product_id):
        self.calls.append(product_id)
        return self.snapshot


def snap(**overrides):
    values = dict(
        product_id=84, captured_at="2026-10-30T00:00:00+00:00",
        open_orders=(), order_history=(), fills=(), positions=({"size": "0", "query_product_id": 84},),
        wallet_transactions=(), complete=True, endpoint_status={"open_orders": "OK", "order_history": "OK", "fills": "OK", "positions": "OK", "wallet_transactions": "OK"},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_empty_journal_complete_flat_snapshot_has_no_prior_order_hold(tmp_path):
    ex = FakeExchange(snap())
    report = TestnetReconciliationCoordinator(ex, tmp_path / "missing.jsonl").run(product_id=84)
    assert report["decision"] == "NO_PRIOR_ORDERS_CLEAR"
    assert report["safe_to_resume_submissions"] is False
    assert report["automatic_action"] == "NONE"
    assert ex.calls == [84]


def test_incomplete_snapshot_holds(tmp_path):
    report = TestnetReconciliationCoordinator(FakeExchange(snap(complete=False)), tmp_path / "x").run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "EXCHANGE_SNAPSHOT_INCOMPLETE" in report["hold_reasons"]


def test_nonzero_position_holds_even_when_journal_empty(tmp_path):
    report = TestnetReconciliationCoordinator(FakeExchange(snap(positions=({"size": "0.01", "query_product_id": 84},))), tmp_path / "x").run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "NONZERO_POSITION_REQUIRES_OPERATOR_REVIEW" in report["hold_reasons"]


def test_out_of_scope_order_rejected(tmp_path):
    order = {"id": 1, "product_id": 85, "size": "1", "state": "open"}
    with pytest.raises(ReconciliationCoordinatorError, match="product scope"):
        TestnetReconciliationCoordinator(FakeExchange(snap(open_orders=(order,))), tmp_path / "x").run(product_id=84)


def test_duplicate_open_and_history_order_is_deduplicated(tmp_path):
    order = {"id": 1, "product_id": 84, "size": "1", "state": "open", "client_order_id": "c1"}
    report = TestnetReconciliationCoordinator(FakeExchange(snap(open_orders=(order,), order_history=(dict(order),))), tmp_path / "x").run(product_id=84)
    assert report["orders"]["orders_reviewed"] == 0


def test_conflicting_open_and_history_order_fails_closed(tmp_path):
    a = {"id": 1, "product_id": 84, "size": "1", "state": "open"}
    b = {"id": 1, "product_id": 84, "size": "2", "state": "open"}
    with pytest.raises(ReconciliationCoordinatorError, match="contradictory"):
        TestnetReconciliationCoordinator(FakeExchange(snap(open_orders=(a,), order_history=(b,))), tmp_path / "x").run(product_id=84)


def test_position_scope_mismatch_fails_closed(tmp_path):
    with pytest.raises(ReconciliationCoordinatorError, match="position product scope"):
        TestnetReconciliationCoordinator(FakeExchange(snap(positions=({"size": "0", "product_id": 85},))), tmp_path / "x").run(product_id=84)


def test_invalid_position_size_fails_closed(tmp_path):
    with pytest.raises(ReconciliationCoordinatorError, match="position size"):
        TestnetReconciliationCoordinator(FakeExchange(snap(positions=({"size": "NaN", "query_product_id": 84},))), tmp_path / "x").run(product_id=84)


def test_invalid_product_id_rejected_before_exchange_call(tmp_path):
    ex = FakeExchange(snap())
    with pytest.raises(ValueError):
        TestnetReconciliationCoordinator(ex, tmp_path / "x").run(product_id=True)
    assert ex.calls == []


def test_exchange_failure_is_redacted_and_fail_closed(tmp_path):
    class Broken:
        def get_reconciliation_snapshot(self, *, product_id):
            raise RuntimeError("secret-token-must-not-leak")
    with pytest.raises(ReconciliationCoordinatorError) as exc:
        TestnetReconciliationCoordinator(Broken(), tmp_path / "x").run(product_id=84)
    assert "secret-token" not in str(exc.value)


def test_no_automatic_actions_are_ever_emitted(tmp_path):
    report = TestnetReconciliationCoordinator(FakeExchange(snap()), tmp_path / "x").run(product_id=84)
    assert report["automatic_action"] == "NONE"
    assert report["safe_to_resume_submissions"] is False


def test_existing_durable_order_keeps_coordinator_on_hold(tmp_path):
    import json
    ledger = tmp_path / "ledger.jsonl"
    events = [
        {"timestamp_utc": 1, "event": "ORDER_RESERVED", "data": {
            "cl_ord_id": "QE-200", "product_id": 84, "symbol": "BTCUSD",
            "order_size": "1", "side": "buy", "limit_price": "60000",
        }},
        {"timestamp_utc": 2, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "QE-200"}},
    ]
    ledger.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    report = TestnetReconciliationCoordinator(FakeExchange(snap()), ledger).run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "ORDER_RECONCILIATION_UNRESOLVED" in report["hold_reasons"]
    assert report["orders"]["orders_reviewed"] == 1
    assert report["safe_to_resume_submissions"] is False


def test_position_fill_mismatch_keeps_coordinator_on_hold(tmp_path):
    fill = {"id": 101, "order_id": 7, "product_id": 84,
            "side": "buy", "size": "2", "price": "100", "fill_type": "normal"}
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(fills=(fill,), positions=({"size": "1", "query_product_id": 84},))),
        tmp_path / "x",
    ).run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "POSITION_FILL_QUANTITY_MISMATCH" in report["hold_reasons"]
    assert report["position_fill_reconciliation"]["difference"] == "-1"
    assert report["safe_to_resume_submissions"] is False


def test_missing_position_row_is_ambiguous_and_keeps_hold(tmp_path):
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(positions=())), tmp_path / "x"
    ).run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "POSITION_FILL_EVIDENCE_AMBIGUOUS" in report["hold_reasons"]


def test_product_linked_funding_adjustment_forces_operator_review(tmp_path):
    txn = {"id": 77, "product_id": 84, "transaction_type": "funding",
           "amount": "-0.25", "created_at": "2026-10-30T00:00:00Z"}
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(wallet_transactions=(txn,))), tmp_path / "x"
    ).run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "PRODUCT_LINKED_WALLET_ADJUSTMENTS_REQUIRE_REVIEW" in report["hold_reasons"]
    assert report["wallet_adjustment_evidence"]["quantity_adjustment_applied"] is False


def test_unscoped_settlement_adjustment_is_not_assigned_to_product(tmp_path):
    txn = {"id": 78, "transaction_type": "settlement", "amount": "1",
           "created_at": "2026-10-30T00:00:00Z"}
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(wallet_transactions=(txn,))), tmp_path / "x"
    ).run(product_id=84)
    assert report["decision"] == "HOLD"
    assert "UNSCOPED_WALLET_ADJUSTMENTS_AMBIGUOUS" in report["hold_reasons"]
    assert report["wallet_adjustment_evidence"]["product_linked_events"] == []


def test_unrelated_deposit_does_not_get_misclassified_as_position_event(tmp_path):
    txn = {"id": 79, "transaction_type": "deposit", "amount": "10",
           "created_at": "2026-10-30T00:00:00Z"}
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(wallet_transactions=(txn,))), tmp_path / "x"
    ).run(product_id=84)
    assert "PRODUCT_LINKED_WALLET_ADJUSTMENTS_REQUIRE_REVIEW" not in report["hold_reasons"]
    assert "UNSCOPED_WALLET_ADJUSTMENTS_AMBIGUOUS" not in report["hold_reasons"]


def test_liquidation_fill_is_counted_but_never_silently_certified(tmp_path):
    fill = {"id": 201, "order_id": 9, "product_id": 84, "side": "sell",
            "size": "1", "price": "100", "fill_type": "liquidation"}
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(fills=(fill,), positions=({"size": "-1", "query_product_id": 84},))),
        tmp_path / "x",
    ).run(product_id=84)
    assert report["position_fill_reconciliation"]["matches"] is True
    assert "NON_NORMAL_OR_UNCLASSIFIED_FILLS_REQUIRE_REVIEW" in report["hold_reasons"]
    assert report["decision"] == "HOLD"


def test_fill_without_type_is_unclassified_and_holds(tmp_path):
    fill = {"id": 202, "order_id": 10, "product_id": 84, "side": "buy",
            "size": "1", "price": "100"}
    report = TestnetReconciliationCoordinator(
        FakeExchange(snap(fills=(fill,), positions=({"size": "1", "query_product_id": 84},))),
        tmp_path / "x",
    ).run(product_id=84)
    assert report["position_fill_reconciliation"]["matches"] is True
    assert report["fill_type_review"][0]["reason"] == "FILL_TYPE_MISSING"
    assert report["decision"] == "HOLD"
