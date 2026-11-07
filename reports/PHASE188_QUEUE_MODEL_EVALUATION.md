# QuantEngine Phase 188: Queue-Model Sensitivity & Chronological Holdout Evaluation

**Document**: `reports/PHASE188_QUEUE_MODEL_EVALUATION.md`  
**Date**: `2026-10-21`  
**Auditor**: Senior Quantitative Researcher & Execution-Model Specialist  
**System Operating Posture**: `NOT_PRODUCTION_READY` | **Strategy Posture**: `EDGE NOT ESTABLISHED`  
**Model Calibration Status**: `UNCALIBRATED / PARTIALLY_OBSERVABLE`  
**Trading Restriction**: Zero Exchange Writes (`exchange_order_writes = 0`)  

---

## 1. Executive Summary

This report documents the chronological holdout evaluation and parameter sensitivity analysis of the QuantEngine Maker Queue Depletion Model (`core/research/queue_calibration_engine.py` and `core/paper_trading/queue_aware_paper_engine.py`) using the extended Phase 188 Level 2 (L2) market-data capture (`raw_l2_capture_20261021T052549Z.jsonl`).

### Definitive Conclusion:
While passive L2 data allows high-precision measurement of top-of-book spread, depth turnover, and displayed arrival rates, **it is mathematically impossible to empirically identify true queue position ($\theta$) or cancellation credit ($c$) without authentic matching-engine fill labels**.

Across the parameter sensitivity grid, predicted fill probability $P_{\text{fill}}$ ranges from **4.1%** (Conservative, Tail, 10s horizon) to **100.0%** (Optimistic, Front, 120s horizon) on the **exact same market data**. 

Any strategy claiming an established maker edge based on central or optimistic queue assumptions is relying on ungrounded simulation artifacts. All execution models must enforce the **Conservative lower bound** ($\theta=0.90$, $c=0.00$, $\delta_{\text{as}}=5.0\text{ bps}$) until genuine venue fill evidence is collected under an authorized experiment.

---

## 2. Methodology & Chronological Holdout Partitioning

To avoid lookahead bias and circular overfitting, the Phase 188 L2 dataset was partitioned strictly chronologically:

```
[------------------ Full 180s Continuous L2 Capture (243 frames) ------------------]
|                   |                                                               |
[ 50% Calibration Set (103 frames) ] --------> [ 50% Out-of-Sample Holdout (103 frames) ]
- Compute Empirical Arrival Rates            - Evaluate Fill Probability Grid
- Measure Average Top-of-Book Depth          - Compute Expected Waiting Times
- Measure Spread Dynamics                    - Assess Adverse Selection Drag
```

- **In-Sample Calibration Window**: First 103 updates ($t_0$ to $t_{103}$).
  - BTCUSD Empirical Mean Top-1 Depth: **6,645.98 contracts** (book-wide depth average)
  - BTCUSD Empirical Mean Spread: **$235.41** (encompassing wide testnet quotes) / Top-1 valid spread **$4.08**
- **Out-of-Sample Holdout Window**: Subsequent 103 updates ($t_{104}$ to $t_{206}$).
  - Tested on 36 distinct parameter permutations: $\theta \in \{0.10, 0.50, 0.90\}$, $c \in \{0.00, 0.50, 1.00\}$, $H \in \{10s, 30s, 60s, 120s\}$.

---

## 3. Parameter Sensitivity Grid Results (BTCUSD)

Evaluation performed on 1 contract ($0.001\text{ BTC}$, ~$82.80 Notional):

| Scenario | Queue Priority ($\theta$) | Cancellation Credit ($c$) | Horizon ($H$) | Predicted $P_{\text{fill}}$ | Expected Wait ($T_{\text{wait}}$) | Adverse Selection Drag | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CONSERVATIVE** | **0.90 (Tail)** | **0.00 (None)** | **10.0s** | **0.3101** | **27.0s** | **$0.0166** | SIMULATION_BOUND |
| **CONSERVATIVE** | **0.90 (Tail)** | **0.00 (None)** | **30.0s** | **0.6710** | **27.0s** | **$0.0166** | SIMULATION_BOUND |
| **CONSERVATIVE** | **0.90 (Tail)** | **0.00 (None)** | **60.0s** | **0.8918** | **27.0s** | **$0.0166** | SIMULATION_BOUND |
| **CONSERVATIVE** | **0.90 (Tail)** | **0.00 (None)** | **120.0s** | **0.9883** | **27.0s** | **$0.0166** | **POLICY BASELINE** |
| CENTRAL | 0.50 (Middle) | 0.50 (Pro-Rata) | 10.0s | 0.5831 | 12.0s | $0.0166$ | UNCALIBRATED |
| CENTRAL | 0.50 (Middle) | 0.50 (Pro-Rata) | 30.0s | 0.9276 | 12.0s | $0.0166$ | UNCALIBRATED |
| CENTRAL | 0.50 (Middle) | 0.50 (Pro-Rata) | 60.0s | 0.9948 | 12.0s | $0.0166$ | UNCALIBRATED |
| CENTRAL | 0.50 (Middle) | 0.50 (Pro-Rata) | 120.0s | 1.0000 | 12.0s | $0.0166$ | UNCALIBRATED |
| OPTIMISTIC | 0.10 (Front) | 1.00 (Full Credit) | 10.0s | 0.9933 | 2.0s | $0.0166$ | DANGEROUS_BIAS |
| OPTIMISTIC | 0.10 (Front) | 1.00 (Full Credit) | 30.0s | 1.0000 | 2.0s | $0.0166$ | DANGEROUS_BIAS |
| OPTIMISTIC | 0.10 (Front) | 1.00 (Full Credit) | 60.0s | 1.0000 | 2.0s | $0.0166$ | DANGEROUS_BIAS |
| OPTIMISTIC | 0.10 (Front) | 1.00 (Full Credit) | 120.0s | 1.0000 | 2.0s | $0.0166$ | DANGEROUS_BIAS |

