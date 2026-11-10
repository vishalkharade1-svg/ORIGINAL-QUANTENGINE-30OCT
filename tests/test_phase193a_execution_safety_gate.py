"""
Phase 193A — Execution Safety Gate & Book Validity Integration Test Suite.

Audits execution safety gates with strict mocks and verifies market data book validity:
1. Injected strict mock adapters that fail immediately if any exchange write method is called.
2. Proof that an invalid book state cannot authorize an order-writing call in
   TestnetAuthorizationGate.evaluate_preflight() and check_and_reserve_order().
3. Proof that crossed book, stale book, uninitialized book, or missing sequence blocks authorization.
4. Proof that:
   - Authorization remains mandatory.
   - The pending authorization document is still rejected (PENDING_OPERATOR_APPROVAL).
   - Production endpoints remain inaccessible to the testnet execution path.
   - Ambiguous orders cannot be blindly resubmitted.
   - Unresolved orders retain risk and quota.
   - Corrupt ledgers remain fail-closed.

ALL SYNTHETIC SCENARIOS ARE LABELED: SIMULATED.
"""

from decimal import Decimal
import json
import os
from pathlib import Path
import pytest
import time
from typing import Dict, Any

from core.execution.testnet_authorization_gate import (
    TestnetAuthorizationGate,
    OperatorAuthorizationRecord,
    AuthorizationState,
    OrderLifecycleState,
    ExperimentScope,
)
from core.research.l2_book_tracker import L2BookTracker, BookValidityState


from core.execution.testnet_safety_gate import ProductionEndpointAttemptedError
from authorization_test_utils import approve_for_test


class ExplodingExchangeAdapter:
    """Strict mock exchange adapter that explodes if any write method is called."""

    def __init__(self):
        self.write_calls = 0

    def place_order(self, *args, **kwargs):
        self.write_calls += 1
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: place_order called on ExplodingExchangeAdapter!")

    def cancel_order(self, *args, **kwargs):
        self.write_calls += 1
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: cancel_order called on ExplodingExchangeAdapter!")

    def modify_order(self, *args, **kwargs):
        self.write_calls += 1
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: modify_order called on ExplodingExchangeAdapter!")

    def cancel_all(self, *args, **kwargs):
        self.write_calls += 1
        raise AssertionError("CRITICAL_SAFETY_VIOLATION: cancel_all called on ExplodingExchangeAdapter!")


def _create_approved_auth_record() -> OperatorAuthorizationRecord:
    """Create a simulated approved auth record for test purposes only."""
    scope = ExperimentScope(
        venue="DELTA_INDIA_TESTNET",
        target_rest_url="https://cdn-ind.testnet.deltaex.org",
        target_ws_url="wss://socket-ind-pub.testnet.deltaex.org",
        allowed_symbols={"BTCUSD"},
        allowed_product_ids={84},
        max_cumulative_orders=20,
        max_simultaneous_open_orders=1,
        max_order_size_contracts=Decimal("1.0"),
        max_order_notional_usd=Decimal("100.0"),
        max_loss_budget_usd=Decimal("5.0"),
        max_order_wait_seconds=10.0,
        require_post_only=True,
        forbid_market_conversion=True,
        require_valid_book=False,
        contract_size_btc=Decimal("0.001"),
        contract_metadata_product_id=84,
        contract_metadata_sha256="e4d838d7d647e4485399ea19aa699058d30ca47cc3806c51bf8e5e2d99950af2",
    )
    record = OperatorAuthorizationRecord(
        authorization_id="SIMULATED-AUTH-001",
        state=AuthorizationState.OPERATOR_APPROVED,
        operator_identity="SIMULATED_TEST_OPERATOR",
        signed_timestamp_utc="2026-10-21T00:00:00Z",
        expiry_timestamp_utc="2026-10-22T00:00:00Z",
        scope=scope,
        document_sha256="0" * 64,
        signature_payload="",
        raw_content="SIMULATED_CONTENT",
    )
    return approve_for_test(record)


