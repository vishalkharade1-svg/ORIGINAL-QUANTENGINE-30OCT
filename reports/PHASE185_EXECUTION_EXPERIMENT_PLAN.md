# QUANTENGINE PHASE 185 — EXECUTION EXPERIMENT PLAN
## CONTROLLED 50-TRADE MULTI-SYMBOL DEMO EXPERIMENT SPECIFICATION

**Plan Version**: 1.0 (Phase 185)  
**Date**: 2026-10-21  
**Operating Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`  
**Target**: 50 Genuine, Completed Trade Lifecycles Across Verified Multi-Symbol Universe  
**Harness**: `scripts/run_phase185_execution_experiment.py`  

---

## 1. Objectives & Boundaries

### 1.1 Core Objectives
1. Validate multi-symbol execution architecture under authentic contract specifications.
2. Verify deterministic 120-second monotonic limit order timeout and cancellation behavior.
3. Observe queue-depletion mechanics, partial fill handling, and race reconciliation.
4. Measure full post-cost execution economics (maker/taker fees + 18% GST).
5. Produce a complete append-only tamper-evident audit ledger.

### 1.2 Strict Execution Boundaries
- **Real-Money Production Trading**: **STRICTLY PROHIBITED**.
- **Production Credentials**: Must never be used or tested in demo harness.
- **Fail-Closed Gate**: If testnet API credentials cannot be verified, live exchange writes are completely blocked (`writes_to_exchange == 0`), and the experiment runs against the offline `QueueAwarePaperExecutionEngine`.
- **No Fictitious Data**: Orders, timeouts, and cancellations must be tracked with exact timestamps and monotonic intervals without fabrication.

---

## 2. Experiment Controls & Configuration

| Parameter | Specification | Value |
|---|---|---|
| **Execution Mode** | Sandbox / Paper / Testnet Simulation | `TESTNET_SIMULATION` / `DEMO` |
| **Eligible Universe** | Verified liquid perpetual contracts | `BTCUSD`, `ETHUSD`, `SOLUSD`, `XRPUSD`, `ADAUSD` |
| **Starting Balance** | Simulated demo equity | `$10,000.00 USD` |
| **Target Completed Trades** | Completed entry-to-exit lifecycles | `50` (10 per symbol) |
| **Order Type (Entry)** | Post-only resting limit order | `LIMIT_POST_ONLY` |
| **Order Type (Exit)** | Protective bracket exit | `LIMIT` / `MARKET_PROTECTIVE` |
| **Default Order Timeout** | Monotonic resting limit order deadline | `120.0 seconds` |
| **Max Risk Per Trade** | Hard stop loss risk budget | `$150.00 USD` |
| **Max Concurrent Positions** | Maximum simultaneous exposure | `1` per symbol, `3` total |
| **Fee Assumptions** | Delta Exchange India maker/taker | Maker `0.02%`, Taker `0.05%`, GST `18%` |
| **Hurdle Gates** | Friction hurdle constraints | Max fee ratio `40%`, Min post-fee R:R `1.25x`, Min BE `2.0x` |

---

## 3. Order Lifecycle & Two-Minute Timeout Protocol

For every candidate signal:
1. **Pre-Submission**: Client Order ID minted (`CL-{symbol}-{seq}`); intent recorded before transmission.
2. **Safety Evaluation**: Evaluated through `TestnetSafetyGate` and `FrictionHurdleGate`. Fails closed if constraints breached.
3. **Resting Queue Placement**: Placed onto book tick grid; initial queue ahead recorded.
4. **120-Second Monotonic Timer**: Monotonic timestamp recorded (`submission_mono_ns`).
5. **Execution Scenarios**:
   - **Full Fill**: Incoming market volume depletes queue; order fills completely; protective exit bracket armed.
   - **Partial Fill**: Order fills partially; if 120s expires before completion, cancellation requests cancellation of ONLY remaining quantity. Actual filled quantity is managed.
   - **Timeout (No Fill)**: 120 seconds elapse without fill; cancellation dispatched; order transitions to `CANCELLED`. Not converted to market order. Not counted as a completed trade.
   - **Race Condition**: Fill arrives while cancel is in flight; actual cumulative fill reconciled; order marked `FILLED`.
   - **Ambiguous State**: If exchange acknowledgement or cancel status is uncertain, order moves to `UNKNOWN_RECONCILING` and the affected symbol is HALTED for all new entries.

---

## 4. Emergency Stop & Halt Conditions

The experiment must immediately cease submitting new orders upon:
1. Any detection of production endpoints (`https://api.delta.exchange`).
2. Any order state ambiguity or reconciliation failure.
3. Any unexpected position exposure appearing.
4. Failure to confirm cancellation on a timed-out order.
5. Drawdown exceeding $200.00 USD or account equity falling below $9,500.00 USD.
6. Market data corruption or book inversion (`best_bid >= best_ask`).

---

## 5. Artifact & Evidence Recording Plan

- **Ledger**: `research/results/phase185_execution_experiment_ledger.jsonl` (append-only JSONL recording every lifecycle event).
- **Summary**: `research/results/phase185_execution_experiment_summary.json` (machine-readable aggregate metrics).
- **Report**: `reports/PHASE185_EXECUTION_EXPERIMENT_RESULTS.md` (detailed audit findings).
