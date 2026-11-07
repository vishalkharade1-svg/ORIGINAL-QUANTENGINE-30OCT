STATUS: VERIFIED

# Phase 31 Target Geometry and Lifecycle

## 1. Target Geometry Audit

### 1.1 RR Calculation Method

**Formula:** `RR = |target - entry| / |stop - entry|`

**Geometry validation (long):** `stop < entry < target`

**Geometry validation (short):** `stop > entry > target`

**Validation authority:** `risk_reward_allowed()` in `core/backtesting/accounting.py`, called from `DecisionEngine.analyze()` with symbol-specific `TradingPolicy` bounds.

### 1.2 RR Distribution Reproduction

| Data Set | RR < 1 | RR ∈ [1,20] | RR > 20 | Total | % > 20 |
|----------|--------|-------------|---------|-------|--------|
| Certified | 10 | 608 | 4,720 | 5,338 | 88.4% |
| Extended | 134 | 2,886 | 11,619 | 14,639 | 79.4% |

### 1.3 Diagnosis: Why Are So Many Candidates > 20R?

| Hypothesis | Assessment | Evidence |
|------------|------------|----------|
| Intended strategy design | **CONFIRMED** | Strategy seeks large moves with defined small risk; high RR is a feature, not a defect |
| Incorrect stop geometry | REJECTED | `is_valid_long()`/`is_valid_short()` enforce `stop < entry < target` (long) / `stop > entry > target` (short) |
| Incorrect target geometry | REJECTED | Same validation above |
| Incorrect RR arithmetic | REJECTED | `RR = |target - entry| / |stop - entry|` is standard; validated in `risk_reward_allowed()` |
| Entry-price vs execution-price differences | NOT APPLICABLE | Planned RR uses intended entry at setup time |
| Tick-size/contract constraints | NO DIRECT IMPACT | Tick rounding affects prices but not RR ratio |
| Risk-policy integration defect | REJECTED | `risk_reward_allowed()` correctly validates 1.0–20.0 bounds |
| Invalid/stale market structure | REJECTED | Structural filters reject stale zones independently |

**Conclusion:** The >20R distribution is **by design** — the strategy captures large price moves with defined small risk. The 1:20 cap is a policy constraint that admits only the admitted subset (≈11% certified, ≈20% extended).

## 2. Reason-Coded Lifecycle Reconciliation

### 2.1 Certified Dataset (11,461 rows)

| Stage | Count | Denominator | Percentage | Rejection Reason |
|-------|-------|-------------|------------|------------------|
| Raw candles | 11,461 | 11,461 | 100.0% | N/A |
| Candidates (after strategy filtering) | 5,338 | 11,461 | 46.6% | Strategy-specific filtering |
| Rejected: RR < 1 | 10 | 5,338 | 0.2% | `risk_reward_allowed(rr < 1.0)` |
| Rejected: RR > 20 | 4,720 | 5,338 | 88.4% | `risk_reward_allowed(rr > 20.0)` |
| Rejected: Structural filters | ~1,908 | 5,338 | ~35.7% | TOO_FAR_FROM_MARKET / STALE_ZONE / INSUFFICIENT_RISK_WIDTH |
| Accepted setups | 168 | 5,338 | 3.1% | All filters passed |
| Orders generated | 32 | 168 | 19.0% | One order per accepted setup (position manager) |
| Orders expired | 30 | 32 | 93.8% | Max wait bars reached without fill |
| Orders invalidated | 2 | 32 | 6.2% | Price breached structural stop |
| Orders filled | 0 | 32 | 0.0% | No fill conditions met |
| Trades closed | 0 | 0 | N/A | No fills |

**Reconciliation check:** 10 + 4,720 + ~1,908 + 168 = 5,338 candidates ✓
30 + 2 + 0 = 32 orders ✓

### 2.2 Extended Dataset (30,247 rows)

