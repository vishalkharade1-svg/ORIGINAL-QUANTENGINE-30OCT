# QUANTENGINE PHASE 175 — DATA EVIDENCE & STATISTICAL READINESS AUDIT

**Audit Date**: 2026-10-20  
**Status**: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  

---

## 1. Inventory & Lineage of Available Datasets

| Dataset Description | Relative Path | Record Count / Rows | Temporal Interval (UTC) | Integrity SHA-256 | Overlap with Other Datasets |
|---|---|---|---|---|---|
| **BTC 1-Minute Continuous Candles** | [`data/history/BTCUSDT/1m.parquet`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/data/history/BTCUSDT/1m.parquet) | 1,440 rows (24 hours) | `2026-09-05T00:00:00Z` to `2026-09-05T23:59:00Z` | `f3bf5261ca942bf9ec89ae397c729e2621c17ee1917f6942ad55848cb66b96e5` | **None** (Isolated September window) |
| **High-Frequency L2 Order Book Updates** | [`research/captures/phase167_recon/l2/delta_ob_updates_archive.json`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/research/captures/phase167_recon/l2/delta_ob_updates_archive.json) | 113 frames | `2026-10-19T14:26:00Z` to `2026-10-19T14:32:00Z` | `b78a94665a363a033f6df23b6b64f9bf3cf8dfc94294ca238a0b0d62d22b512e` | **None** (Isolated October window) |
| **Authenticated Testnet Fills** | [`research/captures/phase168_delta_reconciled/`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/research/captures/phase168_delta_reconciled/) | **2 fills** (Leg 1 entry, Leg 2 exit) | `2026-10-19T14:26:04Z` | Verified via detached records | Matches L2 session; $N=2$ only |

---

## 2. Non-Overlapping Dataset Constraint

A critical finding from Phase 174 and Phase 175:
- The 1-minute candle history (`1m.parquet`) covers **September 5, 2026**.
- The Level-2 order book updates (`delta_ob_updates_archive.json`) cover **October 19, 2026** (44 days later).
- **Zero Temporal Overlap**: The candle window and the Level-2 order book capture do NOT overlap by even one second.
- **Auditing Invariant**: It is forbidden to concatenate or merge these datasets and claim "synchronized end-to-end signal-to-execution backtesting." All post-cost evaluations using L2 depth on candle signals are **simulated cross-sectional parameter scenarios**, not empirical joint observations.

---

## 3. Authenticated Execution Sample Size ($N=2$)

- The repository contains exactly **two authenticated testnet executions** ($N=2$) for BTCUSD from Phase 168:
  - Fill 1 (Buy Entry): `price: 82015.5`, `size: 1`, `created_at: 2026-10-19T14:26:04.120Z`
  - Fill 2 (Sell Exit): `price: 82020.0`, `size: 1`, `created_at: 2026-10-19T14:26:18.705Z`
- Multiple JSON representations and ledger views of these identical two fills exist in `research/captures/`.
- **Sample Power Invariant**: The authenticated fill count is strictly **$N=2$**, which is far below the initial exploratory threshold of $N \ge 30$, and completely insufficient for statistical power or distribution modeling (`BLOCK-175-04`).

---

## 4. Scope of Unprofitability & Expectancy Claims

### Distinction of Claims
In quantitative risk and execution auditing, we must strictly separate:
1. **Setup Fails a Specific Modeled Cost Scenario**:
   - The 4.5-pt, 15-pt, and 50-pt setups fail the `FrictionHurdleGate` when evaluated against the verified Delta Exchange standard fee schedule ($2.36$ bps maker / $5.90$ bps taker) + modeled $2.0$ bps adverse selection.
   - This is an **empirically proven mathematical fact** for this specific model configuration.
2. **Strategy is Universally Unprofitable**:
   - Proving that a micro-scalp setup fails under a $2.36$ bps fee does **NOT** prove that micro-scalping is universally impossible under all market conditions, venue tiers, or fee regimes.
   - For instance, institutional liquidity providers with negative maker rebate tiers (e.g., $-1.0$ bps or $-0.5$ bps) or zero-fee promotional venues operate under entirely different cost curves.
3. **Historical Backtest vs Empirical Truth**:
   - Queue fill models ($86.47\%$ any-fill, $86.20\%$ complete-fill) remain classified as **`SIMULATION_ASSUMPTION`**. They cannot be cited as empirical fill rates until calibrated against high-frequency Market-by-Order (MBO) order-level feeds.

---

## 5. Proposed Testnet Protocol Requirements

Before any future testnet campaign can be executed to expand the $N=2$ fill sample, all 10 prerequisites must be satisfied:
1. Explicit operator sign-off and authorization.
2. Operator-supplied India testnet API keys (stored in sealed `.env.testnet`).
3. Bounded operational scope: maximum 5 orders, 1 contract per order, max 10-minute runtime.
4. Symbol restricted strictly to `BTCUSD` (Product ID 84).
5. Pre-flight verification of zero open orders and flat position.
6. Real-time post-trade position flatness check.
7. Verification of matching wallet cashflow debits/credits in USD.
8. Execution isolation: zero live trading adapter connections.
9. Privacy scan execution immediately post-run.
10. Automatic kill-switch on any unhandled error or disconnect.
