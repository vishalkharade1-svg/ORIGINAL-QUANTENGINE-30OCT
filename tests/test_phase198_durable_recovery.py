import json
from pathlib import Path

import pytest

from core.execution.testnet_durable_recovery import (
    DurableRecoveryError,
    read_durable_order_journal,
    reconcile_ledger_file,
    reconcile_order_journal,
)


def write_ledger(path: Path, events):
    path.write_text("".join(json.dumps(x) + "\n" for x in events), encoding="utf-8")


def ev(name, data):
    return {"timestamp_utc": 1, "event": name, "data": data}


def base_events():
    return [
        ev("ORDER_RESERVED", {"cl_ord_id": "QE-A", "product_id": 84, "symbol": "BTCUSD", "order_size": "1", "side": "buy", "limit_price": "60000", "post_only": True}),
        ev("ORDER_SUBMITTED", {"cl_ord_id": "QE-A", "rest_path": "/v2/orders"}),
    ]


def test_recovers_acknowledged_id_and_scope_fields(tmp_path):
    p = tmp_path / "ledger.jsonl"
    events = base_events() + [ev("ORDER_RESTING", {"cl_ord_id": "QE-A", "exchange_order_id": 123})]
    write_ledger(p, events)
    row = read_durable_order_journal(p)["QE-A"]
    assert row["state"] == "ACKNOWLEDGED"
    assert row["exchange_order_id"] == "123"
    assert row["product_id"] == 84
    assert row["symbol"] == "BTCUSD"


def test_ambiguous_ack_matches_exact_client_id_and_open_order():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "SUBMISSION_UNKNOWN", "product_id": 84, "symbol": "BTCUSD", "size": "1", "side": "buy"}}
    result = reconcile_order_journal(journal, [{"id": 123, "client_order_id": "QE-A", "product_id": 84, "product_symbol": "BTCUSD", "size": "1", "side": "buy", "state": "open", "size_filled": "0"}], exchange_snapshot_complete=False)
    assert result["orders"][0]["status"] == "OPEN_CONFIRMED"
    assert result["orders"][0]["automatic_action"] == "NONE"
    assert result["safe_to_resume_submissions"] is False


def test_partial_fill_is_never_treated_as_terminal():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "ACKNOWLEDGED", "exchange_order_id": "123", "product_id": 84, "size": "2", "side": "buy"}}
    result = reconcile_order_journal(journal, [{"id": 123, "client_order_id": "QE-A", "product_id": 84, "size": "2", "side": "buy", "state": "open", "size_filled": "0.5"}], exchange_snapshot_complete=True)
    assert result["orders"][0]["status"] == "PARTIALLY_FILLED_OPEN"
    assert result["unresolved_count"] == 1


def test_identity_mismatch_fails_closed():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "SUBMISSION_UNKNOWN", "product_id": 84, "size": "1", "side": "buy"}}
    result = reconcile_order_journal(journal, [{"id": 123, "client_order_id": "QE-A", "product_id": 99, "size": "1", "side": "buy", "state": "open"}], exchange_snapshot_complete=True)
    assert result["orders"][0]["status"] == "CONFLICT_IDENTITY_MISMATCH"


def test_multiple_matches_fail_closed():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "SUBMISSION_UNKNOWN"}}
    rows = [{"id": 1, "client_order_id": "QE-A", "state": "open"}, {"id": 2, "client_order_id": "QE-A", "state": "open"}]
    result = reconcile_order_journal(journal, rows, exchange_snapshot_complete=False)
    assert result["orders"][0]["status"] == "CONFLICT_MULTIPLE_MATCHES"


def test_missing_order_in_snapshot_is_not_assumed_cancelled():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "ACKNOWLEDGED", "exchange_order_id": "123"}}
    result = reconcile_order_journal(journal, [], exchange_snapshot_complete=True)
    assert result["orders"][0]["status"] == "UNRESOLVED_ORDER_NOT_IN_SNAPSHOT"


def test_corrupt_ledger_rejected(tmp_path):
    p = tmp_path / "ledger.jsonl"
    p.write_text('{"event":"ORDER_RESERVED","data":{"cl_ord_id":"QE-A"}}\n{bad\n', encoding="utf-8")
    with pytest.raises(DurableRecoveryError):
        read_durable_order_journal(p)


def test_terminal_local_state_not_enough_without_exchange_evidence():
    result = reconcile_order_journal({"QE-A": {"client_order_id": "QE-A", "state": "CANCELLED_CONFIRMED"}}, [], exchange_snapshot_complete=False)
    assert result["orders"][0]["status"] == "LOCAL_TERMINAL_NEEDS_EXCHANGE_EVIDENCE"


def test_ledger_file_convenience_path(tmp_path):
    p = tmp_path / "ledger.jsonl"
    write_ledger(p, base_events())
    result = reconcile_ledger_file(p, [], exchange_snapshot_complete=False)
    assert result["orders_reviewed"] == 1
    assert result["orders"][0]["status"] == "UNRESOLVED_MANUAL_RECONCILIATION"


def test_matching_fill_evidence_detects_partial_fill():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "SUBMISSION_UNKNOWN", "product_id": 84, "size": "2", "side": "buy"}}
    result = reconcile_order_journal(
        journal,
        [{"id": 123, "client_order_id": "QE-A", "product_id": 84, "size": "2", "side": "buy", "state": "open", "size_filled": "0"}],
        exchange_snapshot_complete=True,
        exchange_fills=[{"order_id": 123, "client_order_id": "QE-A", "product_id": 84, "size": "0.25"}],
    )
    assert result["orders"][0]["status"] == "PARTIALLY_FILLED_OPEN"


def test_invalid_fill_evidence_blocks_reconciliation():
    journal = {"QE-A": {"client_order_id": "QE-A", "state": "ACKNOWLEDGED", "exchange_order_id": "123", "product_id": 84, "size": "2"}}
    result = reconcile_order_journal(
        journal,
        [{"id": 123, "client_order_id": "QE-A", "product_id": 84, "size": "2", "state": "open"}],
        exchange_snapshot_complete=True,
        exchange_fills=[{"order_id": 123, "client_order_id": "QE-A", "product_id": 84, "size": "NaN"}],
    )
    assert result["orders"][0]["status"] == "UNRESOLVED_INVALID_FILL_EVIDENCE"