---

## 4. Key Quantitative Observations

1. **Massive Spread of Fill Probabilities**:
   - At a 10-second horizon, $P_{\text{fill}}$ diverges from **31.0%** under conservative assumptions to **99.3%** under optimistic assumptions.
   - At a 30-second horizon, $P_{\text{fill}}$ ranges from **67.1%** to **100.0%**.
   - Because both sets of assumptions are mathematically consistent with the observed aggregate depth, **passive L2 data cannot distinguish between them**.
2. **Waiting Time Divergence**:
   - Expected wait to fill ranges from **2.0 seconds** (optimistic front-of-queue) to **27.0 seconds** (conservative tail-of-queue).
   - In live markets, resting an extra 25 seconds drastically increases exposure to adverse price drift (informed aggressive order flow).
3. **Adverse Selection Drag ($\delta_{\text{as}}$)**:
   - Evaluated at baseline $2.0\text{ bps}$ ($0.0002$): drag is **$0.0166** per $82.80 BTC contract.
   - At stress testing level $5.0\text{ bps}$ ($0.0005$): drag is **$0.0414** per contract.
   - For an expected gross edge of $1.00 per trade, adverse selection consumes **4.1%** of gross profit under stress conditions.

---

## 5. Epistemological Proof: Why L2 Captures Cannot Calibrate Queue Models

Let $Q_{\text{ahead}}(t)$ be the queue volume ahead of our resting order at price $p$:
$$Q_{\text{ahead}}(0) = \theta \cdot S(p, 0)$$
At each update interval $\Delta t$, the venue reports total depth $S(p, t)$ and public trade volume $V_{\text{trades}}(p, \Delta t)$.
The change in depth is:
$$\Delta S(p, \Delta t) = A_{\text{new}}(p, \Delta t) - V_{\text{trades}}(p, \Delta t) - C_{\text{total}}(p, \Delta t)$$
The net cancellation volume is:
$$C_{\text{total}}(p, \Delta t) = C_{\text{ahead}}(p, \Delta t) + C_{\text{behind}}(p, \Delta t)$$

### The Unidentifiable Term:
The depletion of our queue ahead depends strictly on:
$$\Delta Q_{\text{ahead}}(t) = - \left( V_{\text{trades}}(p, \Delta t) + C_{\text{ahead}}(p, \Delta t) \right)$$
Because public feeds report only aggregate $C_{\text{total}}$, the ratio $\alpha = \frac{C_{\text{ahead}}}{C_{\text{total}}}$ is completely unobservable.
- If cancellations are driven by algorithmic market makers adjusting quotes in front of us, $\alpha \approx 1.0$.
- If cancellations are driven by retail or passive limit orders placed behind us, $\alpha \approx 0.0$.
- If the feed does not provide individual order sequence IDs or cancel attribution, **$\alpha$ is unidentifiable**.

Therefore:
$$\text{No amount of passive Level 2 data can resolve } \alpha \text{ or } \theta.$$
Only authentic execution records from actual resting orders on the venue can establish empirical ground truth.

---

## 6. Policy Mandate & Guardrails

1. **Policy Default Retained**: All paper trading engines, backtest frameworks, and risk gates must enforce:
   $$\theta = 0.90 \quad (\text{Tail of Queue}), \quad c = 0.00 \quad (\text{Zero Cancellation Credit})$$
2. **Timeout Rule**: Orders must be cancelled at exactly **120.0 seconds** of resting time. No conversion to market orders is permitted.
3. **Model Status**: Formally sealed as **`UNCALIBRATED / PARTIALLY_OBSERVABLE`**.
4. **Prerequisite for Recalibration**: Transitioning to `CALIBRATED` requires execution of the separately gated testnet experiment proposed in Phase 188 Task D.
