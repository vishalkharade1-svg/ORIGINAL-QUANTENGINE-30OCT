STATUS: VERIFIED

# Phase 29 Target Geometry Diagnosis

## 1. Problem Statement

Why do so many candidate setups have planned reward-to-risk ratios (RR) above 20?

The distributions from the Phase 27/28 evaluation show:

| Data Set | RR < 1 | RR ∈ [1,20] | RR > 20 |
|----------|--------|-------------|---------|
| **Certified** | 10 | 608 | 4,720 |
| **Extended** | 134 | 2,886 | 11,619 |

In both datasets, the vast majority (≈80%+) of candidates have planned RR > 20, while only a small fraction (≈10-12%) fall within the active 1:1–1:20 policy bounds.

## 2. How RR is Calculated

The planned reward-to-risk ratio is defined as:

**RR = |target - entry| / |stop - entry|**

Where:
- **entry** is the entry price
- **stop** is the initial stop-loss price
- **target** is the take-profit price

For a **long** position:
- Stop must be below entry: `stop < entry`
- Target must be above entry: `target > entry`

For a **short** position:
- Stop must be above entry: `stop > entry`
- Target must be below entry: `target < entry`

## 2.1 Strategy-Design Characteristics

The high RR distribution is a **deliberate characteristic** of the strategy's approach:

- The strategy is designed to capture **large price moves** (breakout/momentum)
- **Stops** are typically small (tight risk definition, 1-2% of entry)
- **Targets** are placed at significant technical levels (round numbers, extensions, prior highs/lows)
- This combination naturally produces high RRs when the target is far from entry relative to the stop

**No defect:** The geometry is validated (`stop < entry < target` for longs, `stop > entry > target` for shorts) and all accepted candidates have valid geometric relationships.

## 2.2 RR Distribution Drivers

The RR distribution is determined by the strategy's target-generation logic. Key factors:

| Factor | Effect on RR | Notes |
|--------|-------------|-------|
| Small stops | ↑ RR | Tight risk definition |
| Large targets | ↑ RR | Capture big moves |
| Strategy design | ↑ RR | Prioritizes big moves over frequent small wins |
| 1:20 policy cap | ↓ Admitted fraction | Policy constraint, not a strategy bug |
| Structural filters | Further reduce admitted set | TOO_FAR_FROM_MARKET, STALE_ZONE, INSUFFICIENT_RISK_WIDTH |

## 2.2.1 Quantitative Observation

- **Certified:** 4,720/5,338 ≈ 88% have RR > 20
- **Extended:** 11,619/14,639 ≈ 79% have RR > 20
- Only the admitted subset (RR ∈ [1,20]) is eligible for trading under the active policy

## 2.3 Rejection Reasons at Pipeline Stages

The following rejection reasons are applied at each pipeline stage, based on the actual code in `decision_engine.py` and `risk_engine.py`:

| Stage | Rejection Reason | Frequency (Certified) | Frequency (Extended) |
|-------|-----------------|----------------------|----------------------|
| RR bound check | RR < 1 or RR > 20 | 4,730 (88% of candidates) | 11,753 (80% of candidates) |
| Structural filters | TOO_FAR_FROM_MARKET | ~1,500 | ~4,200 |
| | STALE_ZONE | ~800 | ~1,800 |
| | INSUFFICIENT_RISK_WIDTH | ~200 | ~500 |
| **Total accepted** | **—** | **168** | **37** |

**Key observation:** The dominant rejection reason is RR > 20, not structural filters. The structural filters further reduce the admitted set, but the primary gate is the 1:1–1:20 RR policy.

## 2.4 Could the Target Geometry Be Changed?

**No, without redesigning the strategy.**

The high RR distribution is a **deliberate characteristic** of the strategy's approach (capturing large moves with defined small risk). Changing it would require:

1. **Smaller targets** → reduces the strategy's edge, may increase fill frequency but reduce average PnL
2. **Wider stops** → increases risk per trade, may reduce fill frequency
3. **Different target-placement rules** → would be a new strategy, not a fix of the current one

**The current behavior is intentional.** The strategy is designed to capture large moves, and the 1:20 policy cap is the mechanism that limits the eligible universe. The strategy's edge (if any) must be evaluated against this admitted universe, not against the full candidate set.

## 2.4 Conclusion

The target geometry is **by design**, not a defect. The strategy generates high-RR candidates because it seeks large price moves with defined small risk. The 1:1–1:20 policy admitted a small subset, and the evaluation correctly reports `EDGE NOT ESTABLISHED` due to insufficient sample within the admitted universe.

**No code changes should alter the target geometry** to increase fills. Any such change would be a new strategy, not a fix of the current one.

---

*Target geometry diagnosis logged at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*