"""
QuantEngine Phase 192 — Adversarial Reconciliation & Boundary Stress Test Suite.

Audits and proves:
  1. Authoritatively absent order vs order missing from incomplete/paginated query.
  2. Unknown / rogue exchange order detected and permanently blocks execution.
  3. Submission timeout with potentially accepted order halts new submissions.
  4. Duplicate REST / private-stream fill events deduplicated without volume double-counting.
  5. Delayed acknowledgment: fill arriving before order acknowledgment.
  6. Partial fill followed by cancellation retains filled exposure and frees unfilled quota.
  7. Late fill arriving after cancellation request updates state cleanly to FILLED.
  8. Overfill anomaly (venue fill > local authorized quantity) detected and blocks execution.
  9. Contradictory order statuses and size mismatches trigger fail-closed BLOCKED state.
  10. Missing identifiers or product metadata handled safely.
  11. Network timeout, 503, or endpoint drop latches fail-closed BLOCKED state.
  12. Repeated reconciliation after restart is strictly idempotent and deterministic.
  13. Temporary disconnection and reconnect recovers state without dropping unconfirmed orders.

Strictly offline. Zero exchange order writes.
"""

from __future__ import annotations

from decimal import Decimal
import unittest

from core.execution.testnet_authorization_gate import OrderLifecycleState
from core.execution.testnet_state_reconciler import (
    TestnetStateReconciler,
    ReconciliationStatus,
    ReconciliationAnomalyType,
    redact_sensitive_data,
)


