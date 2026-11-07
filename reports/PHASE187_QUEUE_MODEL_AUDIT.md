# QuantEngine Phase 187: Maker Queue Model Audit & Identifiability Analysis

**Audit Version**: `1.0.0-phase187`  
**Date**: `2026-10-21`  
**System Status**: `NOT_PRODUCTION_READY` | **Strategy Status**: `EDGE NOT ESTABLISHED`  
**Model Calibration Verdict**: `UNCALIBRATED / PARTIALLY_OBSERVABLE`  

---

## 1. Executive Summary

This audit performs an independent, rigorous quantitative examination of QuantEngine's maker execution and queue-depletion models implemented in:
- `core/paper_trading/queue_aware_paper_engine.py`
- `core/execution/maker_execution_model.py`
- `core/research/queue_dynamics.py`

### Definitive Scientific Finding
**Passive Level 2 (L2) order-book depth updates alone do not and cannot prove that a hypothetical maker order would have filled.**

In the absence of authentic order-level fill labels from the exchange matching engine (private WebSocket / authenticated execution stream), individual queue priority ($\theta \in [0, 1]$) and cancellation depletion ahead ($c \in [0, 1]$) are **mathematically unidentifiable**. Any model claiming empirical calibration from passive depth updates alone commits a fundamental attribution fallacy.

The maker execution model is therefore formally classified as **`UNCALIBRATED / PARTIALLY_OBSERVABLE`**. Conservative defaults and sensitivity bounds must govern all risk assessments.

---

## 2. Taxonomy of Market-Data Observations vs. Model Assumptions

To ensure complete scientific integrity, all components of the execution pipeline are categorized into empirical facts versus simulated assumptions:

| Component | Source / Mechanism | Scientific Classification | Status in Phase 187 |
| :--- | :--- | :--- | :--- |
| **Top-of-Book Best Bid / Ask** | Exchange L2 `ob_updates` (`b[0]`, `a[0]`) | **Observed L2 Market Fact** | Empirically Verified (100% valid coverage) |
| **Displayed Depth ($S(p, t)$)** | Exchange L2 `ob_updates` | **Observed L2 Market Fact** | Empirically Verified |
| **Bid/Ask Spread ($\text{USD}$)** | Computed: $best\_ask - best\_bid$ | **Observed Derived Fact** | Empirically Measured ($4.00 BTC, $0.05 ETH) |
| **Public Trade Prints ($V_{trade}$)** | Exchange `all_trades` stream | **Observed Venue Fact** | Partially Observed (sparse on Testnet) |
| **Order Submission Timestamp ($t_0$)** | Local Monotonic Clock (`now_mono_ns`) | **Deterministic System Fact** | Empirically Recorded |
| **Limit Price Grid Alignment** | `normalize_price_to_tick()` | **Deterministic Model Rule** | Verified against product metadata |
| **Post-Only Non-Crossing Guard** | `validate_post_only()` | **Deterministic Model Guard** | Verified (rejects crossed limit prices) |
| **Hypothetical Queue Position ($\theta$)** | Hardcoded or arbitrary ratio in $[0, 1]$ | **Uncalibrated Assumption** | **UNIDENTIFIABLE** from passive L2 |
| **Cancellations Ahead ($C_{ahead}$)** | Hardcoded heuristic ($0\%$, $50\%$, $100\%$) | **Uncalibrated Assumption** | **UNIDENTIFIABLE** from passive L2 |
| **Simulated Queue Depletion** | $Q_{eff} = V_{trade} + (c \times C_{depth})$ | **Simulation Heuristic** | **UNCALIBRATED MODEL** |
| **Simulated Fills** | Paper engine state transition to `FILLED` | **Synthetic Simulation Outcome** | Zero venue writes; not genuine fills |
| **Exchange Order-Level Fills** | Authenticated venue execution log | **Empirical Ground Truth** | **NONE** in Phase 186/187 (0 venue writes) |

---

## 3. Mathematical Proof of Parameter Underdetermination

Let an order be placed at price $p$ at time $t_0$.
The initial displayed depth at price level $p$ is $S(p, t_0)$.
The incoming hypothetical order is placed at an unobserved queue position:
$$Q_{ahead}(t_0) = \theta \cdot S(p, t_0), \quad \theta \in [0, 1]$$

Between time $t_0$ and $t_0 + \Delta t$, the displayed depth changes from $S(p, t_0)$ to $S(p, t_0 + \Delta t)$.
The net observable change is:
$$\Delta S(p, \Delta t) = S(p, t_0 + \Delta t) - S(p, t_0)$$

