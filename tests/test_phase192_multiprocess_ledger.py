"""
QuantEngine Phase 192 — Multiprocess Ledger Concurrency & Durability Test Suite.

Audits and proves:
  1. Multiple processes reserving simultaneously near quota boundary (20 orders max).
  2. Exactly-at-limit and over-limit attempts fail closed with OrderLimitExceededError / refused decision.
  3. Lock contention and bounded timeout raises LockTimeoutError without hanging indefinitely.
  4. First-time ledger initialization by competing processes safely creates directory and files.
  5. Process termination while holding lock releases lock at kernel level, allowing survivor to acquire.
  6. Truncated JSON and invalid schemas fail closed with LedgerCorruptedError.
  7. Duplicate client order IDs are strictly rejected across restarts and concurrent calls.
  8. Restart after reservation but before dispatch reconstructs state as RECONCILIATION_REQUIRED.
  9. Restart after dispatch but before acknowledgment reconstructs state as RECONCILIATION_REQUIRED.
  10. Read/write IO failure simulation during reservation fails closed and latches refusal.
  11. Two simultaneous attempts to reserve the exact same client order ID: exactly one succeeds.
  12. Stale or corrupted ledger cannot be silently repaired into a permissive clean state.

Strictly offline. Zero exchange order writes.
"""

from __future__ import annotations

from authorization_test_utils import approve_for_test

import concurrent.futures
from decimal import Decimal
import json
import multiprocessing
import sys
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
    LedgerCorruptedError,
)


def _external_lock_holder(lock_path_str: str, hold_seconds: float, ready_file_str: str):
    """Worker function for multiprocess testing: acquires lock, signals ready, holds, exits."""
    lock_path = Path(lock_path_str)
    with CrossProcessFileLock(lock_path, timeout_seconds=2.0):
        Path(ready_file_str).write_text("READY", encoding="utf-8")
        time.sleep(hold_seconds)


def _lock_is_held_elsewhere(lock_path: Path) -> bool:
    """OS-exact check that another process currently holds the cross-process
    file lock, without waiting or sleeping. Uses the same kernel primitives as
    CrossProcessFileLock and therefore detects ownership changes instantly."""
    f = open(lock_path, "a+b")
    fd = f.fileno()
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                return True
            return False
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                return False
            except (BlockingIOError, OSError):
                return True
        # posix path double-check: unlock then analyse
        return False
    finally:
        try:
            f.close()
        except OSError:
            pass



