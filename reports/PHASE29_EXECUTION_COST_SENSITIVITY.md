STATUS: PLANNED

# Phase 29 Execution Cost Sensitivity

## Objective
Document sensitivity of strategy results to execution costs (commission, slippage, funding) under the active 1:1–1:20 RR policy.

## 1. Baseline Cost Assumptions

| Cost Component | Value | Description |
|--------------|-------|-------------|
| Commission per trade | 0.0 | Fixed-quantity legacy path; no per-trade charge |
| Slippage per trade | 0.0 | Fills exact at intent entry; 0.0 bps |
| Funding schedule | Phase 26 repair (529 hourly events, 2026-09-05 to 2026-09-27) | Integrated via `funding_schedule.cost()` |
| All costs labelled | `CONFIGURED_SIMULATION` | Venue-observed costs are unknown; these are simulated values |

## 2. Cost Sensitivity Analysis (Planned)

| Cost Scenario | Commission | Slippage | Expected Effect on Net PnL | Effect on Fill Counts |
|---------------|------------|----------|----------------------------|------------------------|
| **C1: Baseline** | 0.0 | 0.0 | Net PnL as reported (e.g., –0.7372 extended) | No change |
| **C2: Moderate** | 0.5 per trade | 2.0 bps per trade | Net PnL decreases by ~(0.5×N_trades + 0.02×PnL_notional) | No change |
| **C3: High** | 1.0 per trade | 5.0 bps per trade | Net PnL decreases further; may erode small-positive PnL scenarios | No change |
| **C4: Realistic venue** | UNKNOWN (documented) | UNKNOWN | Marked `CONFIGURED_SIMULATION`; cannot claim without venue data | No change |

## 2.1 Why Costs Affect PnL But Not Fill Counts

- **Fill counts** are determined by: RR validation, structural filters (TOO_FAR, STALE_ZONE, etc.), and order execution logic
- **Costs** affect the *net* PnL after a trade is filled, but they do not change whether a trade is filled or exited
- **Exception:** Very high commissions could theoretically cause `risk_reward_allowed()` to reject a trade, but at the baseline commission of 0.0, this is not a factor

## 2.2 Documented Sensitivity Scenarios

### Scenario 1: Commission + Slippage Increase
- **Setup:** Commission = 0.5 per trade, Slippage = 2.0 bps
- **Effect:** Net PnL decreases by approximately (0.5 × number_of_filled_trades) + slippage contribution
- **Fill counts:** Unchanged (0 certified fills; 4 extended fills remain)
- **Conclusion:** Costs shift PnL but do not change the edge assessment

### Scenario 2: High Commission + Slippage
- **Setup:** Commission = 1.0 per trade, Slippage = 5.0 bps
- **Effect:** Net PnL significantly eroded; may turn small-positive PnL into negative
- **Fill counts:** Unchanged
- **Conclusion:** Confirms that the strategy's edge (if any) is small and cost-sensitive

### Scenario 3: Realistic Venue Fees
- **Setup:** Fees per venue schedule (UNKNOWN)
- **Effect:** Marked `CONFIGURED_SIMULATION`; cannot claim edge without venue data
- **Fill counts:** Unchanged
- **Conclusion:** Requires venue-specific data; not available in current repository

## 2.3 Sensitivity to Trailing Stop with Cost Variation

| Cost Scenario | Trailing Activations | Net PnL (extended) | Effect on Verdict |
|---------------|---------------------|--------------------|-------------------|
| C1 (baseline) | 0 | –0.7372 | `EDGE NOT ESTABLISHED` |
| C2 (moderate) | 0 | –0.7372 – (0.5×4 + slippage) | `EDGE NOT ESTABLISHED` (costs reduce PnL but don't change fill counts) |
| C3 (high) | 0 | –0.7372 – (1.0×4 + slippage) | `EDGE NOT ESTABLISHED` (same verdict, worse PnL) |

**Conclusion:** Cost variation does not change the trailing-stop activation count (0) or the edge verdict, because trailing stops never activate under the 1:20 cap.

## 2.4 Sensitivity to Trailing Parameters (Hypothetical)

| Parameter | Value | Expected Effect | Verdict |
|-----------|-------|-----------------|---------|
| `trailing_activation_r` | 1.0 (baseline) | 0 activations (RR cap) | `EDGE NOT ESTABLISHED` |
| `trailing_activation_r` | 0.5 (tighter) | 0 activations (still >20R targets) | `EDGE NOT ESTABLISHED` |
| `trailing_activation_r` | 2.0 (looser) | 0 activations (fewer eligible) | `EDGE NOT ESTABLISHED` |
| `trailing_distance_r` | 0.5 (baseline) | 0 activations | `EDGE NOT ESTABLISHED` |
| `trailing_distance_r` | 0.0 (no trail) | 0 activations | `EDGE NOT ESTABLISHED` |

**Conclusion:** Under the 1:1–1:20 policy and the current strategy's target geometry, trailing-stop parameters have no effect on activations because the RR cap prevents eligibility.

## 2.4 Recommendations

- Run the sensitivity analysis with actual venue data when available
- Document all cost assumptions as `CONFIGURED_SIMULATION`
- Do not claim edge improvement from cost changes alone
- Maintain baseline (C1) for all reproducibility and comparison purposes

---

*Execution cost sensitivity documented at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*