"""
QuantEngine Phase 191 — Testnet State Reconciliation Design Test Suite.

Audits Task 5 requirements using offline synthetic fixtures:
  1. Clean bidirectional reconciliation when local and exchange records match.
  2. Missing order from exchange detected (MISSING_FROM_EXCHANGE).
  3. Unknown exchange orders detected (UNKNOWN_EXCHANGE_ORDER).
  4. Contradictory order records detected (CONTRADICTORY_RECORD).
  5. Delayed/late fills post-cancellation detected and tracked (DELAYED_FILL_POST_CANCEL).
  6. Partial fills correctly recognized and tracked (PARTIAL_FILL_DETECTED).
  7. Unavailable REST endpoint or private WS disconnect fails closed (ENDPOINT_UNAVAILABLE / BLOCKED).
  8. Risk is never released for unresolved orders.
  9. Strict redaction of credentials and secrets from all reports and traces.
  10. Execution permanently blocked when reconciliation is incomplete.

Zero exchange order writes across all reconciliation tests.
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


class TestPhase191ReconciliationDesign(unittest.TestCase):
    """Test Suite: Offline exchange/local-state reconciliation design verification."""

    def setUp(self):
        self.reconciler = TestnetStateReconciler(reservation_grace_period_seconds=10.0)

    def test_clean_reconciliation_permits_execution(self):
        """When local orders match exchange records cleanly, execution is permitted."""
        local_orders = {
            "ord_clean_1": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
            "ord_clean_2": {"state": OrderLifecycleState.FILLED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 101, "cl_ord_id": "ord_clean_1", "state": "open", "size": "1.0", "size_filled": "0.0", "unfilled_size": "1.0"},
            {"id": 102, "cl_ord_id": "ord_clean_2", "state": "filled", "size": "1.0", "size_filled": "1.0", "unfilled_size": "0.0"},
        ]
        exchange_fills = [
            {"order_id": 102, "cl_ord_id": "ord_clean_2", "size": "1.0", "price": "65000.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )

        self.assertEqual(report.status, ReconciliationStatus.CLEAN)
        self.assertTrue(report.execution_permitted)
        self.assertTrue(report.is_clean())
        self.assertEqual(len(report.anomalies), 0)

    def test_missing_order_from_exchange_detected_and_blocks_execution(self):
        """Dispatched local order missing from exchange order book blocks execution."""
        local_orders = {
            "ord_missing_on_venue": {
                "state": OrderLifecycleState.SUBMISSION_UNKNOWN,
                "order_size": "1.0",
                "timestamp_utc": 1000.0,
            }
        }
        exchange_orders = []  # Exchange returns empty list

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
        )

        self.assertEqual(report.status, ReconciliationStatus.AMBIGUOUS)
        self.assertFalse(report.execution_permitted)
        self.assertFalse(report.reconciled_orders["ord_missing_on_venue"].risk_released)
        self.assertTrue(any(a["type"] == ReconciliationAnomalyType.MISSING_FROM_EXCHANGE.value for a in report.anomalies))

    def test_unknown_exchange_order_detected_and_blocks_execution(self):
        """Unknown order present on exchange but absent in local ledger blocks execution."""
        local_orders = {
            "ord_local_known": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 201, "cl_ord_id": "ord_local_known", "state": "open", "size": "1.0", "size_filled": "0.0"},
            {"id": 202, "cl_ord_id": "ord_rogue_unknown", "state": "open", "size": "5.0", "size_filled": "0.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
        )

        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertTrue(any(a["type"] == ReconciliationAnomalyType.UNKNOWN_EXCHANGE_ORDER.value for a in report.anomalies))
        self.assertTrue(any("Unknown exchange order" in r for r in report.reasons))

    def test_contradictory_record_size_mismatch_blocks_execution(self):
        """Contradiction between local order size and exchange reported size blocks execution."""
        local_orders = {
            "ord_contradiction": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 301, "cl_ord_id": "ord_contradiction", "state": "open", "size": "2.0", "size_filled": "0.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
        )

        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertTrue(any(a["type"] == ReconciliationAnomalyType.CONTRADICTORY_RECORD.value for a in report.anomalies))

    def test_delayed_fill_post_cancellation_detected_and_tracked(self):
        """Fill arriving after local cancellation request is recognized and updates state to FILLED."""
        local_orders = {
            "ord_late_fill": {"state": OrderLifecycleState.CANCEL_REQUESTED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 401, "cl_ord_id": "ord_late_fill", "state": "filled", "size": "1.0", "size_filled": "1.0"},
        ]
        exchange_fills = [
            {"order_id": 401, "cl_ord_id": "ord_late_fill", "size": "1.0", "price": "66000.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )

        rec = report.reconciled_orders["ord_late_fill"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.FILLED)
        self.assertTrue(rec.risk_released)
        self.assertIn(ReconciliationAnomalyType.DELAYED_FILL_POST_CANCEL, rec.anomalies)

    def test_partial_fill_tracked_cleanly(self):
        """Partially filled order (0.4 / 1.0 contracts) is correctly tracked."""
        local_orders = {
            "ord_part_fill": {"state": OrderLifecycleState.ACKNOWLEDGED, "order_size": "1.0"},
        }
        exchange_orders = [
            {"id": 501, "cl_ord_id": "ord_part_fill", "state": "open", "size": "1.0", "size_filled": "0.4", "unfilled_size": "0.6"},
        ]
        exchange_fills = [
            {"order_id": 501, "cl_ord_id": "ord_part_fill", "size": "0.4", "price": "66500.0"},
        ]

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            exchange_orders=exchange_orders,
            exchange_fills=exchange_fills,
        )

        rec = report.reconciled_orders["ord_part_fill"]
        self.assertEqual(rec.reconciled_state, OrderLifecycleState.PARTIALLY_FILLED)
        self.assertEqual(rec.exchange_filled_qty, Decimal("0.4"))
        self.assertFalse(rec.risk_released)  # Remaining 0.6 still open

    def test_endpoint_unavailable_fails_closed_and_blocks_execution(self):
        """Network timeout or unavailable REST endpoint immediately blocks execution."""
        local_orders = {
            "ord_unreachable": {"state": OrderLifecycleState.SUBMISSION_UNKNOWN, "order_size": "1.0"},
        }

        report = self.reconciler.reconcile(
            local_orders=local_orders,
            endpoint_error=TimeoutError("REST connection timed out after 5000ms to https://cdn-ind.testnet.deltaex.org"),
        )

        self.assertEqual(report.status, ReconciliationStatus.BLOCKED)
        self.assertFalse(report.execution_permitted)
        self.assertFalse(report.reconciled_orders["ord_unreachable"].risk_released)
        self.assertEqual(
            report.reconciled_orders["ord_unreachable"].reconciled_state,
            OrderLifecycleState.RECONCILIATION_REQUIRED,
        )
        self.assertTrue(any("endpoint unavailable" in r.lower() for r in report.reasons))

    def test_credential_redaction_in_traces_and_anomalies(self):
        """Sensitive credentials (API keys, secrets, auth headers) must be sanitized."""
        raw_error = "Failed request with api_key='delta_key_abc123456789' and api_secret='sec_987654321_secret'"
        sanitized = redact_sensitive_data(raw_error)

        self.assertNotIn("delta_key_abc123456789", sanitized)
        self.assertNotIn("sec_987654321_secret", sanitized)
        self.assertIn("[REDACTED_KEY]", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)


if __name__ == "__main__":
    unittest.main()
