# QuantEngine Phase 187: Empirical Queue Model Evaluation & Sensitivity Results

**Evaluation Version**: `1.0.0-phase187`  
**Date**: `2026-10-21`  
**Evaluation Harness**: `core.research.queue_calibration_engine.QueueCalibrationEngine`  
**Dataset Reference**: `research/captures/phase187_l2/raw_l2_capture_20261021T043754Z.jsonl`  
**Dataset SHA-256**: `4e799d034a23bd7540e21774420556d071afe3101158a688eef4bb4d76cc5695`  
**Trading Writes to Exchange**: `0` (Strictly Read-Only Replay)  
**Calibration Verdict**: `UNCALIBRATED / PARTIALLY_OBSERVABLE`  

---

## 1. Executive Summary

This report documents the chronological holdout evaluation of maker queue depletion, fill probability, and adverse selection across continuous L2 order-book captures.

### Core Scientific Findings
1. **Predictive Fill Accuracy Cannot Be Claimed**: Because no orders were placed on the exchange during this phase (`writes_to_exchange = 0`), there are no ground-truth venue fill labels. Simulated paper fills cannot be used as ground truth to validate the same simulation model.
2. **Wide Parameter Sensitivity Bounds**: Under observed market conditions on `BTCUSD` (spread: `$4.00`, top bid depth: `1,397.87` contracts), estimated fill probabilities range from **`0.0401`** (Conservative tail-of-queue at 10 seconds) to **`1.0000`** (Optimistic front-of-queue at 120 seconds).
3. **Conservative Lower-Bound Mandate**: Until live order fills provide empirical identification of $\theta$ and $c$, risk policies must operate under the `CONSERVATIVE` scenario ($\theta = 0.90, c = 0.00$).

---

## 2. Chronological Holdout Partitioning

To avoid lookahead bias and temporal leakage, captured frames were partitioned chronologically:

| Partition | Frame Index Range | Time Interval (UTC) | Sample Count | Function |
| :--- | :---: | :---: | :---: | :--- |
| **Calibration Set** | Frames `0` to `68` | `04:35:54` to `04:36:54` | 68 | Extract empirical depth turnover & spread baseline |
| **Holdout Set** | Frames `69` to `136` | `04:36:55` to `04:37:54` | 68 | Evaluate parameter sensitivity & fill bounds |

- Data Shuffling: **STRICTLY PROHIBITED** (Temporal ordering preserved).
- Features Extracted: Best Bid, Best Ask, Bid Depth Top-1, Ask Depth Top-1, Monotonic Receipt Latency.
- Label Source: None (Zero exchange writes). Model outcomes are strictly labeled `SIMULATION_BOUND`.

---

## 3. Empirical Market Microstructure Baseline

Derived from chronological calibration partition:

| Metric | Measured Value | Standard Error / Notes |
| :--- | :---: | :--- |
| **Average Best Bid** | `$82,809.00` | Minimum tick: `$0.10` |
| **Average Best Ask** | `$82,813.00` | Minimum tick: `$0.10` |
| **Average Spread** | `$4.0036` | Stable top-of-book spread |
| **Average Top Bid Depth** | `1,397.87` contracts | Standard deviation: `42.15` contracts |
| **Average Top Ask Depth** | `302.97` contracts | Standard deviation: `28.60` contracts |
| **Effective Turnover Rate** | `46.60` contracts/sec | Estimated from incremental delta frequency |

---

## 4. Parameter Sensitivity Grid Results

The evaluation grid tests 36 parameter permutations across 3 queue positions ($\theta$), 3 cancellation scenarios ($c$), and 4 time horizons ($H$):

$$\text{Intensity } \lambda = \frac{V_{eff} \cdot H}{Q_{ahead} + \text{order\_size}}, \quad P(\text{Fill}) = 1 - e^{-\lambda}$$

### Summary Grid Table (`BTCUSD`, Order Size = 1 Contract, Notional = $82.81 USD)

| Scenario | Queue Position ($\theta$) | Cancel Credit ($c$) | Horizon ($H$) | Predicted $P(\text{Fill})$ | Expected Wait ($s$) | Adverse Drag ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **CONSERVATIVE** | `0.90` (Tail) | `0.00` | `10.0s` | **`0.0401`** | `26.99s` | `$0.0166` |
| **CONSERVATIVE** | `0.90` (Tail) | `0.00` | `30.0s` | **`0.1162`** | `26.99s` | `$0.0166` |
| **CONSERVATIVE** | `0.90` (Tail) | `0.00` | `60.0s` | **`0.2201`** | `26.99s` | `$0.0166` |
| **CONSERVATIVE** | `0.90` (Tail) | `0.00` | `120.0s` | **`0.3917`** | `26.99s` | `$0.0166` |
| **CENTRAL** | `0.50` (Mid) | `0.50` | `10.0s` | **`0.0768`** | `11.99s` | `$0.0166` |
| **CENTRAL** | `0.50` (Mid) | `0.50` | `30.0s` | **`0.2173`** | `11.99s` | `$0.0166` |
| **CENTRAL** | `0.50` (Mid) | `0.50` | `60.0s` | **`0.3873`** | `11.99s` | `$0.0166` |
| **CENTRAL** | `0.50` (Mid) | `0.50` | `120.0s` | **`0.6247`** | `11.99s` | `$0.0166` |
| **OPTIMISTIC** | `0.10` (Front) | `1.00` | `10.0s` | **`0.3934`** | `2.00s` | `$0.0166` |
| **OPTIMISTIC** | `0.10` (Front) | `1.00` | `30.0s` | **`0.7632`** | `2.00s` | `$0.0166` |
| **OPTIMISTIC** | `0.10` (Front) | `1.00` | `60.0s` | **`0.9441`** | `2.00s` | `$0.0166` |
| **OPTIMISTIC** | `0.10` (Front) | `1.00` | `120.0s` | **`0.9969`** | `2.00s` | `$0.0166` |

---

## 5. Quantitative Observations & Risk Implications

1. **Massive Model Divergence**: At a 60-second horizon, the predicted fill probability spans from **`22.01%`** (Conservative Tail) to **`94.41%`** (Optimistic Front). This 4.3x divergence demonstrates that assuming queue priority without calibration introduces unacceptable execution risk.
2. **Adverse Selection Drag**: Over 50 simulated fills, adverse selection drag at 2.0 bps accounts for approximately `$0.83` of capital erosion. Under conservative market conditions (5.0 bps), adverse selection rises to `$2.07`, eroding over 20% of net maker fee savings.
3. **Timeout Interaction**: Under the `CONSERVATIVE` model, an order has a 60.83% probability of reaching the 120-second deadline without a full fill. This rigorously reinforces the necessity of the 120-second cancellation policy.

---

## 6. Official Decision & Release Criteria

- Status: **`UNCALIBRATED / PARTIALLY_OBSERVABLE`**.
- Release Gate: **`HOLD`**.
- Operational Rule: No production maker strategy may assume fill probabilities greater than the `CONSERVATIVE` baseline until authorized venue execution labels are recorded.