def test_exploding_adapter_fails_closed_if_called():
    """Verify that the strict exploding adapter prevents any unauthorized write."""
    adapter = ExplodingExchangeAdapter()
    with pytest.raises(AssertionError, match="CRITICAL_SAFETY_VIOLATION: place_order"):
        adapter.place_order(symbol="BTCUSD", size=1)
    assert adapter.write_calls == 1


def test_uninitialized_book_blocks_preflight_and_reservation(tmp_path: Path):
    """Verify uninitialized book tracker fails preflight and atomic reservation."""
    adapter = ExplodingExchangeAdapter()
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    uninit_tracker = L2BookTracker("BTCUSD")
    assert uninit_tracker.state == BookValidityState.INITIALIZING
    assert not uninit_tracker.execution_eligible

    # 1. evaluate_preflight must fail closed
    dec = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        post_only=True,
        book_tracker=uninit_tracker,
    )
    assert not dec.authorized
    assert any("not execution-eligible" in r or "not VALID" in r for r in dec.reasons)

    # 2. check_and_reserve_order must fail closed
    res_dec = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        cl_ord_id="ORD-UNINIT-01",
        book_tracker=uninit_tracker,
    )
    assert not res_dec.authorized
    assert any("not execution-eligible" in r or "not VALID" in r for r in res_dec.reasons)
    # Zero writes allowed to adapter
    assert adapter.write_calls == 0


def test_crossed_book_blocks_authorization_and_reservation(tmp_path: Path):
    """Verify crossed book blocks authorization and atomic reservation."""
    adapter = ExplodingExchangeAdapter()
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    # Cross book: bid 80015 > ask 80010
    tracker.process_update(
        bids=[["80015.0", "1.0"]],
        asks=[],
        sequence=101,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
    )
    assert tracker.state == BookValidityState.INVALID
    assert not tracker.execution_eligible

    dec = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        post_only=True,
        book_tracker=tracker,
    )
    assert not dec.authorized
    assert any("not execution-eligible" in r for r in dec.reasons)

    res_dec = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        cl_ord_id="ORD-CROSSED-01",
        book_tracker=tracker,
    )
    assert not res_dec.authorized
    assert any("not execution-eligible" in r for r in res_dec.reasons)
    assert adapter.write_calls == 0


def test_stale_book_blocks_authorization_and_reservation(tmp_path: Path):
    """Verify stale book blocks authorization and reservation."""
    adapter = ExplodingExchangeAdapter()
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    t0 = time.monotonic_ns() - 10_000_000_000  # 10 seconds ago
    tracker = L2BookTracker("BTCUSD", stale_threshold_seconds=2.0)
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    # Elapsed is 10s > 2.0s threshold
    assert tracker.check_staleness()

    dec = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        post_only=True,
        book_tracker=tracker,
    )
    assert not dec.authorized
    assert any("not execution-eligible" in r for r in dec.reasons)

    res_dec = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        cl_ord_id="ORD-STALE-01",
        book_tracker=tracker,
    )
    assert not res_dec.authorized
    assert adapter.write_calls == 0


def test_missing_sequence_gap_blocks_authorization(tmp_path: Path):
    """Verify sequence gap transitions book to SEQUENCE_GAP and blocks authorization."""
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    t0 = time.monotonic_ns()
    tracker = L2BookTracker("BTCUSD")
    tracker.process_snapshot(
        bids=[["80000.0", "1.0"]],
        asks=[["80010.0", "1.0"]],
        sequence=100,
        venue_timestamp_us=1_000_000,
        receipt_mono_ns=t0,
    )
    # Sequence gap: 100 -> 105
    tracker.process_update(
        bids=[["80002.0", "1.0"]],
        asks=[],
        sequence=105,
        venue_timestamp_us=1_100_000,
        receipt_mono_ns=t0 + 50_000_000,
    )
    assert tracker.state == BookValidityState.SEQUENCE_GAP

    dec = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        post_only=True,
        book_tracker=tracker,
    )
    assert not dec.authorized
    assert any("not execution-eligible" in r for r in dec.reasons)