class TestPhase192ReconciliationAdversarial(unittest.TestCase):
    """Test Suite: Phase 192 Adversarial Reconciliation Stress Tests."""

    def setUp(self):
        self.reconciler = TestnetStateReconciler(reservation_grace_period_seconds=15.0)

    def test_01_authoritatively_absent_vs_incomplete_query_response(self):
        """Distingushes order missing in authoritative query vs missing in non-authoritative/paginated query."""
        local_orders = {
            "ord_missing": {"state": OrderLifecycleState.SUBMISSION_UNKNOWN, "order_size": "1.0", "timestamp_utc": 1000.0},
        }

        # Case A: Authoritative query returned empty list -> MISSING_FROM_EXCHANGE -> AMBIGUOUS
        rep_auth = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=[],
            query_is_authoritative=True,
        )
        self.assertEqual(rep_auth.status, ReconciliationStatus.AMBIGUOUS)
        self.assertFalse(rep_auth.execution_permitted)
        self.assertEqual(
            rep_auth.reconciled_orders["ord_missing"].reconciled_state,
            OrderLifecycleState.RECONCILIATION_REQUIRED,
        )

        # Case B: Non-authoritative / partial query -> INCOMPLETE_QUERY_RESPONSE -> BLOCKED
        rep_non_auth = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=[],
            query_is_authoritative=False,
        )
        self.assertEqual(rep_non_auth.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(rep_non_auth.execution_permitted)
        self.assertTrue(any(a["type"] == "INCOMPLETE_QUERY_RESPONSE" for a in rep_non_auth.anomalies))

    def test_02_rogue_exchange_order_blocks_all_execution(self):
        """Order appearing on exchange not present in local ledger is flagged as rogue and blocks."""
        local_orders = {
            "ord_legit": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 101, "cl_ord_id": "ord_legit", "state": "open", "size": "1.0", "size_filled": "0.0"},
            {"id": 999, "cl_ord_id": "rogue_external_order", "state": "open", "size": "10.0", "size_filled": "0.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
        )
        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertTrue(any(a["type"] == "UNKNOWN_EXCHANGE_ORDER" for a in report.anomalies))

    def test_03_submission_timeout_halts_further_placement(self):
        """Unacknowledged order during timeout enters RECONCILIATION_REQUIRED and refuses risk release."""
        local_orders = {
            "ord_timed_out": {"state": OrderLifecycleState.SUBMISSION_UNKNOWN, "order_size": "1.0"},
        }
        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=[],  # Venue has not returned it yet
        )
        self.assertFalse(report.execution_permitted)
        rec = report.reconciled_orders["ord_timed_out"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.RECONCILIATION_REQUIRED)
        self.assertFalse(rec.risk_released)
        self.assertFalse(rec.unfilled_quota_released)

    def test_04_duplicate_fill_records_deduplicated_without_double_count(self):
        """Duplicate stream/REST fill events for the same trade do not double-count filled size."""
        local_orders = {
            "ord_fill_dup": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 201, "cl_ord_id": "ord_fill_dup", "state": "filled", "size": "1.0", "size_filled": "1.0"},
        ]
        # Three duplicate copies of the same execution trade
        exchange_fills = [
            {"id": "trade_xyz_001", "order_id": 201, "cl_ord_id": "ord_fill_dup", "size": "1.0", "price": "68000.0"},
            {"id": "trade_xyz_001", "order_id": 201, "cl_ord_id": "ord_fill_dup", "size": "1.0", "price": "68000.0"},
            {"id": "trade_xyz_001", "order_id": 201, "cl_ord_id": "ord_fill_dup", "size": "1.0", "price": "68000.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )
        self.assertTrue(any(a["type"] == "DUPLICATE_FILL_EVENT" for a in report.anomalies))
        rec = report.reconciled_orders["ord_fill_dup"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.FILLED)
        self.assertEqual(rec.position_exposure_qty, Decimal("1.0"))  # Not 3.0!

    def test_05_delayed_ack_fill_arrives_before_ack(self):
        """Fill arrives from stream while local state was still SUBMISSION_UNKNOWN."""
        local_orders = {
            "ord_fast_fill": {"state": OrderLifecycleState.SUBMISSION_UNKNOWN, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 301, "cl_ord_id": "ord_fast_fill", "state": "filled", "size": "1.0", "size_filled": "1.0"},
        ]
        exchange_fills = [
            {"id": "trade_301", "order_id": 301, "cl_ord_id": "ord_fast_fill", "size": "1.0", "price": "68100.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )
        rec = report.reconciled_orders["ord_fast_fill"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.FILLED)
        self.assertTrue(rec.position_exposure_held)
        self.assertEqual(rec.position_exposure_qty, Decimal("1.0"))

    def test_06_partial_fill_followed_by_cancellation(self):
        """Order partially filled (0.3 / 1.0) then cancelled: position exposure is 0.3, unfilled 0.7 freed."""
        local_orders = {
            "ord_part_cancel": {"state": OrderLifecycleState.CANCEL_REQUESTED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 401, "cl_ord_id": "ord_part_cancel", "state": "cancelled", "size": "1.0", "size_filled": "0.3", "unfilled_size": "0.7"},
        ]
        exchange_fills = [
            {"id": "fill_part_1", "order_id": 401, "cl_ord_id": "ord_part_cancel", "size": "0.3", "price": "68200.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )
        rec = report.reconciled_orders["ord_part_cancel"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.PARTIALLY_FILLED)
        self.assertEqual(rec.exchange_filled_qty, Decimal("0.3"))
        self.assertTrue(rec.position_exposure_held)
        self.assertEqual(rec.position_exposure_qty, Decimal("0.3"))
        self.assertTrue(rec.unfilled_quota_released)

    def test_07_late_fill_post_cancel_request(self):
        """Late fill arrives when local order was in CANCEL_REQUESTED."""
        local_orders = {
            "ord_late_fill_race": {"state": OrderLifecycleState.CANCEL_REQUESTED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 501, "cl_ord_id": "ord_late_fill_race", "state": "filled", "size": "1.0", "size_filled": "1.0"},
        ]
        exchange_fills = [
            {"id": "fill_late_1", "order_id": 501, "cl_ord_id": "ord_late_fill_race", "size": "1.0", "price": "68300.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )
        rec = report.reconciled_orders["ord_late_fill_race"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.FILLED)
        self.assertIn(ReconciliationAnomalyType.DELAYED_FILL_POST_CANCEL, rec.anomalies)
        self.assertTrue(rec.position_exposure_held)
        self.assertEqual(rec.position_exposure_qty, Decimal("1.0"))

    def test_08_overfill_anomaly_detected_and_blocks_execution(self):
        """Venue reports filled quantity greater than locally expected order size: overfill anomaly."""
        local_orders = {
            "ord_overfill": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 601, "cl_ord_id": "ord_overfill", "state": "filled", "size": "1.5", "size_filled": "1.5"},
        ]
        exchange_fills = [
            {"id": "fill_over_1", "order_id": 601, "cl_ord_id": "ord_overfill", "size": "1.5", "price": "68400.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )
        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertTrue(any(a["type"] == "OVERFILL_DETECTED" for a in report.anomalies))
        self.assertTrue(any("overfilled" in r.lower() for r in report.reasons))

    def test_09_contradictory_order_status_blocks_execution(self):
        """Contradiction between order size_filled and fills sum blocks execution."""
        local_orders = {
            "ord_contradictory_fills": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 701, "cl_ord_id": "ord_contradictory_fills", "state": "open", "size": "1.0", "size_filled": "0.5"},
        ]
        # Fills sum indicates 0.2, but order state indicates 0.5
        exchange_fills = [
            {"id": "fill_mismatch_1", "order_id": 701, "cl_ord_id": "ord_contradictory_fills", "size": "0.2", "price": "68500.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )
        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertTrue(any(a["type"] == "CONTRADICTORY_RECORD" for a in report.anomalies))

    def test_10_missing_identifiers_and_redaction(self):
        """Exchange record missing cl_ord_id is safely handled, and credentials are redacted."""
        local_orders = {
            "ord_tracked": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 801, "cl_ord_id": "", "state": "open", "size": "1.0", "api_key": "my_secret_key_12345678"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
        )
        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        raw_repr = str(report.anomalies)
        self.assertNotIn("my_secret_key_12345678", raw_repr)
        self.assertIn("[REDACTED_KEY]", raw_repr)

    def test_11_rest_timeout_or_error_fails_closed(self):
        """REST timeout or 503 error latches BLOCKED state immediately."""
        local_orders = {
            "ord_net_err": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        report = self.reconciler.reconcile(
            local_orders=local_orders,
            endpoint_error=ConnectionResetError("Connection reset by peer: cdn-ind.testnet.deltaex.org"),
        )
        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertEqual(
            report.reconciled_orders["ord_net_err"].reconciled_state,
            OrderLifecycleState.RECONCILIATION_REQUIRED,
        )

    def test_12_repeated_reconciliation_is_idempotent(self):
        """Reconciliation executed multiple times on the same inputs yields identical reports."""
        local_orders = {
            "ord_idemp_1": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
            "ord_idemp_2": {"state": OrderLifecycleState.FILLED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 901, "cl_ord_id": "ord_idemp_1", "state": "open", "size": "1.0", "size_filled": "0.0"},
            {"id": 902, "cl_ord_id": "ord_idemp_2", "state": "filled", "size": "1.0", "size_filled": "1.0"},
        ]
        exchange_fills = [
            {"id": "f_902", "order_id": 902, "cl_ord_id": "ord_idemp_2", "size": "1.0", "price": "68600.0"},
        ]

        r1 = self.reconciler.reconcile(local_orders=local_orders, exchange_orders=exchange_orders, exchange_fills=exchange_fills)
        r2 = self.reconciler.reconcile(local_orders=local_orders, exchange_orders=exchange_orders, exchange_fills=exchange_fills)

        self.assertEqual(r1.status, r2.status)
        self.assertEqual(r1.execution_permitted, r2.execution_permitted)
        self.assertEqual(len(r1.reconciled_orders), len(r2.reconciled_orders))
        self.assertEqual(len(r1.anomalies), len(r2.anomalies))

    def test_13_temporary_disconnection_and_recovery(self):
        """Sequence of disconnected reconciliation followed by reconnected reconciliation."""
        local_orders = {
            "ord_reconn": {"state": OrderLifecycleState.SUBMISSION_UNKNOWN, "order_size": "1.0"},
        }
        # Step 1: Disconnected -> BLOCKED
        r_step1 = self.reconciler.reconcile(
            local_orders=local_orders,
            endpoint_error=TimeoutError("Temporary disconnection"),
        )
        self.assertEqual(r_step1.status, ReconciliationStatus.BLOCKED)

        # Step 2: Reconnected -> order is found open on exchange -> ACKNOWLEDGED
        exchange_orders = [
            {"id": 999, "cl_ord_id": "ord_reconn", "state": "open", "size": "1.0", "size_filled": "0.0"},
        ]
        r_step2 = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
        )
        self.assertEqual(r_step2.status, ReconciliationStatus.CLEAN)
        self.assertTrue(r_step2.execution_permitted)
        self.assertEqual(r_step2.reconciled_orders["ord_reconn"].reconciled_state, OrderLifecycleState.ACKNOWLEDGED)


if __name__ == "__main__":
    unittest.main()
