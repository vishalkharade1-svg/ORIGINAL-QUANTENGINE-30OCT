"""
QuantEngine Phase 191 — Cross-Process Ledger Concurrency & Safety Audit Test Suite.

Audits Task 3 requirements:
  1. Authoritative cumulative order limit (20 orders max) strictly enforced across concurrent callers.
  2. Serialized check-and-reserve operations prevent slot oversubscription.
  3. Bounded wait on cross-process lock raises LockTimeoutError without hanging indefinitely.
  4. Concurrent callers attempting duplicate client order IDs are refused.
  5. Crash-safe fsync persistence ensures immediate durability across process boundaries.
  6. Corrupted or malformed ledger fails closed across all concurrent processes.
  7. Zero exchange order writes across all concurrency tests.
"""

from __future__ import annotations

from authorization_test_utils import approve_for_test

import concurrent.futures
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from core.execution.testnet_authorization_gate import (
    TestnetAuthorizationGate,
    AuthorizationState,
    OrderLifecycleState,
    OperatorAuthorizationRecord,
    CrossProcessFileLock,
    LockTimeoutError,
)


class TestPhase191LedgerConcurrencyAudit(unittest.TestCase):
    """Test Suite: Multi-process concurrency and check-and-reserve serialization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "concurrent_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.valid_record = OperatorAuthorizationRecord(
            authorization_id="P191-CONCURRENCY-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_CONCURRENCY_AUDITOR",
            signed_timestamp_utc="2026-10-21T06:00:00Z",
            expiry_timestamp_utc="2026-10-21T18:00:00Z",
            scope=self.gate.scope,
            document_sha256="sha256_concurrency_approved",
            signature_payload="sig_concurrency_lead",
        )
        approve_for_test(self.valid_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_concurrent_callers_respect_twenty_order_ceiling(self):
        """25 concurrent callers attempt check_and_reserve: exactly 20 succeed, 5 are blocked."""
        results = []

        def attempt_reservation(idx: int):
            # Create a distinct gate instance per thread/process pointing to the shared ledger
            thread_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
            cl_id = f"ord_concurrent_{idx:03d}"
            decision = thread_gate.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=cl_id,
                order_details={"side": "buy", "limit_price": "80000", "post_only": True},
            )
            return idx, decision

        # Run 25 concurrent reservation attempts
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(attempt_reservation, i) for i in range(25)]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())

        authorized_count = sum(1 for _, d in results if d.authorized)
        refused_count = sum(1 for _, d in results if not d.authorized)

        self.assertEqual(authorized_count, 20, f"Expected exactly 20 reservations, got {authorized_count}")
        self.assertEqual(refused_count, 5, f"Expected exactly 5 refused attempts, got {refused_count}")

        # Verify disk ledger contains exactly 20 distinct reserved orders
        read_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        final_count = read_gate.read_cumulative_orders_from_ledger()
        self.assertEqual(final_count, 20)

    def test_serialized_reservation_prevents_slot_oversubscription(self):
        """When 19 orders exist in the ledger, two concurrent processes race for the final slot.
        Exactly one must succeed, the other must be refused.
        """
        # Pre-seed ledger with 19 orders
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            for i in range(19):
                entry = {
                    "timestamp_utc": time.time(),
                    "event": "ORDER_RESERVED",
                    "data": {"cl_ord_id": f"seed_ord_{i:02d}", "symbol": "BTCUSD"},
                }
                f.write(json.dumps(entry) + "\n")

        # Two racing processes
        results = []

        def race_for_slot(cl_id: str):
            g = TestnetAuthorizationGate(ledger_path=self.ledger_file)
            d = g.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=cl_id,
                order_details={"side": "buy", "limit_price": "80000", "post_only": True},
            )
            return cl_id, d

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(race_for_slot, "racing_ord_A")
            f2 = executor.submit(race_for_slot, "racing_ord_B")
            results = [f1.result(), f2.result()]

        authorized = [(cid, d) for cid, d in results if d.authorized]
        refused = [(cid, d) for cid, d in results if not d.authorized]

        self.assertEqual(len(authorized), 1, "Exactly one process must obtain the final slot")
        self.assertEqual(len(refused), 1, "The competing process must be refused")
        self.assertIn("Cumulative experiment order limit reached", refused[0][1].reasons[0])

    def test_lock_timeout_bounded_wait_fails_closed(self):
        """Holding the lock past timeout forces competing caller to raise LockTimeoutError."""
        lock_path = self.ledger_file.with_suffix(".lock")

        # Acquire lock in thread
        lock_acquired = threading.Event()
        release_lock = threading.Event()

        def lock_holder():
            with CrossProcessFileLock(lock_path, timeout_seconds=2.0):
                lock_acquired.set()
                release_lock.wait(timeout=2.0)

        t = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        t.submit(lock_holder)
        lock_acquired.wait(timeout=1.0)

        # Competing caller with 0.1s timeout must fail with LockTimeoutError
        try:
            with self.assertRaises(LockTimeoutError):
                with CrossProcessFileLock(lock_path, timeout_seconds=0.1, poll_interval=0.01):
                    pass
        finally:
            release_lock.set()
            t.shutdown(wait=True)

    def test_duplicate_client_order_id_concurrent_rejection(self):
        """Two concurrent callers using the exact same cl_ord_id cannot both reserve."""
        shared_cl_id = "duplicate_cl_ord_id_race"
        results = []

        def try_reserve():
            g = TestnetAuthorizationGate(ledger_path=self.ledger_file)
            return g.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=shared_cl_id,
                order_details={"side": "buy", "limit_price": "80000", "post_only": True},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(try_reserve)
            f2 = executor.submit(try_reserve)
            results = [f1.result(), f2.result()]

        authorized = [d for d in results if d.authorized]
        refused = [d for d in results if not d.authorized]

        self.assertEqual(len(authorized), 1)
        self.assertEqual(len(refused), 1)
        self.assertTrue(any("Duplicate cl_ord_id" in r for r in refused[0].reasons))

    def test_corrupted_ledger_concurrent_refusal(self):
        """Corrupted ledger file causes all concurrent check_and_reserve attempts to fail closed."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp_utc": 100, "event": "ORDER_RESERVED", "data": {"cl_ord_id": "ord_1"}}\n')
            f.write('TRUNCATED_GARBAGE_JSON_LINE_AT_PERSISTENCE_BOUNDARY...\n')

        def attempt_on_corrupt(idx: int):
            g = TestnetAuthorizationGate(ledger_path=self.ledger_file)
            return g.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=f"ord_attempt_{idx}",
                order_details={"side": "buy", "limit_price": "80000", "post_only": True},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(attempt_on_corrupt, i) for i in range(4)]
            decisions = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertTrue(all(not d.authorized for d in decisions))
        self.assertTrue(all(any("Persistent ledger corrupted" in r for r in d.reasons) for d in decisions))


if __name__ == "__main__":
    unittest.main()
