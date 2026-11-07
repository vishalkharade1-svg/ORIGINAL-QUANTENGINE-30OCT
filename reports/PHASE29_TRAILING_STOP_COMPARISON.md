STATUS: VERIFIED

# Phase 29 Trailing-Stop Comparison

## Comparison Objective

Compare fixed-target exits versus trailing-stop exits under the active 1:1–1:20 RR policy, using identical data, entry logic, costs, and execution assumptions.

## 1. Baseline Configuration

| Parameter | Value |
|-----------|-------|
| RR range | 1:1 – 1:20 (TRADING_MIN_RISK_REWARD = 1.0, TRADING_MAX_RISK_REWARD = 20.0) |
| Trailing stop | Disabled (baseline C1); Enabled C2 (`R_DISTANCE`, activation=1R, distance=0.5R) |
| Commission | 0.0 per trade |
| Slippage | 0.0 per trade |
| Funding | Phase 26 schedule (529 hourly events) |
| Data | Certified (`phase17_fresh`) + Extended (`oos_topup`) |
| Entry logic | Strategy-generated SetupCandidate objects |
| Execution model | TradeSimulator with fixed-target logic; trailing-stop logic identical except for exit trigger |

## 2. Results: Fixed-Target Only (C1)

### Certified Data
- Candidates: 5,338
- Orders generated: 32
- Filled orders: 0
- Expirations: 30
- Invalidations: 2
- Trailing-stop activations: N/A (disabled)
- Net PnL: 0 (no fills)

### Extended Data
- Candidates: 14,639
- Orders generated: 37 (23 expired, 10 invalidated, 4 filled)
- Filled orders: 4 (all fixed-target exits)
- Trailing-stop activations: 0
- Net PnL: –0.7372 (conservative gap fill)

## 2.2 Results: With Trailing Stop (C2)

### Certified Data
- Candidates: 5,338
- Orders generated: 32
- Filled orders: 0
- Trailing-stop activations: 0 (1:20 cap leaves ~1 eligible order)
- Net PnL: 0 (no fills; identical to C1)

### Extended Data
- Candidates: 14,639
- Orders generated: 37 (23 expired, 10 invalidated, 4 filled)
- Filled orders: 4 (identical to C1; trailing stop never activates)
- Trailing-stop activations: 0
- Net PnL: –0.7372 (identical to C1)

## 2.3 Comparison Summary

| Metric | C1: Fixed-Target Only | C2: With Trailing Stop | Difference |
|--------|-----------------------|------------------------|------------|
| Certified fills | 0 | 0 | 0 (identical) |
| Extended fills | 4 | 4 | 0 (identical) |
| Trailing activations | N/A | 0 | 0 (trailing never activates) |
| Net PnL (extended) | –0.7372 | –0.7372 | 0 (identical) |
| MFE/MAE | Same data | Identical | — |
| Exit-reason distribution | All INITIAL_STOP/TAKE_PROFIT | Same (trailing never triggers) | — |

## 2.4 Key Findings

1. **Trailing stop has no effect** under the 1:1–1:20 policy because the RR cap prevents activation. The strategy's target geometry produces predominantly >20R planned RRs, and the 1:20 cap admits only a small fraction; those admitted candidates still exit via fixed targets, not trailing stops.

2. **Fixed-target and trailing-stop baselines are identical** in terms of fill counts, PnL, and trade outcomes. The trailing-stop feature is functional (all invariants tested and pass) but inactive for the current strategy under the current policy.

3. **No advantage or disadvantage** to enabling the trailing stop in the current configuration. The verdict remains `EDGE NOT ESTABLISHED` regardless.

## 2.5 When Would Trailing Stop Activate?

Trailing stop activation requires:
- Planned RR ∈ [1, 20] (admitted by the policy)
- Price movement that triggers `trailing_activation_r` (1R)
- Price movement that triggers `trailing_distance_r` (0.5R)
- The strategy must have candidates with RR in the admitted range

**Current state:** The strategy's target geometry produces predominantly >20R planned RRs. Until the strategy or policy changes, trailing stops will remain inactive.

## 2.6 When Would Trailing Stop Activate? (Hypothetical)

If the RR cap were loosened or the strategy's target geometry changed to produce more ≤20R RRs:
- Trailing stop could activate at 1R favourable move
- Stop would trail at 0.5R distance
- Exits could occur via trailing stop instead of fixed target
- Net PnL and fill counts could differ

**But this is hypothetical** — the current policy and strategy do not produce such conditions.

---

*Trailing-stop comparison logged at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*