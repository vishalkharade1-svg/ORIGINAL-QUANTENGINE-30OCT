# QuantEngine Phase 162 Research, Machine Learning, and Multi-Instrument Validation

## Executive Summary
This document audits the quantitative research methodology, out-of-sample (OOS) validation protocols, machine learning guardrails, and multi-instrument portfolio isolation in QuantEngine Phase 162.

---

## Statistical Rigor and Bias Prevention

### 1. Lookahead Bias & Candle Timing
- **Rigid Bar Closure**: Features, indicators, and market structure states are computed exclusively using completed, finalized bars (`is_final=True`).
- **Entry Bar Timing**: Order execution occurs strictly on or after the bar following the signal trigger bar. Immediate same-bar execution is forbidden in simulation to prevent lookahead leakage.

### 2. Selection Bias and Multiple Testing
- **Hypothesis Family Freezing**: The hypothesis space (tested parameter combinations, indicator thresholds) is frozen prior to evaluation. Post-hoc parameter tuning is prohibited.
- **Familywise Error Rate Control**: Multiple testing adjustments (e.g. Bonferroni, Holm, False Discovery Rate) are enforced across ablation studies in `research/phase11f/`.
- **Censored / Open Trades**: Trades open at the end of backtest windows are recorded as open/unrealized rather than marked as artificial wins or omitted from metrics.

### 3. Temporal Splitting, Purging, and Embargoing
- **Chronological Walk-Forward**: Folds are split strictly by chronological time blocks without random shuffling.
- **Purging & Embargo**: Purging removes training samples whose trade holding periods overlap with test fold boundaries. Embargoing adds a buffer period after test periods to eliminate serial correlation leakage.

---

## Machine Learning Integration Boundary

### Current ML Status
- Machine learning models in the repository (`research/`, `research/phase11e/`, `research/phase11f/`) are **purely exploratory research artifacts**.
- **No Direct Runtime Integration**: Active runtime code (`core/`) contains no direct dependencies on trained ML model weights or scikit-learn pipelines.
- **Advisory Pre-requisite**: If an ML model is introduced to runtime in a future phase, it can act strictly as an advisory feature score (e.g., probability of continuation) fed into the deterministic `DecisionEngine`. It cannot bypass risk limits, sizing bounds, or protective bracket orders.

---

## Multi-Instrument Portfolio Isolation

### State & Ledger Segregation
- Each instrument maintains an isolated `InstrumentState`, order book cache, and position ledger.
- A feed failure, WebSocket reconnect, or gap on one symbol (e.g. `ETHUSD`) cannot corrupt, block, or delay processing on another symbol (e.g. `BTCUSD`).

### Contract Eligibility Gates
- Although Delta Exchange lists dozens of perpetual contracts, QuantEngine does **NOT** enable trading across arbitrary products automatically.
- **Eligibility Requirement**: An instrument is eligible for execution only when:
  1. Its tick size, step size, and multiplier are verified via official venue specification.
  2. Its fee schedule and funding cadence are modeled.
  3. Its market data feed passes continuity and liquidity depth checks.
- Currently, only `BTCUSD` and `ETHUSD` have empirical verification. All other instruments remain disabled for execution.

---

## Conclusion and Edge Verdict
- Quantitative research protocols in QuantEngine adhere to strict statistical safeguards against lookahead, data snooping, and leakage.
- **Authoritative Verdict**: While engineering and simulation pipelines are verified, empirical trading edge remains **EDGE NOT ESTABLISHED**. Live trading remains strictly disabled.