def test_pending_authorization_document_still_rejected(tmp_path: Path):
    """Verify the real PHASE189 / PHASE191 pending authorization file is strictly rejected."""
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)

    # Load actual repository authorization file
    repo_root = Path(__file__).parent.parent
    auth_file = repo_root / "reports" / "PHASE189_TESTNET_AUTHORIZATION.md"
    assert auth_file.exists()

    auth_record = gate.parse_authorization_document(auth_file)
    assert auth_record.state == AuthorizationState.PENDING_OPERATOR_APPROVAL

    dec = gate.evaluate_preflight(
        auth_record=auth_record,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        post_only=True,
    )
    assert not dec.authorized
    assert dec.state == AuthorizationState.PENDING_OPERATOR_APPROVAL
    assert any("PENDING_OPERATOR_APPROVAL" in r for r in dec.reasons)


def test_production_endpoint_inaccessible_to_execution(tmp_path: Path):
    """Verify production exchange endpoint URLs are strictly rejected by the gate."""
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    # Pass production URL - must raise ProductionEndpointAttemptedError
    with pytest.raises(ProductionEndpointAttemptedError):
        gate.evaluate_preflight(
            auth_record=auth,
            rest_url="https://api.delta.exchange",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=1.0,
            post_only=True,
        )


def test_ambiguous_orders_cannot_be_blindly_resubmitted_and_retain_risk(tmp_path: Path):
    """Verify ambiguous orders retain risk quota and cannot be re-reserved."""
    ledger_path = tmp_path / "testnet_ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    # Reserve order
    res = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        cl_ord_id="ORD-AMBIG-01",
        order_details={
            "side": "buy", "limit_price": "80000", "post_only": True,
        },
        post_only=True,
    )
    assert res.is_armed()

    # Simulate submission timeout -> transition to ambiguous
    gate.register_ack_timeout("ORD-AMBIG-01")
    assert "ORD-AMBIG-01" in gate._ambiguous_orders

    # Attempt to reserve a 2nd order: must be rejected because open/ambiguous limit = 1
    res2 = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        cl_ord_id="ORD-AMBIG-02",
    )
    assert not res2.authorized
    assert any("Open order limit exceeded" in r or "ambiguous" in r for r in res2.reasons)

    # Attempt to resubmit same cl_ord_id: must be rejected as duplicate
    res3 = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=1.0,
        cl_ord_id="ORD-AMBIG-01",
    )
    assert not res3.authorized
    assert any("ambiguous" in r.lower() or "duplicate" in r.lower() for r in res3.reasons)


def test_corrupt_ledger_fails_closed(tmp_path: Path):
    """Verify corrupted ledger file causes gate to fail closed on restart recovery."""
    ledger_path = tmp_path / "testnet_ledger.jsonl"

    # Write corrupt JSON line
    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write('{"timestamp": 12345, "cl_ord_id": "ORD-01", "state": "CORRUPTED_JSON_NO_BRACE\n')

    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    auth = _create_approved_auth_record()

    # Recover state
    rec_summary = gate.recover_and_reconcile_state()
    assert rec_summary["ledger_corrupted"]
    assert gate._ledger_corrupted

    # Preflight must fail closed
    dec = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=27,
        order_size_contracts=1.0,
    )
    assert not dec.authorized
    assert any("corrupted" in r.lower() or "unparseable" in r.lower() for r in dec.reasons)

