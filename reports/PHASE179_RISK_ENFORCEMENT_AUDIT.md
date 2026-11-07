# QuantEngine Phase 179 — End-to-End Risk Enforcement & Execution Boundary Audit

## Executive Summary

Phase 179 traced candidate trade creation through the full order lifecycle:
`Instrument Metadata -> Tick Normalization -> Stop Risk Recalculation -> Friction Hurdle Gate -> Paper Order Dispatch`

All execution paths were verified to enforce authoritative metadata, normalize prices onto the 0.10 tick grid, recalculate cost-adjusted risk, and fail closed prior to resting order submission.

---

## 1. End-to-End Pipeline Architecture

```
[ Trade Candidate ]
        │
        ▼
[ 1. Instrument Metadata Validation ]
        │ ── Invalid / Conflicting metadata ─────────► [ REJECTED_CONSTRAINTS ] (Halted)
        ▼
[ 2. Deterministic Price Normalization ]
        │ ── Non-numeric / Non-positive inputs ──────► [ REJECTED_CONSTRAINTS ] (Halted)
        ▼
[ 3. Post-Normalization Stop Risk Audit ]
        │    - Gross risk recalculated at normalized stop
        │    - Round-trip fees (Maker entry + Taker stop exit) + 18% GST added
        │ ── Normalized Risk > Risk Budget ──────────► [ REJECTED_RISK ] (Halted)
        ▼
[ 4. Friction Hurdle Gate Evaluation ]
        │ ── Fee Ratio > 40% OR Multiple < 2.0x ─────► [ REJECTED_RISK ] (Halted)
        ▼
[ 5. Paper Engine Dispatch (Queue-Aware) ]
        │ ── Post-Only Crossing Spread ──────────────► [ REJECTED_POST_ONLY ] (Halted)
        ▼
[ 6. Resting Order in Queue ]
        │
        ├── Market Fill / Cancellation Update
        └── Risk Amendment (Re-runs Risk Audit; fails closed on breach)
```

---

## 2. Execution Boundary Proofs

1. **Non-Bypassability of Risk Gate:**
   - Evaluated in `QueueAwarePaperExecutionEngine.submit_candidate_trade()`.
   - When a candidate's normalized stop risk breaches the risk budget, the engine constructs a `PaperOrder` with state `PaperOrderState.REJECTED_RISK`.
   - The rejected order is recorded in `completed_orders` and **never** added to `active_orders`.
   - Zero adapter calls, zero quote dispatches.
2. **Order Amendment Risk Recalculation:**
   - Evaluated in `QueueAwarePaperExecutionEngine.amend_order_risk()`.
   - If an active resting order has its quantity or stop price amended such that normalized risk exceeds the risk budget, the engine immediately removes the order from `active_orders` and sets state to `REJECTED_RISK`.
3. **Post-Cost Backtester Gate Integration:**
   - Evaluated in `PostCostBacktester.evaluate_candidate()`.
   - Candidates carrying a `risk_budget` are pre-audited via `audit_and_recalculate_stop_risk()`. Breached candidates return `HurdleVerdict(allowed=False)` and are rejected from the backtest before order placement.
4. **Execution Isolation:**
   - `assert_no_live_adapter_invocation()` verified across all candidate submissions and order transitions.

---

## 3. Risk Calculation Examples Across Boundaries

### Case A: Long Setup Within Risk Budget (`APPROVED`)
- **Inputs:** Entry = $82,000.00, Raw Stop = $81,950.00, Quantity = 1, Contract Multiplier = 0.001, Risk Budget = $0.1500 USD.
- **Normalization:** Normalized Stop = $81,950.00 (On-tick).
- **Gross Risk:** $(82,000 - 81,950) \times 0.001 \times 1 = \$0.05000000$ USD.
- **Entry Fee (Maker):** $82,000 \times 0.001 \times 1 \times 0.000236 = \$0.01935200$ USD.
- **Stop Exit Fee (Taker):** $81,950 \times 0.001 \times 1 \times 0.000590 = \$0.04835050$ USD.
- **Total Normalized Risk:** $\$0.05000000 + \$0.01935200 + \$0.04835050 = \$0.11770250$ USD.
- **Decision:** $\$0.11770250 \le \$0.15000000 \implies$ **`APPROVED`** (Verdict: `allowed=True`).

### Case B: Long Setup Breaching Tight Risk Budget (`REJECTED_RISK`)
- **Inputs:** Identical prices ($82,000 entry, $81,950 stop), but Risk Budget = $0.0500 USD.
- **Total Normalized Risk:** $\$0.11770250$ USD.
- **Decision:** $\$0.11770250 > \$0.05000000 \implies$ **`REJECTED_RISK`** (`valid=False`, dispatched order blocked).

### Case C: Directional Asymmetry Short Setup (`APPROVED`)
- **Inputs:** Entry = $82,000.00, Raw Stop = $82,050.00, Quantity = 1, Risk Budget = $0.1500 USD.
- **Normalization:** Normalized Stop = $82,050.00.
- **Gross Risk:** $(82,050 - 82,000) \times 0.001 \times 1 = \$0.05000000$ USD.
- **Total Normalized Risk:** $\$0.05000000 + \$0.01935200 + \$0.04840950 = \$0.11776150$ USD.
- **Decision:** $\$0.11776150 \le \$0.15000000 \implies$ **`APPROVED`**.
