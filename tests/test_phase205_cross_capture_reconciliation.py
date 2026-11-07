"""Tests for Phase 205 — Cross-Capture Historical Evidence Reconciliation.

Covers all 28 requirements of the Phase 205 test matrix:
1. Identical captures produce deterministic results.
2. Dictionary key ordering does not change canonical hashes.
3. Changed payload produces a changed-record classification.
4. Both versions of a changed record remain preserved.
5. A late-arriving record is detected.
6. A record absent from a later capture is not labelled deleted.
7. Duplicate identifiers with identical payloads are detected.
8. Duplicate identifiers with conflicting payloads are detected.
9. Incomplete capture prevents a complete-reconciliation claim.
10. Incomplete pagination prevents a complete-reconciliation claim.
11. Different venues are rejected or marked incompatible.
12. Different tenant/account scopes are not mixed.
13. Different products are not silently mixed.
14. Different record categories are not mixed.
15. Time-window boundaries are handled correctly.
16. Overlapping windows are compared correctly.
17. Non-overlapping windows are not misrepresented as equivalent.
18. Timestamp timezone handling is deterministic.
19. Financial decimal values are not silently rounded.
20. Null and optional fields are handled deterministically.
21. Unsupported serialization values fail safely.
22. Corrupt source checksums are detected.
23. Corrupt reconciliation outputs are detected.
24. Interrupted writes do not leave valid-looking partial evidence.
25. Rerunning identical inputs is deterministic and idempotent under project conventions.
26. Historical capture files remain byte-for-byte unchanged.
27. Existing Phase 204 snapshot adapter integrates cleanly.
28. Human-readable report formatting adheres to truthful taxonomy.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.execution.cross_capture_reconciliation import (
    AmbiguousRecord,
    CanonicalSerializationError,
    CaptureSnapshot,
    ChangedRecord,
    CorruptReconciliationResultError,
    CrossCaptureReconciliationError,
    CrossCaptureReconciliationResult,
    DuplicateRecord,
    FieldDiff,
    IncompatibleScopeError,
    LateArrivingRecord,
    NotObservedRecord,
    SourceChecksumMismatchError,
    _parse_utc,
    canonical_json_bytes,
    canonical_normalize,
    canonical_record_hash,
    compute_capture_checksum,
    compute_field_diffs,
    format_human_readable_report,
    load_reconciliation_result,
    persist_reconciliation_result,
    reconcile_captures_sequence,
    reconcile_reconciliation_snapshots,
    reconcile_two_captures,
    snapshot_to_captures,
)
from core.exchanges.delta.reconciliation_read_adapter import DeltaReconciliationSnapshot


# Common test fixtures
WINDOW_A_START = "2026-10-01T09:00:00Z"
WINDOW_A_END = "2026-10-01T10:00:00Z"
WINDOW_B_START = "2026-10-01T09:30:00Z"
WINDOW_B_END = "2026-10-01T10:30:00Z"


def _make_capture(
    capture_id: str,
    records: list[dict],
    *,
    venue: str = "delta",
    product_id: int = 84,
    account_id: str = "acct_test",
    record_category: str = "orders",
    captured_at: str = "2026-10-01T10:05:00Z",
    window_start: str = WINDOW_A_START,
    window_end: str = WINDOW_A_END,
    overlap_seconds: int = 60,
    complete: bool = True,
    pagination_complete: bool = True,
    raw_source_checksum: str | None = None,
) -> CaptureSnapshot:
    return CaptureSnapshot(
        capture_id=capture_id,
        venue=venue,
        record_category=record_category,
        product_id=product_id,
        account_id=account_id,
        records=tuple(copy.deepcopy(r) for r in records),
        captured_at=captured_at,
        window_start=window_start,
        window_end=window_end,
        overlap_seconds=overlap_seconds,
        complete=complete,
        pagination_complete=pagination_complete,
        raw_source_checksum=raw_source_checksum,
    )


# ---------------------------------------------------------------------------
# Test Matrix 1: Identical captures produce deterministic results
# ---------------------------------------------------------------------------

def test_identical_captures_produce_deterministic_results():
    records = [
        {"id": 1, "product_id": 84, "size": "1.5", "price": "100.0", "created_at": "2026-10-01T09:15:00Z"},
        {"id": 2, "product_id": 84, "size": "2.0", "price": "101.5", "created_at": "2026-10-01T09:30:00Z"},
    ]
    c1 = _make_capture("cap_1", records, captured_at="2026-10-01T10:01:00Z")
    c2 = _make_capture("cap_2", records, captured_at="2026-10-01T10:02:00Z")

    res1 = reconcile_two_captures(c1, c2, reconciliation_id="recon_fixed")
    res2 = reconcile_two_captures(c1, c2, reconciliation_id="recon_fixed")

    assert res1.status == "RECONCILED"
    assert len(res1.unchanged) == 2
    assert len(res1.changed) == 0
    assert len(res1.newly_observed) == 0
    assert len(res1.not_observed) == 0
    assert len(res1.late_arriving) == 0
    assert res1.content_identity == res2.content_identity
    assert res1.to_dict() == res2.to_dict()


# ---------------------------------------------------------------------------
# Test Matrix 2: Dictionary key ordering does not change canonical hashes
# ---------------------------------------------------------------------------

def test_dictionary_key_ordering_does_not_change_canonical_hashes():
    r1 = {"id": 101, "price": "50000.0", "size": "0.1", "side": "buy", "meta": {"a": 1, "b": 2}}
    r2 = {"meta": {"b": 2, "a": 1}, "side": "buy", "size": "0.1", "price": "50000.0", "id": 101}

    h1 = canonical_record_hash(r1)
    h2 = canonical_record_hash(r2)

    assert h1 == h2
    assert canonical_json_bytes(r1) == canonical_json_bytes(r2)


# ---------------------------------------------------------------------------
# Test Matrix 3: Changed payload produces a changed-record classification
# ---------------------------------------------------------------------------

def test_changed_payload_produces_changed_record_classification():
    r1 = [{"id": 1, "product_id": 84, "size": "1.0", "state": "open", "created_at": "2026-10-01T09:15:00Z"}]
    r2 = [{"id": 1, "product_id": 84, "size": "1.0", "state": "filled", "created_at": "2026-10-01T09:15:00Z"}]

    c1 = _make_capture("cap_1", r1, captured_at="2026-10-01T10:01:00Z")
    c2 = _make_capture("cap_2", r2, captured_at="2026-10-01T10:02:00Z")

    res = reconcile_two_captures(c1, c2)
    assert res.status == "RECONCILED_WITH_DIFFERENCES"
    assert len(res.changed) == 1
    assert len(res.unchanged) == 0
    changed = res.changed[0]
    assert changed.record_id == "1"
    assert changed.earlier_capture_id == "cap_1"
    assert changed.later_capture_id == "cap_2"
    assert any(d.field == "state" and d.earlier_value == "open" and d.later_value == "filled" for d in changed.differing_fields)


# ---------------------------------------------------------------------------
# Test Matrix 4: Both versions of a changed record remain preserved
# ---------------------------------------------------------------------------

def test_both_versions_of_changed_record_preserved():
    orig_payload = {"id": 10, "product_id": 84, "size": "5.0", "price": "100"}
    later_payload = {"id": 10, "product_id": 84, "size": "4.0", "price": "100"}

    c1 = _make_capture("cap_1", [orig_payload], captured_at="2026-10-01T10:01:00Z")
    c2 = _make_capture("cap_2", [later_payload], captured_at="2026-10-01T10:02:00Z")

    res = reconcile_two_captures(c1, c2)
    changed = res.changed[0]

    assert changed.earlier_payload["size"] == "5.0"
    assert changed.later_payload["size"] == "4.0"
    assert changed.earlier_content_hash == canonical_record_hash(orig_payload)
    assert changed.later_content_hash == canonical_record_hash(later_payload)


# ---------------------------------------------------------------------------
# Test Matrix 5: A late-arriving record is detected
# ---------------------------------------------------------------------------

def test_late_arriving_record_detected():
    # Capture 1 window: 09:00 - 10:00 (overlap 60s -> effective 08:59 - 10:01)
    # Record 99 was created at 09:30:00Z (squarely inside Capture 1's window),
    # but only observed in Capture 2.
    c1 = _make_capture("cap_1", [], captured_at="2026-10-01T10:01:00Z",
                       window_start="2026-10-01T09:00:00Z", window_end="2026-10-01T10:00:00Z")
    c2 = _make_capture("cap_2", [
        {"id": 99, "product_id": 84, "size": "1.0", "created_at": "2026-10-01T09:30:00Z"}
    ], captured_at="2026-10-01T11:00:00Z", window_start="2026-10-01T09:00:00Z", window_end="2026-10-01T11:00:00Z")

    res = reconcile_two_captures(c1, c2)
    assert len(res.late_arriving) == 1
    late = res.late_arriving[0]
    assert late.record_id == "99"
    assert late.first_observed_capture_id == "cap_2"
    assert late.earlier_capture_id == "cap_1"
    assert late.is_late_arrival is True
    assert late.event_timestamp == "2026-10-01T09:30:00+00:00"
    assert "earlier capture window" in late.explanation


# ---------------------------------------------------------------------------
# Test Matrix 6: A record absent from a later capture is NOT labelled deleted
# ---------------------------------------------------------------------------

def test_record_absent_from_later_capture_not_labelled_deleted():
    c1 = _make_capture("cap_1", [
        {"id": 5, "product_id": 84, "size": "1", "created_at": "2026-10-01T09:30:00Z"}
    ], captured_at="2026-10-01T10:01:00Z")
    c2 = _make_capture("cap_2", [], captured_at="2026-10-01T10:02:00Z")

    res = reconcile_two_captures(c1, c2)
    assert len(res.not_observed) == 1
    missing = res.not_observed[0]
    assert missing.record_id == "5"
    assert missing.classification == "NOT_OBSERVED_IN_LATER_CAPTURE"
    assert "deleted" not in missing.classification.lower()
    assert "cancelled" not in missing.classification.lower()
    assert "Absence is NOT proof of deletion or cancellation" in missing.reason


# ---------------------------------------------------------------------------
# Test Matrix 7: Duplicate identifiers with identical payloads detected
# ---------------------------------------------------------------------------

def test_duplicate_identifiers_with_identical_payloads_detected():
    records = [
        {"id": 1, "product_id": 84, "size": "1.0", "created_at": "2026-10-01T09:10:00Z"},
        {"id": 1, "product_id": 84, "size": "1.0", "created_at": "2026-10-01T09:10:00Z"},
    ]
    c1 = _make_capture("cap_1", records, captured_at="2026-10-01T10:01:00Z")
    c2 = _make_capture("cap_2", records, captured_at="2026-10-01T10:02:00Z")

    res = reconcile_two_captures(c1, c2)
    assert len(res.duplicates_identical) >= 1
    assert any(d.record_id == "1" and d.status == "DUPLICATE_IDENTICAL" for d in res.duplicates_identical)
    assert len(res.duplicates_conflicting) == 0


# ---------------------------------------------------------------------------
# Test Matrix 8: Duplicate identifiers with conflicting payloads detected
# ---------------------------------------------------------------------------

def test_duplicate_identifiers_with_conflicting_payloads_detected():
    records = [
        {"id": 1, "product_id": 84, "size": "1.0", "state": "open"},
        {"id": 1, "product_id": 84, "size": "2.0", "state": "closed"},
    ]
    c1 = _make_capture("cap_1", records, captured_at="2026-10-01T10:01:00Z")
    c2 = _make_capture("cap_2", [records[0]], captured_at="2026-10-01T10:02:00Z")

    res = reconcile_two_captures(c1, c2)
    assert len(res.duplicates_conflicting) == 1
    dup = res.duplicates_conflicting[0]
    assert dup.record_id == "1"
    assert dup.status == "DUPLICATE_CONFLICTING"
    assert any(d.field == "size" for d in dup.differing_fields)


# ---------------------------------------------------------------------------
# Test Matrix 9: Incomplete capture prevents a complete-reconciliation claim
# ---------------------------------------------------------------------------

def test_incomplete_capture_prevents_complete_reconciliation_claim():
    r = [{"id": 1, "product_id": 84, "size": "1.0"}]
    c1 = _make_capture("cap_1", r, complete=False)
    c2 = _make_capture("cap_2", r, complete=True)

    res = reconcile_two_captures(c1, c2)
    assert res.status == "PARTIAL"
    assert res.status != "RECONCILED"


# ---------------------------------------------------------------------------
# Test Matrix 10: Incomplete pagination prevents a complete-reconciliation claim
# ---------------------------------------------------------------------------

def test_incomplete_pagination_prevents_complete_reconciliation_claim():
    r = [{"id": 1, "product_id": 84, "size": "1.0"}]
    c1 = _make_capture("cap_1", r, pagination_complete=False)
    c2 = _make_capture("cap_2", r, pagination_complete=True)

    res = reconcile_two_captures(c1, c2)
    assert res.status == "PARTIAL"
    assert res.status != "RECONCILED"


# ---------------------------------------------------------------------------
# Test Matrix 11: Different venues are rejected or marked incompatible
# ---------------------------------------------------------------------------

def test_different_venues_rejected():
    c1 = _make_capture("cap_1", [], venue="delta")
    c2 = _make_capture("cap_2", [], venue="binance")

    with pytest.raises(IncompatibleScopeError, match="Venue mismatch"):
        reconcile_two_captures(c1, c2)


# ---------------------------------------------------------------------------
# Test Matrix 12: Different tenant/account scopes are not mixed
# ---------------------------------------------------------------------------

def test_different_tenant_account_scopes_rejected():
    c1 = _make_capture("cap_1", [], account_id="tenant_alpha")
    c2 = _make_capture("cap_2", [], account_id="tenant_beta")

    with pytest.raises(IncompatibleScopeError, match="Account scope mismatch"):
        reconcile_two_captures(c1, c2)


# ---------------------------------------------------------------------------
# Test Matrix 13: Different products are not silently mixed
# ---------------------------------------------------------------------------

def test_different_products_rejected():
    c1 = _make_capture("cap_1", [], product_id=84)
    c2 = _make_capture("cap_2", [], product_id=85)

    with pytest.raises(IncompatibleScopeError, match="Product scope mismatch"):
        reconcile_two_captures(c1, c2)


# ---------------------------------------------------------------------------
# Test Matrix 14: Different record categories are not mixed
# ---------------------------------------------------------------------------

def test_different_record_categories_rejected():
    c1 = _make_capture("cap_1", [], record_category="orders")
    c2 = _make_capture("cap_2", [], record_category="fills")

    with pytest.raises(IncompatibleScopeError, match="Record category mismatch"):
        reconcile_two_captures(c1, c2)


# ---------------------------------------------------------------------------
# Test Matrix 15: Time-window boundaries are handled correctly
# ---------------------------------------------------------------------------

def test_time_window_boundaries_handled_correctly():
    # Earlier capture: 09:00 - 10:00. Record 1 at 09:10:00Z.
    # Later capture: 10:30 - 11:30. Record 1 is outside Capture 2's window.
    c1 = _make_capture("cap_1", [
        {"id": 1, "product_id": 84, "created_at": "2026-10-01T09:10:00Z"}
    ], window_start="2026-10-01T09:00:00Z", window_end="2026-10-01T10:00:00Z", overlap_seconds=0)

    c2 = _make_capture("cap_2", [], window_start="2026-10-01T10:30:00Z",
                       window_end="2026-10-01T11:30:00Z", overlap_seconds=0)

    res = reconcile_two_captures(c1, c2)
    assert len(res.not_observed) == 1
    not_obs = res.not_observed[0]
    assert not_obs.classification == "OUTSIDE_CAPTURE_WINDOW"


# ---------------------------------------------------------------------------
# Test Matrix 16: Overlapping windows are compared correctly
# ---------------------------------------------------------------------------

def test_overlapping_windows_compared_correctly():
    # Window A: 09:00 - 10:00. Window B: 09:30 - 10:30. Overlap is 09:30 - 10:00.
    # Record 1 at 09:45 (in both)
    # Record 2 at 10:15 (new in B)
    r_overlap = {"id": 1, "product_id": 84, "size": "1.0", "created_at": "2026-10-01T09:45:00Z"}
    r_extended = {"id": 2, "product_id": 84, "size": "2.0", "created_at": "2026-10-01T10:15:00Z"}

    c1 = _make_capture("cap_1", [r_overlap], window_start=WINDOW_A_START, window_end=WINDOW_A_END)
    c2 = _make_capture("cap_2", [r_overlap, r_extended], window_start=WINDOW_B_START, window_end=WINDOW_B_END)

    res = reconcile_two_captures(c1, c2)
    assert res.integrity["windows_overlap"] is True
    assert len(res.unchanged) == 1
    assert len(res.newly_observed) == 1
    assert res.newly_observed[0]["id"] == 2
    assert res.status == "RECONCILED"


# ---------------------------------------------------------------------------
# Test Matrix 17: Non-overlapping windows are not misrepresented as equivalent
# ---------------------------------------------------------------------------

def test_non_overlapping_windows_not_misrepresented_as_equivalent():
    c1 = _make_capture("cap_1", [], window_start="2026-10-01T08:00:00Z", window_end="2026-10-01T09:00:00Z")
    c2 = _make_capture("cap_2", [], window_start="2026-10-01T10:00:00Z", window_end="2026-10-01T11:00:00Z")

    res = reconcile_two_captures(c1, c2)
    assert res.integrity["windows_overlap"] is False


# ---------------------------------------------------------------------------
# Test Matrix 18: Timestamp timezone handling is deterministic
# ---------------------------------------------------------------------------

def test_timestamp_timezone_handling_deterministic():
    # 09:00 UTC == 14:30 IST (+05:30) == 05:00 EDT (-04:00)
    ts1 = "2026-10-01T09:00:00Z"
    ts2 = "2026-10-01T14:30:00+05:30"
    ts3 = "2026-10-01T05:00:00-04:00"

    p1 = _parse_utc(ts1)
    p2 = _parse_utc(ts2)
    p3 = _parse_utc(ts3)

    assert p1 == p2 == p3
    assert p1.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Test Matrix 19: Financial decimal values are not silently rounded
# ---------------------------------------------------------------------------

def test_financial_decimal_values_not_silently_rounded():
    # Exact high-precision financial quantity: 18 decimal places
    d_exact = Decimal("100.123456789012345678")
    norm = canonical_normalize(d_exact)
    assert norm == "100.123456789012345678"

    # Distinct Decimals with trailing differences must produce distinct hashes
    d1 = Decimal("100.123456789012345678")
    d2 = Decimal("100.123456789012345679")
    h1 = canonical_record_hash({"amount": d1})
    h2 = canonical_record_hash({"amount": d2})
    assert h1 != h2


# ---------------------------------------------------------------------------
# Test Matrix 20: Null and optional fields are handled deterministically
# ---------------------------------------------------------------------------

def test_null_and_optional_fields_handled_deterministically():
    r1 = {"id": 1, "notes": None, "extra": "data"}
    r2 = {"id": 1, "extra": "data", "notes": None}

    h1 = canonical_record_hash(r1)
    h2 = canonical_record_hash(r2)
    assert h1 == h2


# ---------------------------------------------------------------------------
# Test Matrix 21: Unsupported serialization values fail safely
# ---------------------------------------------------------------------------

def test_unsupported_serialization_values_fail_safely():
    with pytest.raises(CanonicalSerializationError, match="Non-finite float"):
        canonical_normalize(float("nan"))

    with pytest.raises(CanonicalSerializationError, match="Non-finite float"):
        canonical_normalize(float("inf"))

    with pytest.raises(CanonicalSerializationError, match="Non-finite Decimal"):
        canonical_normalize(Decimal("NaN"))

    class CustomObject:
        pass

    with pytest.raises(CanonicalSerializationError, match="Unsupported data type"):
        canonical_normalize(CustomObject())


# ---------------------------------------------------------------------------
# Test Matrix 22: Corrupt source checksums are detected
# ---------------------------------------------------------------------------

def test_corrupt_source_checksums_detected():
    records = [{"id": 1, "product_id": 84, "size": "1"}]
    with pytest.raises(SourceChecksumMismatchError, match="raw_source_checksum mismatch"):
        _make_capture("cap_corrupt", records, raw_source_checksum="0" * 64)


# ---------------------------------------------------------------------------
# Test Matrix 23: Corrupt reconciliation outputs are detected
# ---------------------------------------------------------------------------

def test_corrupt_reconciliation_outputs_detected(tmp_path):
    c1 = _make_capture("cap_1", [{"id": 1, "product_id": 84}])
    c2 = _make_capture("cap_2", [{"id": 1, "product_id": 84}])
    res = reconcile_two_captures(c1, c2)

    target_file = tmp_path / "recon_test.json"
    persist_reconciliation_result(res, target_file)

    # Tamper with file
    data = json.loads(target_file.read_text(encoding="utf-8"))
    data["status"] = "TAMPERED_STATUS"
    target_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CorruptReconciliationResultError, match="Content identity mismatch"):
        load_reconciliation_result(target_file)


# ---------------------------------------------------------------------------
# Test Matrix 24: Interrupted writes do not leave valid-looking partial evidence
# ---------------------------------------------------------------------------

def test_interrupted_writes_do_not_leave_valid_looking_partial_evidence(tmp_path):
    target_file = tmp_path / "recon_interrupted.json"
    # Write partial corrupted JSON directly
    target_file.write_text('{"reconciliation_id": "incomplete', encoding="utf-8")

    with pytest.raises(CorruptReconciliationResultError, match="Malformed"):
        load_reconciliation_result(target_file)


# ---------------------------------------------------------------------------
# Test Matrix 25: Rerunning identical inputs is deterministic and idempotent
# ---------------------------------------------------------------------------

def test_rerunning_identical_inputs_deterministic_and_idempotent():
    records = [
        {"id": 1, "price": "100", "size": "2", "created_at": "2026-10-01T09:15:00Z"},
        {"id": 2, "price": "105", "size": "3", "created_at": "2026-10-01T09:20:00Z"},
    ]
    c1 = _make_capture("cap_1", records, captured_at="2026-10-01T10:00:00Z")
    c2 = _make_capture("cap_2", records, captured_at="2026-10-01T10:05:00Z")

    run1 = reconcile_two_captures(c1, c2, reconciliation_id="recon_stable")
    run2 = reconcile_two_captures(c1, c2, reconciliation_id="recon_stable")

    assert run1.content_identity == run2.content_identity
    assert canonical_json_bytes(run1.to_dict()) == canonical_json_bytes(run2.to_dict())


# ---------------------------------------------------------------------------
# Test Matrix 26: Historical capture files remain byte-for-byte unchanged
# ---------------------------------------------------------------------------

def test_historical_capture_files_remain_byte_for_byte_unchanged(tmp_path):
    capture_data = {
        "capture_id": "cap_frozen",
        "venue": "delta",
        "record_category": "orders",
        "records": [{"id": 1, "size": "1.0"}],
        "captured_at": "2026-10-01T10:00:00Z",
    }
    cap_path = tmp_path / "raw_capture.json"
    cap_path.write_text(json.dumps(capture_data), encoding="utf-8")

    hash_before = hashlib.sha256(cap_path.read_bytes()).hexdigest()

    # Load and run reconciliation
    loaded = CaptureSnapshot.from_dict(json.loads(cap_path.read_text(encoding="utf-8")))
    _ = reconcile_two_captures(loaded, loaded)

    hash_after = hashlib.sha256(cap_path.read_bytes()).hexdigest()
    assert hash_before == hash_after


# ---------------------------------------------------------------------------
# Test Matrix 27: Existing Phase 204 snapshot adapter integrates cleanly
# ---------------------------------------------------------------------------

def test_existing_phase204_snapshot_adapter_integrates():
    snap1 = DeltaReconciliationSnapshot(
        captured_at="2026-10-01T10:00:00Z",
        product_id=84,
        open_orders=({"id": 1, "product_id": 84, "size": "1", "created_at": "2026-10-01T09:10:00Z"},),
        order_history=(),
        fills=({"id": 10, "order_id": 1, "product_id": 84, "size": "1", "price": "100", "side": "buy"},),
        positions=({"product_id": 84, "size": "1"},),
        wallet_transactions=({"id": 100, "amount": "0.5", "transaction_type": "deposit", "created_at": "2026-10-01T09:00:00Z"},),
        complete=True,
        endpoint_status={"open_orders": "OK", "order_history": "OK", "fills": "OK", "positions": "OK", "wallet_transactions": "OK"},
        window_start=WINDOW_A_START,
        window_end=WINDOW_A_END,
        overlap_seconds=60,
    )

    # Call the decomposition function
    caps = snapshot_to_captures(snap1, venue="delta", account_id="acct_1")
    assert "orders" in caps
    assert "fills" in caps
    assert "positions" in caps
    assert "wallet_transactions" in caps

    # Compare against identical snapshot
    recon_results = reconcile_reconciliation_snapshots(snap1, snap1)
    assert recon_results["orders"].status == "RECONCILED"
    assert recon_results["fills"].status == "RECONCILED"
    assert recon_results["positions"].status == "RECONCILED"
    assert recon_results["wallet_transactions"].status == "RECONCILED"


# ---------------------------------------------------------------------------
# Test Matrix 28: Human-readable report contains truthful sections
# ---------------------------------------------------------------------------

def test_human_readable_report_contains_truthful_sections():
    c1 = _make_capture("cap_1", [{"id": 1, "size": "1.0"}])
    c2 = _make_capture("cap_2", [{"id": 1, "size": "1.0"}])
    res = reconcile_two_captures(c1, c2)

    report_text = format_human_readable_report(res)
    assert "Cross-Capture Historical Evidence Reconciliation Report" in report_text
    assert "Absence from a later capture is not proof of deletion" in report_text
    assert "RECONCILED" in report_text
    assert "Provenance" in report_text
    assert "Input Captures" in report_text
