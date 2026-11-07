STATUS: PARTIAL

# Phase 29 Experiment Matrix

## Objective
Compare separately versioned hypotheses for strategy edge research under the active 1:1–1:20 RR policy.

## Experiment Design

Each experiment uses a distinct, recorded configuration. Rules are not mixed into the active production strategy.

### Experiment A: Existing Strategy + Current RR Policy
- **RR range:** 1:1 – 1:20 (active policy)
- **Trailing stop:** Disabled (current baseline)
- **Costs:** Commission=0.0, Slippage=0.0, Funding (Phase 26 schedule)
- **Data:** Certified (`phase17_fresh`) + Extended (`oos_topup`)
- **Hypothesis:** Baseline edge evaluation under current policy
- **Status:** `IMPLEMENTED` / `TESTED` (71 focused tests pass, all trade counts verified)

### Experiment B: Alternative Target-Selection Rules
- **RR range:** 1:1 – 1:20 (same active policy)
- **Target-selection mode:** 
  - Option B1: Reject RR > 20 (current behavior)
  - Option B2: Clamp targets to 20R maximum
  - Option B3: Configurable target-selection mode (new parameter)
- **Trailing stop:** Disabled
- **Costs:** Same as Experiment A
- **Data:** Same datasets
- **Hypothesis:** Different target-selection modes change fill counts and RR distribution
- **Status:** `NOT IMPLEMENTED` — would require strategy code modification; documented as separate hypothesis

### Experiment C: Fixed-Target vs. Trailing-Stop Exits
- **RR range:** 1:1 – 1:20 (active policy)
- **Trailing stop:** 
  - C1: Disabled (fixed-target only)
  - C2: Enabled, `R_DISTANCE`, activation=1R, distance=0.5R
- **Costs:** Same as Experiment A
- **Data:** Same datasets
- **Hypothesis:** Trailing stop may change exit behavior; under 1:20 cap, trailing never activates
- **Status:** `IMPLEMENTED` — tested; 0 trailing activations in both datasets; identical to fixed-target baseline

### Experiment D: Sensitivity to Execution Costs
- **RR range:** 1:1 – 1:20 (active policy)
- **Cost variations:**
  - C1: Commission=0.0, Slippage=0.0 (baseline)
  - C2: Commission=0.5 per trade, Slippage=2.0 bps
  - C3: Commission=1.0, Slippage=5.0 bps
  - C4: Realistic venue fees (documented as UNKNOWN — mark as `CONFIGURED_SIMULATION`)
- **Trailing stop:** Disabled (baseline), then enabled with same parameters
- **Data:** Same datasets
- **Hypothesis:** Costs affect net PnL but not fill counts or RR distributions
- **Status:** `PLANNED` — sensitivity analysis documented; not yet executed

### Experiment E: Sensitivity to Sample Size / Holdout
- **RR range:** 1:1 – 1:20 (active policy)
- **Data splits:**
  - D1: All certified data (5,338 candidates)
  - D2: All extended data (14,639 candidates)
  - D3: Hypothetical holdout (not yet available)
- **Trailing stop:** Disabled
- **Costs:** Baseline (C1)
- **Hypothesis:** Insufficient sample precludes edge claims; larger data may change verdict
- **Status:** `PLANNED` — holdout acquisition protocol documented in `PHASE29_HOLDOUT_PROTOCOL.md`

## Experiment Matrix Summary

| Experiment | RR Policy | Trailing Stop | Cost Variation | Data | Status |
|-----------|-----------|---------------|----------------|------|--------|
| A | 1:1–1:20 | Disabled | Baseline | Both | `IMPLEMENTED` / `TESTED` |
| B | 1:1–1:20 | Disabled | Baseline | Both | `PARTIAL` (hypothesis only) |
| C | 1:1–1:20 | C1/C2 | Baseline | Both | `IMPLEMENTED` (0 trailing activations) |
| D | 1:1–1:20 | Disabled | C1 | Various | `PLANNED` (holdout protocol defined) |

## Constraints & Constraints

- **No silent target clamping:** Any target-selection change must be explicit and documented.
- **No strategy behavior change:** Experiments B–D must not modify the active strategy code.
- **Policy consistency:** All experiments must respect the 1:1–1:20 RR bounds.
- **Documentation:** Each experiment configuration must be recorded in the experiment matrix and the Evidence Ledger.

## Experiment Matrix Status

| Experiment | Status | Next Action |
|-----------|--------|-------------|
| A | `IMPLEMENTED` / `TESTED` | Complete; results verified |
| B | `PARTIAL` | Document as hypothesis; no code changes |
| C | `IMPLEMENTED` | Complete; 0 trailing activations verified |
| D | `PLANNED` | Document holdout protocol; pending data acquisition |

---

*Experiment matrix logged at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*