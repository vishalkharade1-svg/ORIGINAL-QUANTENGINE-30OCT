# QUANTENGINE PHASE 174 — INDEPENDENT QUEUE MODEL & ADVERSE SELECTION AUDIT

**Audit Date**: 2026-10-20  
**Status**: `SIMULATION_ASSUMPTION | NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Target Module**: `core/research/queue_dynamics.py`  
**Classification**: `SIMULATION_ASSUMPTION` (Aggregated Level-2 order books do not contain Market-by-Order / Level-3 individual queue queue priority)

---

## 1. Executive Summary & Core Formula Audit

In Phase 172 and Phase 173, `core/research/queue_dynamics.py` introduced granular queue metrics for resting limit orders, reporting an **86.47% any-fill probability** and an **86.20% complete-fill probability** under baseline parameters:
- $\lambda = 20 \text{ contracts/sec}$
- $t = 10 \text{ seconds}$
- $Q = 100 \text{ contracts ahead}$
- $S = 1 \text{ contract order size}$

This independent audit rigorously investigates the mathematical foundations, answers all seven operational questions, compares the model against an Erlang queue process, and assesses empirical calibration readiness.

---

## 2. Answers to the Seven Core Queue Questions

### 1. What does $\lambda$ represent: contracts per second, queue-clearing events per second, or a normalized block-arrival rate?
In `queue_dynamics.py`, the input parameter is named `volume_rate_per_sec` ($\lambda$), with units of **contracts per second**. Over horizon $t$, the expected total volume arriving at the price level is $V = \lambda \cdot t$ (for $\lambda = 20, t = 10$, $V = 200$ contracts).
However, inside the exponential formula $P = 1 - \exp(-V / Q)$, the total volume is divided by the queue depth $Q$. Thus, the effective Poisson event rate is $\mu = \lambda / Q$ **queue-clearing blocks per second**.
Therefore, while parameterized in contracts per second, the mathematical formula treats the arrival of a single aggregate block of size $Q$ as a Poisson event.

### 2. What does $Q$ represent: visible depth, estimated quantity ahead, or a model scaling factor?
$Q$ represents the **estimated contract quantity ahead** of our limit order at the specific price level (`queue_depth_ahead`). For complete fill, $Q$ is augmented by our order size $S$, becoming $Q + S$ (e.g., $100 + 1 = 101$). In this formulation, $Q$ serves both as the physical depth ahead and the characteristic scale parameter of the exponential hazard distribution.

### 3. What stochastic process does the formula assume?
The formula assumes that the time until our order fills is governed by an **exponentially distributed block-depletion time**:
$$T_{\text{clear}} \sim \text{Exponential}\left(\text{rate} = \frac{\lambda}{Q}\right)$$
The cumulative distribution function (CDF) for an exponential distribution is:
$$P(T_{\text{clear}} \le t) = 1 - e^{-\frac{\lambda}{Q} t}$$
This assumes a **memoryless, single-server hazard process** where trade volume arrives in a continuous, homogeneous Poisson stream, but queue priority is approximated as a single lumped obstacle rather than discrete individual trade executions.

### 4. What is the exact formula for the reported 86.20% complete-fill probability?
For complete fill, the arriving volume must consume both the queue ahead $Q = 100$ and our order size $S = 1$:
$$\text{Total Queue Ahead} = Q + S = 100 + 1 = 101 \text{ contracts}$$
$$\text{Expected Traded Volume} = \lambda \cdot t = 20 \times 10 = 200 \text{ contracts}$$
$$\text{Hazard Intensity} = \frac{200}{101} = 1.9801980198\dots$$
$$P(\text{complete}) = 1 - e^{-1.980198} = 1 - 0.13804217\dots = \mathbf{0.8619578\dots \approx 86.20\%}$$
In code, this is formatted as `0.861958` (Decimal).

### 5. Why do any-fill and complete-fill probabilities differ by only 0.27 percentage points?
- Any-fill intensity: $200 / 100 = 2.0000 \implies P(\text{any}) = 1 - e^{-2.0} = 0.864665$ ($86.47\%$).
- Complete-fill intensity: $200 / 101 = 1.980198 \implies P(\text{complete}) = 1 - e^{-1.980198} = 0.861958$ ($86.20\%$).
- Difference: $0.864665 - 0.861958 = \mathbf{0.002707}$ ($0.2707$ percentage points).
Because our order size $S = 1$ is tiny relative to the queue ahead $Q = 100$ ($1\%$ of the queue), once 100 contracts ahead have been consumed by 200 contracts of incoming volume, the 101st contract is almost certainly filled in the exact same trade burst.

### 6. What happens when queue position, arrival intensity, cancellation rate, or order quantity changes?
- **Queue Position ($Q$ increases)**: Intensity $\lambda t / Q \to 0$, causing fill probability to decay exponentially towards 0.
- **Arrival Intensity ($\lambda$ increases)**: Intensity increases linearly, causing fill probability to approach 1 asymptotically ($1 - e^{-\infty} = 1$).
- **Cancellation Rate ($C$)**: In the `QueueAwarePaperExecutionEngine`, cancellations ahead deplete the queue by effective credit $\alpha$:
  - Conservative ($\alpha = 0.0$): Cancellations provide zero queue depletion; only executed volume moves the order.
  - Central ($\alpha = 0.5$): 50% of cancelled depth ahead is credited towards queue depletion.
  - Optimistic ($\alpha = 1.0$): Any price touch fills the order immediately.
- **Order Size ($S$ increases)**: Complete fill requires $Q + S$. If $S$ is large (e.g., $S = 100$, doubling queue to 200), intensity drops to $200 / 200 = 1.0 \implies P(\text{complete}) = 1 - e^{-1.0} = 63.21\%$, widening the partial-fill gap dramatically.

### 7. Is the result calibrated against observed order-level fills, or is it purely a simulation assumption?
It is **strictly a simulation assumption** (`SIMULATION_ASSUMPTION`).
The repository contains 1m OHLCV bars and 113 aggregated Level-2 order book snapshots. Neither asset contains individual order timestamps, cancel-replace sequences, or queue position tokens (Market-by-Order / Level 3). Without MBO data, queue priority cannot be empirically calibrated.

---

## 3. Comparison: Exponential Block Hazard vs Erlang-$k$ Pure Poisson Process

To evaluate the mathematical validity of the exponential block hazard approximation, we contrast it with a rigorous **discrete Poisson arrival process**:

| Model Aspect | Exponential Block Hazard (`queue_dynamics.py`) | Erlang-$Q$ Poisson Counting Process |
|---|---|---|
| **Stochastic Variable** | $T_{\text{clear}} \sim \text{Exp}(\lambda / Q)$ | $N(t) \sim \text{Poisson}(\lambda t)$ |
| **Event Definition** | Depletion of monolithic block $Q$ | Arrival of $k$ individual 1-contract trades |
| **Probability Formula** | $P = 1 - e^{-\frac{\lambda t}{Q}}$ | $P(N(t) \ge Q) = 1 - \sum_{k=0}^{Q-1} \frac{(\lambda t)^k e^{-\lambda t}}{k!}$ |
| **Mean Volume ($V$)** | $200$ contracts | $200$ contracts |
| **Queue Ahead ($Q$)** | $100$ contracts | $100$ contracts |
| **Fill Probability ($10\text{s}$)** | **$86.47\%$** | **$> 99.9999999999\%$** ($> 1 - 10^{-12}$) |
| **Economic Interpretation** | High variance; models lumpy, large-block order flow | Low variance; models independent tiny trades |

### Mathematical Insight
In a pure Poisson arrival process where $\lambda = 20 \text{ contracts/sec}$, the number of contracts arriving in $10$ seconds has mean $\mu = 200$ and standard deviation $\sigma = \sqrt{200} \approx 14.14$.
The threshold $Q = 100$ is more than **$7$ standard deviations below the mean** ($(200 - 100) / 14.14 = 7.07\sigma$). Under an Erlang counting process, the probability of failing to trade at least 100 contracts is virtually zero ($< 10^{-12}$).
The exponential block-hazard formula yields $86.47\%$ because it assigns high dispersion to queue depletion, effectively assuming that queue exhaustion happens in large, uncertain chunks. This makes the block-hazard model **far more conservative** than a naive Poisson trade counting model, which is desirable for safety.

---

## 4. Boundary Condition & Robustness Testing

The model has been hardened and verified across all boundary conditions in `core/research/queue_dynamics.py`:
- **$\lambda = 0$ (Zero volume rate)**: Intensity $= 0 \implies P(\text{any}) = 0.000000, P(\text{complete}) = 0.000000, \text{wait} = 999999.00 \text{s}$.
- **$Q = 0$ (Top of queue)**: $P(\text{any}) = 1.000000, \text{time} = 0.00 \text{s}$; complete fill governed solely by $S$.
- **$Q \to \infty$ (Deep queue)**: Intensity $\to 0 \implies P \to 0$.
- **Negative or Non-Finite Inputs**: Rejects with `ValueError("Inputs must be finite")` or `ValueError("Inputs must be non-negative and positive where required")`.