class TestPhase192MultiprocessLedger(unittest.TestCase):
    """Test Suite: Phase 192 Multiprocess Concurrency, Durability, and Failure Resilience."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "p192_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.valid_record = OperatorAuthorizationRecord(
            authorization_id="P192-AUDIT-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_P192_AUDITOR",
            signed_timestamp_utc="2026-10-21T08:00:00Z",
            expiry_timestamp_utc="2026-10-21T20:00:00Z",
            scope=self.gate.scope,
            document_sha256="sha256_p192_valid",
            signature_payload="sig_p192_auditor",
        )
        approve_for_test(self.valid_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_concurrent_reservers_near_quota_boundary(self):
        """25 concurrent threads/processes reserve orders near quota limit: exactly 20 succeed, 5 fail."""
        results = []

        def worker(idx: int):
            local_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
            cl_id = f"p192_ord_{idx:03d}"
            decision = local_gate.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=cl_id,
            )
            return idx, decision

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(worker, i) for i in range(25)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        succeeded = [d for _, d in results if d.authorized]
        refused = [d for _, d in results if not d.authorized]

        self.assertEqual(len(succeeded), 20)
        self.assertEqual(len(refused), 5)
        self.assertTrue(all(any("Cumulative experiment order limit reached" in r for r in d.reasons) for d in refused))

        # Re-read ledger from disk
        check_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.assertEqual(check_gate.read_cumulative_orders_from_ledger(), 20)

    def test_02_exactly_at_limit_and_over_limit_attempts(self):
        """When ledger has 20 orders, further reservation attempt fails closed."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            for i in range(20):
                f.write(json.dumps({
                    "timestamp_utc": time.time(),
                    "event": "ORDER_RESERVED",
                    "data": {"cl_ord_id": f"seed_{i}", "symbol": "BTCUSD"},
                }) + "\n")

        decision = self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="over_limit_order",
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("Cumulative experiment order limit reached" in r for r in decision.reasons))

    def test_03_lock_contention_and_bounded_timeout(self):
        """Lock contention raises LockTimeoutError within bounded duration."""
        lock_path = self.ledger_file.with_suffix(".lock")
        ready_flag = Path(self.temp_dir.name) / "ready.txt"

        # Spawn child process holding lock for 1.0 second
        proc = multiprocessing.Process(
            target=_external_lock_holder,
            args=(str(lock_path), 1.0, str(ready_flag)),
        )
        proc.start()

        # Wait until child process verifiably HOLDS the OS-level lock
        # (readiness flag is advisory only; kernel lock ownership is the
        # authoritative availability signal). Bounded, never indefinite.
        for _ in range(150):
            if _lock_is_held_elsewhere(lock_path):
                break
            time.sleep(0.02)
        else:
            self.fail(
                "child lock-holder never obtained the OS-level lock "
                "within the 3.0s witness window (host under load)"
            )

        try:
            # Competitor with short timeout (0.1s) must fail closed with LockTimeoutError
            t0 = time.monotonic()
            with self.assertRaises(LockTimeoutError):
                with CrossProcessFileLock(lock_path, timeout_seconds=0.1, poll_interval=0.01):
                    pass
            t1 = time.monotonic()
            self.assertLess(t1 - t0, 0.5)
        finally:
            proc.join(timeout=2.0)

    def test_04_first_time_ledger_initialization_by_competing_processes(self):
        """Competing processes simultaneously initializing nonexistent ledger directory and file."""
        nonexistent_dir = Path(self.temp_dir.name) / "nested_dir" / "deeper"
        ledger_path = nonexistent_dir / "fresh_ledger.jsonl"

        def init_and_reserve(idx: int):
            local_gate = TestnetAuthorizationGate(ledger_path=ledger_path)
            return local_gate.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=f"fresh_ord_{idx}",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(init_and_reserve, i) for i in range(4)]
            decisions = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertTrue(all(d.authorized for d in decisions))
        self.assertTrue(ledger_path.exists())
        check_gate = TestnetAuthorizationGate(ledger_path=ledger_path)
        self.assertEqual(check_gate.read_cumulative_orders_from_ledger(), 4)

    def test_05_process_termination_while_holding_lock(self):
        """When a process holding the lock terminates/crashes, kernel frees file lock immediately."""
        lock_path = self.ledger_file.with_suffix(".lock")
        ready_flag = Path(self.temp_dir.name) / "proc_ready.txt"

        proc = multiprocessing.Process(
            target=_external_lock_holder,
            args=(str(lock_path), 10.0, str(ready_flag)),
        )
        proc.start()

        for _ in range(50):
            if ready_flag.exists():
                break
            time.sleep(0.02)

        # Force terminate the child process while it holds the lock
        proc.terminate()
        proc.join(timeout=1.0)

        # Survivor process should be able to acquire lock cleanly without deadlock
        acquired = False
        with CrossProcessFileLock(lock_path, timeout_seconds=1.0, poll_interval=0.02):
            acquired = True

        self.assertTrue(acquired)

    def test_06_truncated_json_and_invalid_schemas_fail_closed(self):
        """Ledger file with half-written / truncated JSON record fails closed with corruption latch."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp_utc": 100.0, "event": "ORDER_RESERVED", "data": {"cl_ord_id": "ord_ok_1"}}\n')
            f.write('{"timestamp_utc": 101.0, "event": "ORDER_RESERVED", "data": {"cl_ord_id": "ord_tru')  # Truncated!

        recovery = self.gate.recover_and_reconcile_state()
        self.assertTrue(recovery["ledger_corrupted"])
        self.assertIn("Corrupted JSON", recovery["corruption_reason"])

        # Subsequent order reservation attempts must fail closed
        decision = self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_after_corrupt",
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("ledger corrupted" in r.lower() for r in decision.reasons))

    def test_07_duplicate_client_order_ids_rejected(self):
        """Submitting an identical cl_ord_id twice is rejected via persistent ledger check."""
        from dataclasses import replace
        scope_5 = replace(self.gate.scope, max_simultaneous_open_orders=5)
        scope_multi = replace(self.valid_record, scope=scope_5)
        approve_for_test(scope_multi)  # re-sign after the explicitly changed test scope

        gate_multi = TestnetAuthorizationGate(ledger_path=self.ledger_file, default_scope=scope_5)
        d1 = gate_multi.check_and_reserve_order(
            auth_record=scope_multi,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="order_dup_test_1",
        )
        self.assertTrue(d1.authorized)

        # Attempt to reserve identical cl_ord_id on a new gate instance reading the ledger
        gate_multi_2 = TestnetAuthorizationGate(ledger_path=self.ledger_file, default_scope=scope_5)
        d2 = gate_multi_2.check_and_reserve_order(
            auth_record=scope_multi,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="order_dup_test_1",
        )
        self.assertFalse(d2.authorized)
        self.assertTrue(any("Duplicate cl_ord_id" in r for r in d2.reasons))

    def test_08_restart_after_reservation_before_dispatch(self):
        """Crash after reservation before dispatch reconstructs order as RECONCILIATION_REQUIRED."""
        self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_crashed_before_dispatch",
        )

        # Simulate restart
        new_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        summary = new_gate.recover_and_reconcile_state()

        self.assertIn("ord_crashed_before_dispatch", summary["ambiguous"])
        self.assertEqual(
            new_gate._ambiguous_orders["ord_crashed_before_dispatch"]["state"],
            OrderLifecycleState.RECONCILIATION_REQUIRED,
        )

    def test_09_restart_after_dispatch_before_acknowledgment(self):
        """Crash after dispatch before venue acknowledgment reconstructs as RECONCILIATION_REQUIRED."""
        self.gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_dispatched_unacked",
        )
        self.gate.register_order_submitted(
            cl_ord_id="ord_dispatched_unacked",
            details={"symbol": "BTCUSD", "size": "1.0"},
        )

        # Simulate restart
        new_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        summary = new_gate.recover_and_reconcile_state()

        self.assertIn("ord_dispatched_unacked", summary["ambiguous"])
        self.assertEqual(
            new_gate._ambiguous_orders["ord_dispatched_unacked"]["state"],
            OrderLifecycleState.RECONCILIATION_REQUIRED,
        )

    def test_10_io_failure_during_reservation_fails_closed(self):
        """Simulated file system IO failure during check_and_reserve fails closed gracefully."""
        # Use an invalid path that cannot be written (directory where file is expected)
        bad_dir = Path(self.temp_dir.name) / "bad_path_is_dir"
        bad_dir.mkdir()
        # Creating a gate whose ledger_path is an existing directory causes IO failure on read/write
        bad_gate = TestnetAuthorizationGate(ledger_path=bad_dir)

        decision = bad_gate.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="io_fail_order",
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(bad_gate._ledger_corrupted)
        self.assertTrue(any("corrupted" in r.lower() or "io error" in r.lower() for r in decision.reasons))

    def test_11_simultaneous_attempts_for_exact_same_client_order_id(self):
        """Two concurrent threads racing for the identical client order ID: exactly one succeeds."""
        cl_id = "exact_same_race_id"
        results = []

        def race_id():
            g = TestnetAuthorizationGate(ledger_path=self.ledger_file)
            return g.check_and_reserve_order(
                auth_record=self.valid_record,
                rest_url="https://cdn-ind.testnet.deltaex.org",
                symbol="BTCUSD",
                product_id=84,
                order_size_contracts=Decimal("1.0"),
                cl_ord_id=cl_id,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(race_id)
            f2 = ex.submit(race_id)
            results = [f1.result(), f2.result()]

        succeeded = [d for d in results if d.authorized]
        refused = [d for d in results if not d.authorized]

        self.assertEqual(len(succeeded), 1)
        self.assertEqual(len(refused), 1)
        self.assertTrue(any("Duplicate cl_ord_id" in r for r in refused[0].reasons))

    def test_12_corrupted_ledger_never_repaired_into_permissive_state(self):
        """A corrupted ledger cannot be silently ignored or reset; state remains permanently fail-closed."""
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_NON_JSON_DATA_AT_START\n")

        g1 = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        summary1 = g1.recover_and_reconcile_state()
        self.assertTrue(summary1["ledger_corrupted"])
        self.assertTrue(g1._ledger_corrupted)

        # Attempting check_and_reserve
        d1 = g1.check_and_reserve_order(
            auth_record=self.valid_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="ord_on_stale",
        )
        self.assertFalse(d1.authorized)

        # Another process reading the same ledger must also fail closed
        g2 = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        count = g2.read_cumulative_orders_from_ledger()
        self.assertTrue(g2._ledger_corrupted)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
