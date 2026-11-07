# QUANTENGINE PHASE 185 — FINDINGS REGISTER

**Audit Date**: 2026-10-21  
**Phase**: 185  
**Operating Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`  
**Release Gate**: `HOLD / BLOCKED_EVIDENCE`  

---

## Index of Findings

| Finding ID | Severity | Category | Title | Status |
|---|---|---|---|---|
| **F-185-01** | `INFORMATIONAL / RESOLUTION` | Exchange Metadata | Product ID 84 (BTCUSD) Contract Multiplier Certified via Live Venue Capture | **RESOLVED** |
| **F-185-02** | `SECURITY / ARCHITECTURE` | Safety Gate | Dedicated Testnet Safety Gate Enforcing Absolute Production Endpoint Isolation | **IMPLEMENTED** |
| **F-185-03** | `ARCHITECTURE` | Instrument Registry | Multi-Symbol Eligibility Registry Covering 5 Liquid Perpetual Contracts | **IMPLEMENTED** |
| **F-185-04** | `EXECUTION_POLICY` | Timeout & Reconciliation | Deterministic 120-Second Monotonic Order Timeout with Partial-Fill Preservation | **IMPLEMENTED** |
| **F-185-05** | `DEFECT_REMEDIATION` | Friction Gate | Latent Short Setup Defect Repaired in Friction Hurdle Gate | **REPAIRED** |
| **F-185-06** | `VERIFICATION` | Execution Experiment | Controlled 50-Trade Multi-Symbol Experiment Completed with Zero Venue Writes | **VERIFIED** |

---

## Detailed Findings

### F-185-01: Product ID 84 Contract Multiplier Certified via Live Venue Capture
- **Category**: Exchange Metadata Authority
- **Severity**: `INFORMATIONAL / RESOLUTION`
- **Description**: Standing blocker `BLOCK-184-03` questioned whether Product ID 84 (`BTCUSD`) had authoritative venue proof for its 0.001 multiplier. On 2026-10-21, a direct query to Delta Exchange India Testnet (`https://cdn-ind.testnet.deltaex.org/v2/products`) retrieved the authoritative product definition.
- **Evidence**: `research/results/phase185_testnet_products_snapshot.json` records ID 84 `contract_value = "0.001"`, `tick_size = "0.1"`, `quoting_asset = "USD"`, `settling_asset = "USD"`.
- **Resolution**: `BLOCK-184-03` is permanently closed.

---

### F-185-02: Dedicated Testnet Safety Gate Enforcing Absolute Production Isolation
- **Category**: Security & Execution Safety
- **Severity**: `SECURITY / ARCHITECTURE`
- **Description**: To ensure that demo or testnet execution cannot silently or accidentally route orders to real-money production accounts, a separate, hardened `TestnetSafetyGate` was authored in `core/execution/testnet_safety_gate.py`.
- **Key Invariants**:
  1. Rejects production REST and WebSocket endpoints (`api.delta.exchange`, `india.delta.exchange`) with typed `ProductionEndpointAttemptedError`.
  2. Prohibits production credential reuse (`DELTA_API_KEY`).
  3. Fails closed on missing testnet credentials, inverted orderbooks, and risk budget breaches.
  4. Mints per-process tamper-resistant decision tokens.

---

### F-185-03: Multi-Symbol Eligibility Registry Covering 5 Liquid Perpetual Contracts
- **Category**: Architecture & Symbol Expansion
- **Severity**: `ARCHITECTURE`
- **Description**: Implemented `SymbolEligibilityRegistry` (`core/execution/symbol_registry.py`) providing structured lifecycle tracking: `DISCOVERED`, `METADATA_VERIFIED`, `DATA_VERIFIED`, `RISK_VERIFIED`, `TESTNET_VERIFIED`, `ELIGIBLE`, `REJECTED`, `BLOCKED_EVIDENCE`.
- **Certified Universe**:
  1. `BTCUSD`: Product ID 84, Multiplier 0.001, Tick 0.10
  2. `ETHUSD`: Product ID 1699, Multiplier 0.01, Tick 0.05
  3. `SOLUSD`: Product ID 92572, Multiplier 1.0, Tick 0.0001
  4. `XRPUSD`: Product ID 93723, Multiplier 1.0, Tick 0.0001
  5. `ADAUSD`: Product ID 101760, Multiplier 1.0, Tick 0.00001
- High-multiplier contracts (`DOGEUSD`, mult 100) and synthetic index perps (`QQQXUSD`) remain held in `RISK_VERIFIED` / `BLOCKED_EVIDENCE`.

---

### F-185-04: Deterministic 120-Second Monotonic Order Timeout Policy
- **Category**: Execution Policy & Reconciliation
- **Severity**: `EXECUTION_POLICY`
- **Description**: Implemented `TwoMinuteOrderPolicyManager` (`core/execution/two_minute_order_policy.py`) and wired timeout checks into `QueueAwarePaperExecutionEngine`.
- **Key Invariants**:
  1. High-resolution monotonic clock tracking (`submission_mono_ns`).
  2. 120-second timeout cancellation of resting orders without conversion to market orders.
  3. Cancels only remaining quantity on partial fills; preserves filled quantity.
  4. Reconciles fill vs. cancel race conditions.
  5. Fails closed with symbol-level entry halt upon ambiguous or failed cancellation.

---

### F-185-05: Latent Short Setup Defect Repaired in Friction Hurdle Gate
- **Category**: Defect Remediation
- **Severity**: `DEFECT_REMEDIATION`
- **Description**: In `core/execution/friction_hurdle_gate.py`, `gross_target = rt.gross_pnl` computed negative gross profit for short setups (`tp < ep`), causing all short orders to fail the post-fee R:R hurdle (`post_fee_rr < 1.25`).
- **Remediation**: Updated to `gross_target = abs(rt.gross_pnl)`, ensuring symmetric reward-to-risk and fee-ratio calculations for both long and short trades. Proven by unit test suite.

---

### F-185-06: Controlled 50-Trade Multi-Symbol Experiment Completed with Zero Venue Writes
- **Category**: Verification & Evidence Capture
- **Severity**: `VERIFICATION`
- **Description**: Ran `scripts/run_phase185_execution_experiment.py`.
- **Results**:
  - Live testnet write gate: evaluated and properly refused (`BLOCKED_EVIDENCE: API_CREDENTIALS_NOT_PROVISIONED`). Zero write calls sent.
  - Controlled paper execution: 50 completed trade lifecycles across 5 symbols.
  - 55 submitted orders, 50 full fills, 5 intentional 120s timeouts cancelled cleanly.
  - Net Realized PnL: $383.03 USD; Max Drawdown: $22.57 USD.
  - Append-only tamper-evident ledger created: `research/results/phase185_execution_experiment_ledger.jsonl` (206 lines).
