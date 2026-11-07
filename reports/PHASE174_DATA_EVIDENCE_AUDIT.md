# QUANTENGINE PHASE 174 — DATA EVIDENCE, LINEAGE & TESTNET PROTOCOL AUDIT

**Audit Date**: 2026-10-20  
**Status**: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Primary Focus**: Data Asset Verification, Temporal Boundary Analysis & Authorized Testnet Experiment Protocol

---

## 1. Inventory of Repository Data Assets

An independent byte-level audit was conducted across all active data assets in the repository:

### A. 1-Minute Parquet OHLCV Candles
- **Path**: `data/history/BTCUSDT/1m.parquet`
- **File Size**: $38,552$ bytes
- **SHA-256 Digest**: `3c6836848e4c78a11422f103aacf997d438c5ef9050902f5f376429b71c8933f`
- **Total Rows**: Exactly **1,440 continuous rows** (24 continuous hours)
- **Start Timestamp**: `2026-09-05T21:35:00+00:00`
- **End Timestamp**: `2026-09-06T21:34:00+00:00`
- **Data Integrity**: Continuous timestamps at 60-second intervals; zero internal gaps; zero duplicate timestamps; monotonically increasing.

### B. High-Frequency Level-2 Order Book Snapshots
- **Path**: `research/captures/phase167_recon/l2/delta_ob_updates_archive.json`
- **File Size**: $57,001$ bytes
- **SHA-256 Digest**: `b14f39e019e5c5d0483d02be4251d04852416c13ab49da76a41410f21c986e3a`
- **Total Frames**: Exactly **113 updates**
- **Capture Date**: `2026-10-19` (High-frequency Delta orderbook capture)

### C. Authenticated Execution Fill Records
- **Attributable Venue Executions**: Exactly **$N = 2$ fills** (from historical pilot testnet captures in Phase 80/81).
- **Statistical Significance**: $N = 2$ is wholly inadequate for statistical inference. Formal validation requires at least **$N \ge 30$ fills** under varied market volatility regimes.

---

## 2. Temporal Disjunction & Lineage Disclosure

> [!WARNING]
> **TEMPORAL NON-OVERLAP CONFIRMED**
> The 1m parquet candle data spans **2026-09-05T21:35:00Z to 2026-09-06T21:34:00Z**, whereas the Level-2 order book frames date from **2026-10-19**.
> 
> Because these two datasets represent non-overlapping calendar windows separated by approximately 43 days:
> 1. No synchronized signal-to-execution tick replay is currently possible.
> 2. Level-2 orderbook depth cannot be used to backtest 1m candle breakout signals directly.
> 3. Multi-year 2024–2026 tick depth is unsupplied in repository assets and is tracked as an active blocker under `BLOCK-174-05`.

---

## 3. Historical Account Blockers

### A. Historical ADAUSD Position Closure (`BLOCK-174-02`)
- **Status**: `UNRESOLVED`
- **Description**: The historical ADAUSD open position belonged to a pre-rotation operator credential. While the current testnet account is verified completely flat, closure of the position on the historical account cannot be proved without original venue ledger captures.
- **Rule**: Per Safety Rule #12, this blocker is not closed or fabricated; it remains marked `UNRESOLVED`.

---

## 4. Proposed Protocol for Future Operator-Authorized Testnet Experiment

In strict adherence to Safety Rules #1, #2, and #3, **no testnet orders were placed in Phase 174**.
Before any future testnet campaign may be initiated, the following deterministic protocol must be formally authorized by the operator:

### Phase A: Operator Pre-Flight Authorization
1. Explicit written operator approval defining campaign scope, budget, and risk boundaries.
2. Verification of endpoint URLs: enforce strictly `https://cdn-ind.testnet.delta.exchange` (Delta India Testnet) or equivalent testnet endpoints. Prohibit any production IP/URL.
3. Verification that credentials are loaded exclusively from isolated testnet environment variables.

### Phase B: Pre-Experiment Account Baseline
1. Query testnet balance: record initial wallet collateral in USDT.
2. Query open orders: assert exactly 0 open orders exist.
3. Query open positions: assert account is completely flat (0 positions across all symbols).
4. System clock synchronization: NTP validation verifying system clock skew $< 200 \text{ ms}$.

### Phase C: Bounded Execution Scope
1. **Allowed Instrument**: BTCUSDT only.
2. **Order Type**: Passive Post-Only Limit (`order_type="LIMIT_POST_ONLY"`).
3. **Order Size**: Strictly 1 contract ($0.001$ BTC multiplier).
4. **Max Orders per Session**: 5 orders maximum.
5. **Session Duration**: 15 minutes maximum.
6. **Safety Kill-Switch**: If an order fills as taker or if spread inversion occurs, instantly cancel all orders and abort.

### Phase D: Post-Experiment Reconciliation
1. Query final account position: assert account has returned to flat (0 open positions).
2. Query open orders: cancel any resting residual orders; assert 0 open orders.
3. Download venue ledger records: verify actual commission debit matches maker rate ($2.36$ bps) and 18% GST.
4. Calculate slippage and markout at 1s, 5s, 10s, and 30s post-fill.
5. Redact private credentials and session tokens before persisting evidence.