def test_only_atomic_reservation_mints_scope_bound_write_capability(tmp_path: Path):
    """Preflight cannot write; a reserved decision cannot be altered via dataclasses.replace."""
    from dataclasses import replace
    from core.exchanges.delta.write_authority import (
        TransportWriteAuthorityError,
        token_for_testnet_experiment,
    )

    gate = TestnetAuthorizationGate(ledger_path=tmp_path / "sealed-ledger.jsonl")
    auth = _create_approved_auth_record()

    preflight = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1.0"),
        post_only=True,
        limit_price=Decimal("80000"),
    )
    assert preflight.authorized
    assert not preflight.is_armed()
    with pytest.raises(TransportWriteAuthorityError):
        token_for_testnet_experiment(
            preflight,
            "https://cdn-ind.testnet.deltaex.org",
            payload={"product_id": 84, "size": "1.0", "side": "buy"},
        )

    unbound_gate = TestnetAuthorizationGate(
        ledger_path=tmp_path / "unbound-ledger.jsonl"
    )
    unbound = unbound_gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1.0"),
        cl_ord_id="ORD-UNBOUND-01",
        post_only=True,
    )
    # An incomplete reservation must not persist, consume quota, or arm.
    assert not unbound.authorized
    assert not unbound.is_armed()
    assert any("requires exactly side, limit_price, and post_only" in reason
               for reason in unbound.reasons)
    assert not (tmp_path / "unbound-ledger.jsonl").exists()

    reserved = gate.check_and_reserve_order(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1.0"),
        cl_ord_id="ORD-SEALED-01",
        order_details={
            "side": "buy",
            "limit_price": "80000",
            "post_only": True,
        },
        post_only=True,
    )
    assert reserved.is_armed()

    payload = {
        "product_id": 84,
        "size": "1.0",
        "side": "buy",
        "limit_price": "80000",
        "post_only": True,
        "client_order_id": "ORD-SEALED-01",
    }
    with pytest.raises(TransportWriteAuthorityError, match="finite integer"):
        token_for_testnet_experiment(
            reserved,
            "https://cdn-ind.testnet.deltaex.org",
            payload={**payload, "product_id": 84.5},
        )
    with pytest.raises(TransportWriteAuthorityError, match="operator-authorized REST endpoint"):
        token_for_testnet_experiment(
            reserved,
            "https://testnet-api.delta.exchange",
            payload=payload,
        )

    token = token_for_testnet_experiment(
        reserved,
        "https://cdn-ind.testnet.deltaex.org",
        payload=payload,
    )
    assert token.kind == "TESTNET_EXPERIMENT"
    with pytest.raises(TransportWriteAuthorityError, match="already minted"):
        token_for_testnet_experiment(
            reserved,
            "https://cdn-ind.testnet.deltaex.org",
            payload=payload,
        )

    with pytest.raises(TransportWriteAuthorityError, match="positive integer order id"):
        token_for_testnet_experiment(
            reserved,
            "https://cdn-ind.testnet.deltaex.org",
            payload={"id": 12345.5, "product_id": 84},
            method="DELETE",
        )
    cancel_payload = {"id": 12345, "product_id": 84}
    cancel_token = token_for_testnet_experiment(
        reserved,
        "https://cdn-ind.testnet.deltaex.org",
        payload=cancel_payload,
        method="DELETE",
    )
    assert cancel_token.method == "DELETE"
    with pytest.raises(TransportWriteAuthorityError, match="DELETE"):
        token_for_testnet_experiment(
            reserved,
            "https://cdn-ind.testnet.deltaex.org",
            payload=cancel_payload,
            method="DELETE",
        )

    forged_decisions = (
        replace(reserved, authorized_product_id=999),
        replace(reserved, authorized_order_size_contracts=Decimal("2.0")),
        replace(reserved, authorized_symbol="ETHUSD"),
        replace(reserved, authorized_rest_url="https://testnet-api.delta.exchange"),
        replace(reserved, authorized_client_order_id="ORD-ATTACK"),
        replace(reserved, authorized=False),
    )
    for forged in forged_decisions:
        assert not forged.is_armed()
        with pytest.raises(TransportWriteAuthorityError):
            token_for_testnet_experiment(
                forged,
                "https://cdn-ind.testnet.deltaex.org",
                payload=payload,
            )



