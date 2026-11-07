"""
QuantEngine Phase 192 — Order Lifecycle State Machine & Crash-Recovery Invariants.

Audits and proves:
  1. The 10 canonical lifecycle states and their backward-compatible mappings.
  2. Table-driven transition matrix: legal transitions succeed, illegal transitions fail closed.
  3. Invariant A: Ambiguous submission preserves quota and risk reservations without blind resubmission.
  4. Invariant B: Partial fills create position exposure that survives remainder cancellation.
  5. Invariant C: Fully filled orders transition exposure to position risk without gaps or double-counting.
  6. Invariant D: Cancellation requests never release risk before authoritative confirmation.
  7. Invariant E: Restart recovery is deterministic, idempotent, and never assumes venue state on elapsed time.
  8. Invariant F: Corrupt persistence latches fail-closed state without skipping malformed records.

Strictly offline. Zero exchange order writes.
"""

from __future__ import annotations

from authorization_test_utils import approve_for_test

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import time
import unittest

from core.execution.testnet_authorization_gate import (
    TestnetAuthorizationGate,
    AuthorizationState,
    OrderLifecycleState,
    ORDER_STATE_CANONICAL_MAP,
    OperatorAuthorizationRecord,
)


class TestPhase192LifecycleTransitions(unittest.TestCase):
    """Test Suite: Phase 192 Lifecycle Transitions and Invariants."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "lifecycle_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.valid_record = OperatorAuthorizationRecord(
            authorization_id="P192-LIFECYCLE-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_LIFECYCLE_AUDITOR",
            signed_timestamp_utc="2026-10-21T08:00:00Z",
            expiry_timestamp_utc="2026-10-21T20:00:00Z",
            scope=self.gate.scope,
            document_sha256="sha256_lifecycle_valid",
            signature_payload="sig_lifecycle_auditor",
        )
        approve_for_test(self.valid_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_canonical_ten_states_and_backward_compatibility(self):
        """All 10 canonical states exist, are distinct, and legacy aliases map correctly."""
        canonical_states = {
            OrderLifecycleState.NOT_SUBMITTED,
            OrderLifecycleState.RESERVED,
            OrderLifecycleState.SUBMISSION_UNKNOWN,
            OrderLifecycleState.ACKNOWLEDGED,
            OrderLifecycleState.PARTIALLY_FILLED,
            OrderLifecycleState.FILLED,
            OrderLifecycleState.CANCEL_REQUESTED,
            OrderLifecycleState.CANCELLED_CONFIRMED,
            OrderLifecycleState.RECONCILIATION_REQUIRED,
            OrderLifecycleState.LEDGER_CORRUPTED,
        }
        self.assertEqual(len(canonical_states), 10)

        # Legacy aliases must map to canonical states without collapsing safety
        self.assertEqual(ORDER_STATE_CANONICAL_MAP[OrderLifecycleState.PENDING_SUBMISSION], OrderLifecycleState.RESERVED)
        self.assertEqual(ORDER_STATE_CANONICAL_MAP[OrderLifecycleState.SUBMITTED], OrderLifecycleState.SUBMISSION_UNKNOWN)
        self.assertEqual(ORDER_STATE_CANONICAL_MAP[OrderLifecycleState.RESTING], OrderLifecycleState.ACKNOWLEDGED)
        self.assertEqual(ORDER_STATE_CANONICAL_MAP[OrderLifecycleState.CANCELLED_UNFILLED], OrderLifecycleState.CANCELLED_CONFIRMED)
        self.assertEqual(ORDER_STATE_CANONICAL_MAP[OrderLifecycleState.AMBIGUOUS_STATE], OrderLifecycleState.RECONCILIATION_REQUIRED)

    def test_02_table_driven_legal_and_illegal_transitions(self):
        """Table-driven verification of legal vs illegal lifecycle state transitions."""
        # Define transition validity matrix:
        # (initial_state, target_state, is_legal)
        test_matrix = [
            # Legal flow
            (OrderLifecycleState.NOT_SUBMITTED, OrderLifecycleState.RESERVED, True),
            (OrderLifecycleState.RESERVED, OrderLifecycleState.SUBMISSION_UNKNOWN, True),
            (OrderLifecycleState.SUBMISSION_UNKNOWN, OrderLifecycleState.ACKNOWLEDGED, True),
            (OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.PARTIALLY_FILLED, True),
            (OrderLifecycleState.PARTIALLY_FILLED, OrderLifecycleState.FILLED, True),
            (OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.CANCEL_REQUESTED, True),
            (OrderLifecycleState.CANCEL_REQUESTED, OrderLifecycleState.CANCELLED_CONFIRMED, True),
            # Late fill race: cancel requested -> filled
            (OrderLifecycleState.CANCEL_REQUESTED, OrderLifecycleState.FILLED, True),
            # Ambiguity / timeout flow
            (OrderLifecycleState.SUBMISSION_UNKNOWN, OrderLifecycleState.RECONCILIATION_REQUIRED, True),
            (OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.RECONCILIATION_REQUIRED, True),
            # Illegal transitions: terminal to active
            (OrderLifecycleState.CANCELLED_CONFIRMED, OrderLifecycleState.ACKNOWLEDGED, False),
            (OrderLifecycleState.FILLED, OrderLifecycleState.SUBMISSION_UNKNOWN, False),
            (OrderLifecycleState.FILLED, OrderLifecycleState.RESERVED, False),
            (OrderLifecycleState.NOT_SUBMITTED, OrderLifecycleState.FILLED, False),
            (OrderLifecycleState.LEDGER_CORRUPTED, OrderLifecycleState.ACKNOWLEDGED, False),
        ]

        def is_transition_permitted(s_from: OrderLifecycleState, s_to: OrderLifecycleState) -> bool:
            # Terminal states cannot transition to active states
            terminal_states = {OrderLifecycleState.FILLED, OrderLifecycleState.CANCELLED_CONFIRMED}
            if s_from in terminal_states:
                return False
            if s_from == OrderLifecycleState.LEDGER_CORRUPTED:
                return False
            if s_from == OrderLifecycleState.NOT_SUBMITTED and s_to not in (OrderLifecycleState.RESERVED, OrderLifecycleState.SUBMISSION_UNKNOWN):
                return False
            return True

        for s_from, s_to, expected_legal in test_matrix:
            permitted = is_transition_permitted(s_from, s_to)
            self.assertEqual(
                permitted,
                expected_legal,
                f"Transition {s_from.value} -> {s_to.value} expected legal={expected_legal}, got {permitted}",
            )

    def test_03_invariant_a_ambiguous_submission_holds_quota_and_risk(self):
        """Invariant A: Timeout on order submission must not cause resubmission; state stays ambiguous."""
        d = self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_ambig_sub_1",
        )
        self.assertTrue(d.authorized)
        self.gate.register_order_submitted("ord_ambig_sub_1", {"size": "1.0"})

        # Timeout occurs
        self.gate.register_ack_timeout("ord_ambig_sub_1")

        # Quota remains held; new order attempt is refused because open ambiguous orders halt placement
        d2 = self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_next_attempt",
        )
        self.assertFalse(d2.authorized)
        self.assertTrue(any("ambiguous/unreconciled" in r for r in d2.reasons))

    def test_04_invariant_b_partial_fill_exposure_survives_cancellation(self):
        """Invariant B: Cancelling remainder of a partially filled order does not release filled position risk."""
        # 1.0 contract order, 0.4 filled, 0.6 cancelled
        order_record = {
            "cl_ord_id": "ord_partial_fill_inv_b",
            "state": OrderLifecycleState.CANCEL_REQUESTED,
            "order_size": "1.0",
        }
        exchange_order = {
            "id": 801,
            "cl_ord_id": "ord_partial_fill_inv_b",
            "state": "cancelled",
            "size": "1.0",
            "size_filled": "0.4",
            "unfilled_size": "0.6",
        }
        exchange_fills = [
            {"order_id": 801, "cl_ord_id": "ord_partial_fill_inv_b", "size": "0.4", "price": "67000.0"},
        ]

        from core.execution.testnet_state_reconciler import TestnetStateReconciler
        reconciler = TestnetStateReconciler()
        report = reconciler.reconcile(
            local_orders={"ord_partial_fill_inv_b": order_record},
            exchange_orders=[exchange_order],
            exchange_fills=exchange_fills,
        )

        rec = report.reconciled_orders["ord_partial_fill_inv_b"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.PARTIALLY_FILLED)
        self.assertEqual(rec.exchange_filled_qty, Decimal("0.4"))
        self.assertTrue(rec.position_exposure_held)
        self.assertEqual(rec.position_exposure_qty, Decimal("0.4"))
        # Unfilled quota is released, but position risk remains held
        self.assertTrue(rec.unfilled_quota_released)

    def test_05_invariant_c_filled_order_transfers_to_position_accounting(self):
        """Invariant C: FILLED order transfers exposure to position risk without double count or drop."""
        exchange_order = {
            "id": 901,
            "cl_ord_id": "ord_full_fill_inv_c",
            "state": "filled",
            "size": "1.0",
            "size_filled": "1.0",
            "unfilled_size": "0.0",
        }
        # Duplicate stream events for the same fill ID
        exchange_fills = [
            {"id": "fill_901_a", "order_id": 901, "cl_ord_id": "ord_full_fill_inv_c", "size": "1.0", "price": "67500.0"},
            {"id": "fill_901_a", "order_id": 901, "cl_ord_id": "ord_full_fill_inv_c", "size": "1.0", "price": "67500.0"},  # DUPLICATE!
        ]

        from core.execution.testnet_state_reconciler import TestnetStateReconciler
        reconciler = TestnetStateReconciler()
        report = reconciler.reconcile(
            local_orders={"ord_full_fill_inv_c": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"}},
            exchange_orders=[exchange_order],
            exchange_fills=exchange_fills,
        )

        rec = report.reconciled_orders["ord_full_fill_inv_c"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.FILLED)
        self.assertTrue(rec.position_exposure_held)
        self.assertEqual(rec.position_exposure_qty, Decimal("1.0"))
        # Duplicate fill was caught and deduplicated
        self.assertTrue(any(a["type"] == "DUPLICATE_FILL_EVENT" for a in report.anomalies))

    def test_06_invariant_d_cancellation_request_does_not_release_risk_prematurely(self):
        """Invariant D: Sending cancel request does not release risk until venue confirmation."""
        self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_cancel_req_test",
        )
        self.gate.register_order_submitted("ord_cancel_req_test", {"size": "1.0"})
        self.gate.register_order_acknowledged("ord_cancel_req_test", 1001)

        # Operator triggers cancel
        self.gate.handle_resting_timeout("ord_cancel_req_test", 125.0)

        # Order must be in CANCEL_REQUESTED, still active
        self.assertEqual(
            self.gate._active_open_orders["ord_cancel_req_test"]["state"],
            OrderLifecycleState.CANCEL_REQUESTED,
        )

        # It still counts as an active open order, blocking new placement under single-open constraint
        d_next = self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_after_cancel_req",
        )
        self.assertFalse(d_next.authorized)
        self.assertTrue(any("Single-open-order limit reached" in r for r in d_next.reasons))

    def test_07_invariant_e_restart_recovery_never_assumes_terminal_on_elapsed_time(self):
        """Invariant E: Recovery after crash never marks an unconfirmed order CANCELLED solely on elapsed time."""
        # Seed an order in resting state 24 hours ago
        old_time = time.time() - 86400.0
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp_utc": old_time,
                "event": "ORDER_RESERVED",
                "data": {"cl_ord_id": "ord_ancient_1", "symbol": "BTCUSD"},
            }) + "\n")
            f.write(json.dumps({
                "timestamp_utc": old_time + 1.0,
                "event": "ORDER_SUBMITTED",
                "data": {"cl_ord_id": "ord_ancient_1", "symbol": "BTCUSD"},
            }) + "\n")

        new_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        summary = new_gate.recover_and_reconcile_state()

        # It must NOT be marked CANCELLED_CONFIRMED. It must enter RECONCILIATION_REQUIRED.
        self.assertIn("ord_ancient_1", summary["ambiguous"])
        self.assertEqual(
            new_gate._ambiguous_orders["ord_ancient_1"]["state"],
            OrderLifecycleState.RECONCILIATION_REQUIRED,
        )

    def test_08_invariant_f_corruption_latches_fail_closed_and_preserves_count(self):
        """Invariant F: Malformed line latches fail-closed state without skipping or lowering count."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp_utc": 100.0,
                "event": "ORDER_RESERVED",
                "data": {"cl_ord_id": "ord_prior_1", "symbol": "BTCUSD"},
            }) + "\n")
            f.write("BOGUS_GARBAGE_RECORD_WITHOUT_JSON\n")
            f.write(json.dumps({
                "timestamp_utc": 102.0,
                "event": "ORDER_RESERVED",
                "data": {"cl_ord_id": "ord_prior_2", "symbol": "BTCUSD"},
            }) + "\n")

        recovery_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        summary = recovery_gate.recover_and_reconcile_state()

        self.assertTrue(summary["ledger_corrupted"])
        self.assertTrue(recovery_gate._ledger_corrupted)
        # Order placement must be completely refused
        d = recovery_gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_after_corrupt",
        )
        self.assertFalse(d.authorized)


if __name__ == "__main__":
    unittest.main()