From market microstructure fundamentals, depth changes are governed by:
$$\Delta S(p, \Delta t) = A_{new}(p, \Delta t) - V_{trades}(p, \Delta t) - C_{total}(p, \Delta t)$$
where:
- $A_{new}$: New orders joining price level $p$.
- $V_{trades}$: Trade executions consuming liquidity at price level $p$.
- $C_{total}$: Order cancellations at price level $p$.

Furthermore, cancellations are split into those ahead of our hypothetical order versus those behind our order:
$$C_{total}(p, \Delta t) = C_{ahead}(\Delta t) + C_{behind}(\Delta t)$$

For our hypothetical order to fill at time $t_f \le t_0 + \Delta t$, the cumulative depletion ahead must exceed the initial queue ahead:
$$\int_{t_0}^{t_f} V_{trade, aggressor}(p, \tau) d\tau + C_{ahead}(t_f - t_0) \ge Q_{ahead}(t_0)$$

### The Underdetermination Invariant:
1. Passive L2 updates report only aggregate depth $S(p, t)$. They do NOT distinguish whether a reduction in depth was caused by trade executions ($V_{trades}$) or cancellations ($C_{total}$).
2. Even if public trades $V_{trades}$ are fully observed, passive L2 updates cannot decompose $C_{total}$ into $C_{ahead}$ versus $C_{behind}$.
3. Most critically, **the true queue priority $\theta$ is completely unknown** without the exchange matching engine's internal order book queue.
4. Hence, the parameter pair $(\theta, c_{cancellation})$ has infinitely many degenerate solutions that produce the exact same observable $\Delta S(p, \Delta t)$.

**Conclusion**: Any algorithm claiming to estimate fill probability solely from passive L2 depth without order-level execution labels cannot identify the true parameters. Claims of empirical queue calibration without authentic venue fills are mathematically invalid.

---

## 4. Audit of Existing Model Equations in Codebase

### 4.1 `core/paper_trading/queue_aware_paper_engine.py`
The engine implements three execution scenarios:
- **`CONSERVATIVE`**:
  $$Q_{depletion} = V_{trade} \quad (c = 0.0)$$
  *Assumes zero credit for cancellations. Fill requires trade volume to completely deplete initial queue ahead.*
- **`CENTRAL`**:
  $$Q_{depletion} = V_{trade} + (0.50 \times \Delta C_{depth}) \quad (c = 0.5)$$
  *Heuristic assumption: 50% of depth reductions are cancellations ahead of our order.*
- **`OPTIMISTIC`**:
  $$Q_{depletion} = V_{trade} + \Delta C_{depth} \quad (c = 1.0)$$
  *Immediate fill on price touch or total depth reduction.*

### 4.2 `core/research/queue_dynamics.py`
Evaluates Poisson arrival intensity $\lambda = \frac{V_{rate} \times H}{Q_{ahead} + \text{size}}$:
$$P(\text{Fill}) = 1 - e^{-\lambda}$$
- If $Q_{ahead} = 0$, $P(\text{Fill}) = 1.0$ (immediate fill assumption).
- Adverse selection drag:
  $$\text{Cost}_{USD} = \text{Notional} \times \frac{\delta_{bps}}{10,000}$$
  *Default drag: $\delta = 2.0\text{ bps}$.*

---

## 5. Sensitivity Bounds Across Uncalibrated Parameters

Because $\theta$ and $c$ cannot be calibrated from passive data, we define rigorous bounding intervals:

| Parameter | Conservative Bound | Central Baseline | Optimistic Bound |
| :--- | :---: | :---: | :---: |
| **Queue Position ($\theta$)** | `0.90` (Tail of Queue) | `0.50` (Mid-Queue) | `0.10` (Front of Queue) |
| **Cancellation Credit ($c$)** | `0.00` (Zero Credit) | `0.50` (50% Depletion) | `1.00` (Full Depletion) |
| **Adverse Selection ($\delta$)** | `5.0 bps` | `2.0 bps` | `1.0 bps` |

---

## 6. Required Evidence for Future Calibration Gate

To transition this model from `UNCALIBRATED` to `EMPIRICALLY_CALIBRATED`, the following conditions must be met:
1. **Authenticated Private WebSocket Capture**: Record `v2/user_trades` and `orders` frames with matching engine timestamps.
2. **Order-Level Fill Timing**: Measure the exact duration $\Delta t = t_{fill} - t_{place}$ for live resting limit orders.
3. **Chronological Holdout Validation**: Calibrate $\theta$ on historical session $T_1$ and achieve out-of-sample prediction accuracy within $\pm 10\%$ on holdout session $T_2$.
4. **Separately Authorized Testnet Experiment**: Execution of live orders must be authorized by an explicit, standalone governance mandate.