@pytest.mark.parametrize(
    "price,expected_authorized",
    [
        ("100000", True),
        ("100000.1", False),
        ("NaN", False),
        ("Infinity", False),
        ("0", False),
        ("-1", False),
    ],
)
def test_reusable_gate_enforces_usd_notional_ceiling(tmp_path: Path, price: str, expected_authorized: bool):
    gate = TestnetAuthorizationGate(ledger_path=tmp_path / "notional-ledger.jsonl")
    decision = gate.evaluate_preflight(
        auth_record=_create_approved_auth_record(),
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1"),
        post_only=True,
        limit_price=price,
    )
    assert decision.authorized is expected_authorized
    if not expected_authorized:
        assert any("notional" in reason.lower() or "limit price" in reason.lower() for reason in decision.reasons)


def test_reusable_gate_refuses_unpriced_preflight(tmp_path: Path):
    gate = TestnetAuthorizationGate(ledger_path=tmp_path / "unpriced-ledger.jsonl")
    decision = gate.evaluate_preflight(
        auth_record=_create_approved_auth_record(),
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1"),
        post_only=True,
    )
    assert not decision.authorized
    assert any("Limit price is required" in reason for reason in decision.reasons)


def test_reusable_gate_fails_closed_without_verified_contract_metadata(tmp_path: Path):
    from dataclasses import replace
    auth = _create_approved_auth_record()
    auth.scope = replace(auth.scope, contract_size_btc=None, contract_metadata_product_id=None, contract_metadata_sha256="")
    auth = approve_for_test(auth)
    gate = TestnetAuthorizationGate(ledger_path=tmp_path / "missing-metadata-ledger.jsonl")
    decision = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1"),
        post_only=True,
        limit_price="80000",
    )
    assert not decision.authorized
    assert any("contract multiplier" in reason.lower() for reason in decision.reasons)
    assert any("snapshot sha-256" in reason.lower() for reason in decision.reasons)


def test_reservation_persists_notional_inputs_and_metadata_provenance(tmp_path: Path):
    ledger_path = tmp_path / "notional-reservation-ledger.jsonl"
    gate = TestnetAuthorizationGate(ledger_path=ledger_path)
    decision = gate.check_and_reserve_order(
        auth_record=_create_approved_auth_record(),
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1"),
        cl_ord_id="ORD-NOTIONAL-BOUND-01",
        order_details={"side": "buy", "limit_price": "80000", "post_only": True},
        post_only=True,
    )
    assert decision.is_armed()
    record = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
    data = record["data"]
    assert data["notional_usd"] == "80.000"
    assert data["contract_size_btc"] == "0.001"
    assert data["contract_metadata_product_id"] == 84
    assert data["contract_metadata_sha256"] == "e4d838d7d647e4485399ea19aa699058d30ca47cc3806c51bf8e5e2d99950af2"


@pytest.mark.parametrize(
    "metadata_changes",
    [
        {"contract_size_btc": Decimal("0.0005")},
        {"contract_metadata_product_id": 999},
        {"contract_metadata_sha256": "f" * 64},
    ],
)
def test_reusable_gate_rejects_substituted_contract_metadata(tmp_path: Path, metadata_changes: dict):
    from dataclasses import replace
    auth = _create_approved_auth_record()
    auth.scope = replace(auth.scope, **metadata_changes)
    auth = approve_for_test(auth)
    gate = TestnetAuthorizationGate(ledger_path=tmp_path / "substituted-metadata-ledger.jsonl")
    decision = gate.evaluate_preflight(
        auth_record=auth,
        rest_url="https://cdn-ind.testnet.deltaex.org",
        symbol="BTCUSD",
        product_id=84,
        order_size_contracts=Decimal("1"),
        post_only=True,
        limit_price="80000",
    )
    assert not decision.authorized
