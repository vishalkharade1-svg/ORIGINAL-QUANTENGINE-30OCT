STATUS: PLANNED

# Phase 29 Holdout Protocol

## 1. Holdout Dataset Status

### Currently Available Datasets
- **Certified** (`BTCUSDT_1m_phase17_fresh.json`): 11,461 rows, used for strategy tuning and the legacy 1:6 OOS run. Label: `DEVELOPMENT_SEEN_DATA`.
- **Extended** (`BTCUSDT_1m_oos_topup.json`): 30,247 rows, out-of-sample extension. Label: `SEEN_EXTENSION`, never used for edge claims without holdout.
- **Holdout:** **NOT AVAILABLE** after Phase 26. No unseen dataset exists that has been kept independent of strategy development and parameter tuning.

### 2. Rationale for No Holdout

- The Phase 26 evaluation used the extended data as an OOS run, but this data was already part of the strategy's development cycle (the strategy was tuned on certified data, and the extended data was added as a top-up).
- No genuinely independent dataset has been generated or acquired post-Phase 26.
- Without a holdout, any edge claim would be vulnerable to selection bias and overfitting.

### 3. Holdout Acquisition Protocol

If the owner decides to acquire a holdout dataset, the following protocol should be followed:

#### Step 1: Data Source Identification
- Identify a new data feed or historical period that is **not** part of the current development set.
- Ensure the data covers a different time range, different market conditions, or a different instrument.
- Document the source, time range, and any known characteristics.

#### Step 2: Data Validation
- Verify the data quality: no missing timestamps, no stale bars, correct OHLC structure.
- Verify the data is not already in the repository (cross-check hashes).
- Compute the dataset SHA-256 hash for provenance.

#### Step 3: Strategy Freeze
- Freeze the current strategy version, configuration, and RR policy (1:1–1:20).
- Record the exact code hash, policy configuration, and dataset hash.
- Do not make any further parameter tuning or strategy modifications after the freeze.

#### Step 4: Evaluation on Holdout
- Run the strategy on the holdout dataset using the frozen configuration.
- Compute the same metrics as the baseline evaluation (RR distributions, fills, PnL, trailing activations).
- Do not tune parameters based on holdout results.

#### Step 5: Provenance and Reporting
- Record the holdout dataset hash, the frozen configuration hash, and the evaluation results.
- Include in the Evidence Ledger (`PHASE29_EVIDENCE_LEDGER.json`).
- Clearly label the results as from an **independent holdout** or note that no holdout was available.

### 4. If No Holdout Is Available

If no holdout dataset can be acquired, the following steps should be taken:

1. **Acknowledge the limitation:** Explicitly state that no independent holdout exists and that previous data has been used for development/tuning.
2. **Use conservative metrics:** Report only metrics that are less susceptible to overfitting (e.g., RR distributions, fill counts) rather than profitability claims.
3. **Prepare for future holdout:** Document the holdout acquisition protocol (above) for future use when new data becomes available.
4. **Maintain the `EDGE NOT ESTABLISHED` / `INSUFFICIENT SAMPLE` verdict** until a holdout is acquired and evaluated.

### 5. Current Verdict

- **No holdout dataset exists.**
- **Verdict:** `EDGE NOT ESTABLISHED` / `INSUFFICIENT SAMPLE`.
- **Next step:** Owner may acquire a holdout dataset; until then, all edge claims are speculative.

---

*Holdout protocol logged at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*