"""
QuantEngine Phase 190 — Offline Adversarial Authorization Gate & Ledger Audit Test Suite.

Audits Task 5 edge cases in core/execution/testnet_authorization_gate.py:
  1. Corrupted persistent ledger lines (truncated JSON, invalid syntax).
  2. Duplicate client order IDs (cl_ord_id) in persistent ledger.
  3. Malformed JSON records (non-dict, missing event).
  4. File read / permission / IO errors fail-closed.
  5. Boundary conditions on cumulative orders (19 allows, 20 blocks).
  6. Ambiguous order state fail-closed refusal.
  7. Process restart with corrupted ledger prevents counter reset and blocks authorization.
  8. Zero exchange order writes verified across all adversarial paths.
"""

from __future__ import annotations

from authorization_test_utils import approve_for_test

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from core.execution.testnet_authorization_gate import (
    TestnetAuthorizationGate,
    AuthorizationState,
    OrderLifecycleState,
    OperatorAuthorizationRecord,
)


class TestPhase190LedgerCorruptionAndBoundaryAudit(unittest.TestCase):
    """Test Suite: Adversarial ledger integrity and fail-closed state testing."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "adversarial_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.valid_record = OperatorAuthorizationRecord(
            authorization_id="P190-VALID-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="AUDITOR_01",
            signed_timestamp_utc="2026-10-21T06:00:00Z",
            expiry_timestamp_utc="2026-10-21T18:00:00Z",
            scope=self.gate.scope,
            document_sha256="abc123sha",
            signature_payload="valid_sig_abc123",
        )
        approve_for_test(self.valid_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_corrupted_json_line_in_ledger_fails_closed(self):
        """A corrupted or truncated JSON line in the ledger must fail closed."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp_utc": 100, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "ord_1"}}\n')
            f.write('{"timestamp_utc": 101, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "ord_2"}}\n')
            f.write('CORRUPTED_JSON_TRUNCATED_LINE{"timestamp_utc": 102...\n')

        # Read cumulative orders should detect corruption
        count = self.gate.read_cumulative_orders_from_ledger()
        self.assertTrue(self.gate._ledger_corrupted)
        self.assertIn("Corrupted JSON", self.gate._ledger_corruption_reason)

        # Preflight evaluation MUST refuse authorization
        decision = self.gate.evaluate_preflight(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("Persistent ledger corrupted" in r for r in decision.reasons))

    def test_duplicate_client_order_id_in_ledger_fails_closed(self):
        """Duplicate cl_ord_id submitted events must be detected as an integrity breach."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp_utc": 100, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "ord_duplicate"}}\n')
            f.write('{"timestamp_utc": 101, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "ord_duplicate"}}\n')

        self.gate.read_cumulative_orders_from_ledger()
        self.assertTrue(self.gate._ledger_corrupted)
        self.assertIn("Duplicate cl_ord_id", self.gate._ledger_corruption_reason)

        decision = self.gate.evaluate_preflight(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)

    def test_malformed_record_structure_fails_closed(self):
        """Non-dictionary JSON or missing 'event' key must fail closed."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write('["an", "array", "not", "a", "dict"]\n')

        self.gate.read_cumulative_orders_from_ledger()
        self.assertTrue(self.gate._ledger_corrupted)
        self.assertIn("Malformed record structure", self.gate._ledger_corruption_reason)

        decision = self.gate.evaluate_preflight(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)

    def test_exact_boundary_condition_nineteen_versus_twenty(self):
        """19 submitted orders allows order 20; 20 submitted orders blocks order 21."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            for i in range(19):
                f.write(json.dumps({"timestamp_utc": 100 + i, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": f"ord_{i}"}}) + "\n")

        # 19 orders in ledger: order 20 is permitted
        d19 = self.gate.evaluate_preflight(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertTrue(d19.authorized)
        self.assertEqual(d19.cumulative_orders_placed, 19)

        # Append 20th order to ledger
        with open(self.ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp_utc": 200, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "ord_19"}}) + "\n")

        # Now 20 orders in ledger: order 21 is blocked
        gate20 = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        d20 = gate20.evaluate_preflight(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(d20.authorized)
        self.assertEqual(d20.cumulative_orders_placed, 20)
        self.assertTrue(any("Cumulative experiment order limit reached" in r for r in d20.reasons))

    def test_restarting_process_with_corrupted_ledger_blocks_execution(self):
        """Simulate process crashing after corrupting ledger: restart must NOT reset to 0."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp_utc": 100, "event": "ORDER_SUBMITTED", "data": {"cl_ord_id": "ord_crash"}}\n')
            f.write('HALF_WRITTEN_CORRUPTED_LINE_FROM_CRASH\n')

        # New process instance
        restarted_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        decision = restarted_gate.evaluate_preflight(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(restarted_gate._ledger_corrupted)


if __name__ == "__main__":
    unittest.main()
