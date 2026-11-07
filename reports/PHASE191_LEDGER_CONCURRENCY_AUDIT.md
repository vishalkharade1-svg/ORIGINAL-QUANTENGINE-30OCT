# QuantEngine Phase 191 — Authorization Ledger Concurrency Audit Report

**Audit Component**: `Phase191LedgerConcurrencyAudit`  
**Date**: 2026-10-21  
**Auditor**: Senior Autonomous Python Engineer & Execution-Safety Auditor  
**System Posture**: `NOT_PRODUCTION_READY`  
**Strategy Status**: `EDGE NOT ESTABLISHED`  
**Release Gate**: `HOLD`  
**Order Writes to Exchange**: `0` (Strictly Offline & Read-Only Tests)

---

## 1. Executive Summary

In Phase 190, an architectural limitation was identified: `TestnetAuthorizationGate.evaluate_preflight()` and `record_order_event_to_ledger()` lacked cross-process synchronization. If two separate processes evaluated preflight concurrently when 19 orders were logged, both could receive authorization and submit orders #20 and #21, violating the 20-order cumulative ceiling.

In Phase 191, this concurrency vulnerability has been resolved:
1. Implemented `CrossProcessFileLock` providing true OS-level mutual exclusion across concurrent processes on Windows (`msvcrt.locking`) and POSIX (`fcntl.flock`).
2. Implemented atomic `check_and_reserve_order()`, combining preflight evaluation, duplicate order ID checking, quota enforcement, and persistent ledger append into a single synchronized critical section.
3. Implemented crash-safe durability: each reservation is flushed and synced to disk via `os.fsync(fileno)` under the lock before the gate returns authorization.
4. Enforced bounded waits: lock acquisition times out after 5.0s (configurable) raising typed `LockTimeoutError`, preventing indefinite blocking.
5. Tested under multi-process contention with 25 concurrent callers; exactly 20 orders were authorized and 5 were refused.

---

## 2. Cross-Process Locking Architecture

### 2.1 OS-Level Mutex Design

A process-local mutex (`threading.Lock`) cannot protect across separate Python processes. A file-based locking mechanism was implemented in `core/execution/testnet_authorization_gate.py`:

```python
class CrossProcessFileLock:
    """Bounded, crash-safe cross-process file lock supporting Windows (msvcrt) and POSIX (fcntl)."""
```

- **Windows Architecture**: Uses `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` on a dedicated lock file (`<ledger>.lock`).
- **POSIX Architecture**: Uses `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`.
- **Reentrancy**: Implements thread-local reentrancy tracking (`_local.held_locks`), permitting nested calls within the same thread while strictly serializing across distinct threads and OS processes.
- **Bounded Waiting**: Non-blocking lock attempts poll at 20 ms intervals until success or timeout (`timeout_seconds = 5.0`). On timeout, raises `LockTimeoutError`.
- **Crash Recovery**: File locks held by the OS kernel are automatically released if a process crashes, terminates abnormally, or is killed by `SIGKILL` / `taskkill`, eliminating dangling stale locks.

---

## 3. Atomic Check-and-Reserve Transaction

The method `check_and_reserve_order()` establishes an atomic transaction:

```python
def check_and_reserve_order(
    self,
    auth_record: OperatorAuthorizationRecord,
    rest_url: str,
    symbol: str,
    product_id: int,
    order_size_contracts: Decimal | float,
    cl_ord_id: str,
    order_details: Optional[Dict[str, Any]] = None,
    post_only: bool = True,
    cumulative_realized_loss: Decimal | float = Decimal("0.0"),
    lock_timeout_seconds: float = 5.0,
) -> AuthorizationDecision:
```

### Execution Steps Inside Critical Section:
1. **Acquire Cross-Process Lock**: Lock file `<ledger_path>.lock`.
2. **Execute Full Preflight Checks**:
   - Kill switch verification.
   - Production endpoint isolation (typed `ProductionEndpointAttemptedError`).
   - Authorization document validity & template placeholder check.
   - Scope, symbol, and product ID validation.
   - Sizing, post-only, and realized loss budget verification.
   - Ambiguous order check (refuses if any order is in `RECONCILIATION_REQUIRED`).
   - Single open order check (refuses if open orders >= 1).
3. **Parse Persistent Ledger**:
   - Scans entire ledger file line-by-line.
   - Detects malformed/truncated records, setting `_ledger_corrupted = True` and failing closed.
   - Calculates exact cumulative orders placed (`ORDER_RESERVED`, `ORDER_SUBMITTED`, `ORDER_PLACED`).
   - Verifies cumulative count < 20.
4. **Duplicate Order ID Detection**:
   - Scans in-memory and disk records for `cl_ord_id`.
   - Refuses immediately if `cl_ord_id` has already been reserved or placed.
5. **Durable Reservation Append**:
   - Writes `ORDER_RESERVED` JSON record.
   - Executes `f.flush()` and `os.fsync(f.fileno())` to ensure immediate physical disk write.
6. **Update In-Memory Tracking**:
   - Adds `cl_ord_id` to `_active_open_orders` with state `OrderLifecycleState.RESERVED`.
7. **Release Lock & Return Authorized Decision**:
   - Mint token attached only upon successful completion.

---

## 4. Test Verification Matrix

Automated verification was conducted in `tests/test_phase191_ledger_concurrency.py`:

| Test Name | Concurrency Scenario | Injected Condition | Expected Behavior | Observed Result | Verdict |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `test_concurrent_callers_respect_twenty_order_ceiling` | 25 concurrent callers | High contention racing for 20 slots | Exactly 20 authorized, 5 refused; disk ledger = 20 | 20 authorized, 5 refused, ledger = 20 | **PASS** |
| `test_serialized_reservation_prevents_slot_oversubscription` | 2 concurrent processes | Ledger at 19 orders; both race for slot 20 | Exactly 1 succeeds, 1 refused with limit breach | 1 authorized, 1 refused with cumulative limit | **PASS** |
| `test_lock_timeout_bounded_wait_fails_closed` | 1 holder, 1 waiter | Lock held for 2.0s; waiter timeout = 0.1s | Waiter raises `LockTimeoutError`, fails closed | `LockTimeoutError` raised at 0.1s | **PASS** |
| `test_duplicate_client_order_id_concurrent_rejection` | 2 concurrent callers | Both race with identical `cl_ord_id` | Exactly 1 succeeds, 1 refused with duplicate ID error | 1 authorized, 1 refused with duplicate reason | **PASS** |
| `test_corrupted_ledger_concurrent_refusal` | 4 concurrent callers | Ledger contains truncated garbage line | All 4 fail closed with `_ledger_corrupted = True` | All 4 refused: `Persistent ledger corrupted` | **PASS** |

---

## 5. Summary Verdict

**Ledger Concurrency & Race Condition Audit**: **PASS**  
The cross-process locking and atomic reservation architecture prevents slot oversubscription, duplicate order ID collision, and unpersisted reservations under arbitrary concurrent multi-process execution.
