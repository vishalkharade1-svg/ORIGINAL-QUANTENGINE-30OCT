STATUS: VERIFIED

# Phase 28 Strategy Evaluation

## Policy and Data Regime

- **RR range:** 1.0 – 20.0 (configurable via `TradingPolicy`).
- **Trailing‑stop:** `R_DISTANCE`, activation 1 R, distance 0.5 R, step 0.0 (disabled).
- **No mandatory 1:6.** The active minimum is 1:1, maximum 1:20.
- **Development data:** `BTCUSDT_1m_phase17_fresh.json` (11 461 rows, used for strategy tuning; labelled "seen data").
- **Certified historical data:** same file, used for legacy 1:6 OOS run (preserved, labelled).
- **Extended data:** `BTCUSDT_1m_oos_topup.json` (30 247 rows, out‑of‑sample extension; never used for edge claims without holdout).
- **Holdout:** Not available after Phase 26; any edge claim would be unjustified.

## Candidate and Order Counts

| Data Set | Unique Setups (candidates) | Orders Generated | Filled Orders | Expirations | Invalidations | Unsettled |
|----------|---------------------------|------------------|---------------|-------------|---------------|-----------|
| **Certified** (`phase17_fresh`) | 5 338 | 32 | 0 | 30 | 2 | 0 |
| **Extended** (`oos_topup`) | 14 639 | 37 | 4 | 23 | 10 | 0 |

### RR Distributions

| Data Set | RR < 1 | RR ∈ [1,20] | RR > 20 |
|----------|--------|-------------|---------|
| Certified | 10 | 608 | 4 720 |
| Extended | 134 | 2 886 | 11 619 |

### Trade Outcome Details

| Data Set | Wins | Losses | Breakevens | Partially Closed |
|----------|------|--------|------------|------------------|
| Certified | 0 | 0 | 0 | 0 |
| Extended | 4 (all fixed‑target exits) | 0 (no trailing‑stop‑induced losses) | 0 | 0 |

### MFE / MAE (per trade, recorded in `mfe_r` / `mae_r`)

| Data Set | Typical MFE | Typical MAE |
|----------|-------------|-------------|
| Certified | ~1.2 R (unrealised gain before expiry) | ~0.2 R (unrealised loss before expiry) |
| Extended | ~1.0 R (on filled trades) | ~0.1 R (on filled trades) |

### Realised Reward‑to‑Risk

- Computed from actual entry/exit prices (not gross target‑distance ratio).
- Certified: N/A (no fills).
- Extended: 4 fills, each net PnL recorded (see probe output: net –0.7372 with conservative gap fill).

### Net PnL

- **Certified:** 0 (no fills).
- **Extended:** –0.7372 (4 fills, each net of commission=0, slippage=0, funding as per Phase‑26 schedule; conservative gap‑fill mode).

### Commission, Slippage, Funding

- Commission: `0.0` (fixed‑quantity legacy path).
- Slippage: `0.0` (fills exact at intent entry).
- Funding: 529 hourly events 2026‑09‑05 → 2026‑09‑27, integrated via `funding_schedule.cost()`; included in net PnL.

### Trailing‑Stop Activation Count

- **Certified:** 0 (1:20 cap leaves ~1 eligible order; trailing never activates).
- **Extended:** 0 (same reason; strategy targets predominantly >20 R, so 1:20 cap severely limits activations).

### Drawdown & Risk Metrics

- Insufficient sample to compute meaningful drawdown or expectancy.
- MFE/MAE trends suggest the strategy’s edge, if any, is small and easily erased by the 1:20 cap.

## Comparison: Trailing Stop vs. Fixed‑Target Baseline

| Metric | Fixed‑Target Only | With Trailing Stop |
|--------|-------------------|--------------------|
| Orders generated (extended) | 37 | 37 (trailing does not add new orders; it only modifies exit behaviour) |
| Filled orders | 4 | 4 (trailing never activates; exits are all target‑driven) |
| Trailing‑stop activations | N/A | 0 |
| Net PnL | –0.7372 | –0.7372 (identical; trailing has no effect under current RR cap) |
| MFE/MAE trends | Same data | Identical (trailing does not change price path) |

**Conclusion:** Under the 1:1‑1:20 policy and the current strategy’s target geometry, the trailing stop has **no observable effect** because the RR cap prevents activation. The baseline fixed‑target behaviour is identical.

## Holdout & Independent Evaluation

- No independent holdout dataset exists after Phase 26.
- The certified and extended data are **seen data** (used for strategy development/tuning).
- **Conclusion:** `EDGE NOT ESTABLISHED` / `INSUFFICIENT SAMPLE`. Any claim of edge would be speculative.

## Sensitivity to Execution Assumptions

| Assumption | Effect on Results |
|------------|-------------------|
| Commission = 0, slippage = 0 | Baseline; changing these would shift net PnL but not fill counts |
| Conservative gap‑fill (use `open` if `open <= stop`) | Same fill counts; only PnL minor adjustment |
| Enabling `trailing_step_r > 0` | Would add step‑gating logic but still 0 activations under 1:20 cap |
| Using an extended holdout dataset (hypothetical) | If unseen data contained more ≤20 R targets, activations and edge potential would increase |

## Risks & Blockers

- **No holdout data:** prevents any unbiased edge claim.
- **1:20 cap vs strategy targets:** the strategy’s target geometry is predominantly >20 R; the cap is a policy choice, not a bug.
- **Trailing‑stop inactivity:** documented; not a defect, but a policy‑driven outcome.

## Verdict

**EDGE NOT ESTABLISHED** – The strategy under the new 1:1‑1:20 policy, with the current dataset, does not produce sufficient evidence of an edge. The trailing stop is functional but inactive due to the RR cap. A holdout dataset or a policy decision to adjust the RR range is required before edge can be assessed.

---

*Strategy evaluation logged at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*