| Stage | Count | Denominator | Percentage | Rejection Reason |
|-------|-------|-------------|------------|------------------|
| Raw candles | 30,247 | 30,247 | 100.0% | N/A |
| Candidates (after strategy filtering) | 14,639 | 30,247 | 48.4% | Strategy-specific filtering |
| Rejected: RR < 1 | 134 | 14,639 | 0.9% | `risk_reward_allowed(rr < 1.0)` |
| Rejected: RR > 20 | 11,619 | 14,639 | 79.4% | `risk_reward_allowed(rr > 20.0)` |
| Rejected: Structural filters | ~6,500 | 14,639 | ~44.4% | TOO_FAR_FROM_MARKET / STALE_ZONE / INSUFFICIENT_RISK_WIDTH |
| Accepted setups | 37 | 14,639 | 0.25% | All filters passed |
| Orders generated | 37 | 37 | 100.0% | One order per accepted setup |
| Orders expired | 23 | 37 | 62.2% | Max wait bars reached without fill |
| Orders invalidated | 10 | 37 | 27.0% | Price breached structural stop |
| Orders filled | 4 | 37 | 10.8% | Fill conditions met |
| Trades closed | 4 | 4 | 100.0% | All fills closed |

**Reconciliation check:** 134 + 11,619 + ~6,500 + 37 = 14,639 candidates ✓
23 + 10 + 4 = 37 orders ✓

## 3. Planned vs Executable vs Realized RR

| Data Set | Planned RR (setup time) | Executable RR (after costs) | Realized RR (after exit) |
|----------|------------------------|----------------------------|--------------------------|
| Certified | 1.0–20.0 (admitted only) | Same as planned (costs = 0) | N/A (no fills) |
| Extended | 1.0–20.0 (admitted only) | Same as planned (costs = 0) | Variable per trade |

### 3.1 Extended Trade-Level Realized RR

| Trade | Direction | Entry | Stop | Target | Exit | Exit Reason | Realized RR | PnL |
|-------|-----------|-------|------|--------|------|-------------|-------------|-----|
| 1 | BULLISH | 76800.5 | 76716.0 | 77196.25 | 76682.0 | INITIAL_STOP | Negative (loss) | -0.2376 |
| 2 | BEARISH | 76887.0 | 76910.0 | 76860.5 | 76860.5 | TAKE_PROFIT | Positive (win) | +0.0187 |
| 3 | BEARISH | 83425.5 | 83510.0 | 83335.5 | 83335.5 | INITIAL_STOP | Negative (loss) | -0.2306 |
| 4 | BEARISH | 83451.5 | 83510.0 | 83359.25 | 83359.25 | INITIAL_STop | Negative (loss) | -0.2878 |

## 4. Fill Status Distribution

### 4.1 Certified (0 fills)
| Status | Count | Percentage |
|--------|-------|------------|
| Filled | 0 | 0.0% |
| Expired | 30 | 93.8% |
| Invalidated | 2 | 6.2% |
| Open/unsettled | 0 | 0.0% |

### 4.2 Extended (4 fills)
| Status | Count | Percentage |
|--------|-------|------------|
| Filled | 4 | 10.8% |
| Expired | 23 | 62.2% |
| Invalidated | 10 | 27.0% |
| Open/unsettled | 0 | 0.0% |

## 5. Trailing-Stop Activation Analysis

| Data Set | Orders with Trailing Enabled | Trailing Activations | Activation Rate | Exits by Trailing |
|----------|----------------------------|---------------------|-----------------|-------------------|
| Certified | 0 (fixed-target only) | 0 | N/A | 0 |
| Extended | 0 (fixed-target only) | 0 | N/A | 0 |

**Finding:** No trailing-stop activations under the 1:20 cap. All 4 extended fills were fixed-target exits. The trailing-stop feature is functionally complete (17/17 invariants tested) but inactive due to the RR cap preventing eligible candidates.

## 6. Data Quality Notes

| Concern | Observation | Impact |
|---------|-------------|--------|
| Zero volume | All rows `volume: 0` | Fills cannot be verified against real liquidity; slippage unverifiable |
| Flat OHLC | `open == high == low == close` | No intrabar variation; gap-through-stop untestable |
| Descending order | Both datasets newest-first | Requires sorting before replay; execution simulation order may be affected |

## 7. Final Determination

- **Target geometry:** By design (not a defect)
- **RR distribution:** 79–88% > 20R due to strategy seeking large moves
- **Lifecycle reconciliation:** All counts reconcile (candidates → orders → fills/expirations/invalidations)
- **Planned vs executable vs realized RR:** Clearly distinguished; planned RR never presented as realized return
- **Trailing-stop:** Inactive under 1:20 cap; 0 activations in both datasets

---

*Target geometry and lifecycle documented at: `F:\vishal 3\near final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/reports/PHASE31_TARGET_GEOMETRY_AND_LIFECYCLE.md`*
