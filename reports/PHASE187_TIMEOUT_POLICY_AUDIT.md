# QuantEngine Phase 187: Two-Minute Order Timeout Policy Audit

**Audit Version**: `1.0.0-phase187`  
**Date**: `2026-10-21`  
**Target Policy**: Strict 120-Second Resting Order Cancellation  
**Verification Method**: Offline Deterministic Mocks & Microstructure Replay (Zero Venue Writes)  
**Policy Status**: `TIMEOUT_POLICY_VERIFIED_OFFLINE` (Paper / Simulation Separated from Venue)  

---

## 1. Executive Summary

QuantEngine enforces a non-negotiable two-minute (120-second) maximum resting time for passive limit orders. The objective of this policy is to eliminate stale limit orders, protect against adverse regime shifts, and avoid uncompensated inventory risk.

This audit:
1. Formally resolves the distinction between simulated timeout cancellation (paper engine) and physical exchange cancellation (matching engine).
2. Explains the Phase 186 observation where 5 paper timeouts were cancelled at ~125 seconds against the 120-second policy.
3. Formulates the state machine for in-flight cancellation races and partial fills.
4. Confirms that **under no circumstances does a timed-out order convert to a taker market order**.

---

## 2. Temporal State Machine: Simulated vs. Physical Exchange Cancellation

A critical finding of Phase 186 and Phase 187 forensics is that a simulator's internal transition must never be conflated with venue matching-engine confirmation.

### 2.1 The Five Discrete Timeout Milestones

```mermaid
sequenceDiagram
    participant Engine as QuantEngine Core
    participant Net as Network Transport
    participant Venue as Delta Matching Engine

    Note over Engine: t = t_0: Order Submitted (Monotonic Clock Marked)
    Note over Engine: t = t_0 + 120.0s: Monotonic Deadline Reached
    Engine->>Net: 1. Dispatch Cancel Request (DELETE /v2/orders)
    Note over Net: Network Transit Delay (Delta_t_transit ~ 50-250ms)
    Net->>Venue: 2. Cancel Request Arrives at Exchange
    alt Case A: Cancel Arrives Before Fill
        Venue->>Venue: Cancel Processed; Order State -> CANCELLED
        Venue-->>Net: 3. Cancellation Acknowledged (200 OK / WS status)
        Net-->>Engine: 4. Terminal State Confirmed (CANCELLED)
    else Case B: Fill Occurred In-Flight (Match Race)
        Venue->>Venue: In-Flight Match Executed; Order State -> FILLED
        Venue-->>Net: 3b. Fill Acknowledged (v2/user_trades)
        Net-->>Engine: 4b. Late Fill Reconciled (Filled Size Updated)
    end
```

### Milestone Definitions:
1. **Milestone 1 — Deadline Reached ($t_{deadline} = t_0 + 120.0\text{s}$)**: High-resolution monotonic timer triggers cancellation routine.
2. **Milestone 2 — Cancellation Request Dispatched**: Signed HTTP `DELETE` or WebSocket cancellation frame transmitted over wire.
3. **Milestone 3 — Cancellation Acknowledged**: Exchange HTTP response (`200 OK`) or WebSocket response received.
4. **Milestone 4 — Terminal State Confirmed**: Order status confirmed as `CANCELLED` via venue event feed.
5. **Milestone 5 — Fill Reconciliation**: Verification that zero fills occurred during wire transit, or exact binding of any in-flight partial fills.

---

## 3. Root Cause Analysis: Phase 186 ~125s Paper Cancellations

The Phase 186 audit noted that 5 paper timeout scenarios were cancelled at approximately 125 seconds rather than exactly 120.00 seconds.

### Root Cause: Discrete Polling Tick Quantization
In `scripts/run_phase185_execution_experiment.py`, the paper execution event loop evaluated order timeouts on discrete 5-second polling intervals:
```python
# Event loop tick: sleep 5.0 seconds
await asyncio.sleep(5.0)
engine.check_order_timeouts(current_mono_ns=time.monotonic_ns())
```
- At $t = 119.9\text{s}$, the deadline was not yet reached ($119.9 < 120.0$).
- The next evaluation occurred at $t = 124.9\text{s} - 125.1\text{s}$, at which point the elapsed time was $\ge 120.0\text{s}$, triggering cancellation.
- **Verdict**: The order was NOT kept alive due to policy erosion. It was cancelled on the very first evaluation tick following deadline expiry.

### Phase 187 Hardening:
In Phase 187, `L2BookTracker` and `QueueAwarePaperExecutionEngine` support event-driven monotonic timestamp checking on every inbound market frame, eliminating polling quantization delay.

---

## 4. Safety Invariants & Negative Protections

### Invariant 1: Zero Market Order Conversion
**An expired post-only limit order must NEVER be converted into a taker market order.**
- Rationale: Market order conversion forces taker fee drag (-5.9 bps with GST) and unbounded slippage, destroying strategy edge.
- Code Verification: `QueueAwarePaperExecutionEngine.check_order_timeouts()` strictly transitions active orders to `PaperOrderState.CANCELLED`. `order.order_type` remains `LIMIT_POST_ONLY`.

### Invariant 2: Monotonic Clock Authority
- Wall-clock time (`time.time()`) is vulnerable to NTP synchronization jumps, VM time-drift, and leap seconds.
- Timeout deadlines are strictly evaluated using `time.monotonic_ns()`.

### Invariant 3: Protective Handling of Partial Fills
If an order filled $q_{filled} < q_{total}$ prior to timeout:
- The filled quantity $q_{filled}$ is retained and recorded with exact fee decomposition.
- The remaining quantity $q_{remaining} = q_{total} - q_{filled}$ is cancelled.
- If $q_{filled} > 0$, the corresponding protective stop and target orders must be adjusted to protect the actual filled quantity, preventing naked exposure.

### Invariant 4: Fail-Closed On Uncertain State
If a cancellation request times out or disconnects:
- The system enters `RESYNCING` / `UNCERTAIN` state.
- No new orders may be placed until REST reconciliation confirms whether the order was cancelled or filled.

---

## 5. Offline Test Suite Verification

The timeout invariants are verified offline by `tests/test_phase187_l2_queue_and_security.py::TestPhase187TimeoutPolicyOffline`:
- `test_120s_timeout_cancels_without_market_conversion`: **PASSED**.
- Orders resting at 119s remain resting. At 120s, orders are cancelled with 0 filled quantity and zero market conversion.
