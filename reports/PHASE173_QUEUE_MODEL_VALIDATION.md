# QUANTENGINE PHASE 173 — QUEUE DYNAMICS MATHEMATICAL AUDIT & VALIDATION

**Evaluation Date**: 2026-10-20  
**Status**: `SIMULATION_ASSUMPTION | NOT_PRODUCTION_READY`  
**Classification**: `QUEUE_MODEL_MATHEMATICAL_AUDIT`

---

## 1. Executive Summary

This report performs a rigorous mathematical audit of the queue dynamics module (`core/research/queue_dynamics.py`) implemented in Phase 171 and continued into Phase 172. It investigates the Poisson arrival formulation, derives the relationship between the reported $86.47\%$ and $86.20\%$ fill probabilities, separates the 8 required granular metrics, and formalizes why aggregate L2 data cannot provide empirical order-level fill validation.

---

## 2. Mathematical Audit of the 86.47% and 86.20% Estimates

### 2.1 Parameterization
The simulation parameters evaluated are:
- Displayed Queue Ahead ($Q$): $100$ contracts
- Submitted Order Size ($O$): $1$ contract
- Effective Volume Arrival Rate ($\lambda$): $20.0$ contracts/second
- Observation Time Horizon ($T$): $10.0$ seconds
- Expected Total Volume ($V$): $\lambda \times T = 20.0 \times 10.0 = 200.0$ contracts

### 2.2 Derivation from Code
In `core/research/queue_dynamics.py`, the probabilities are calculated as:
1. **Probability of Any Fill ($P_{\text{any}}$)**:
   The volume required to consume the queue ahead is $Q = 100$.
   $$\text{intensity}_{\text{any}} = \frac{V}{Q} = \frac{200.0}{100.0} = 2.0$$
   $$P_{\text{any}} = 1 - e^{-2.0} = 1 - 0.13533528 = 0.8646647... \approx \mathbf{86.47\%}$$
   Expected time to first fill:
   $$E[T_{\text{first}}] = \frac{Q}{\lambda} = \frac{100}{20} = \mathbf{5.00\text{ s}}$$

2. **Probability of Complete Fill ($P_{\text{complete}}$)**:
   The volume required to consume the queue ahead plus the order size is $Q + O = 101$.
   $$\text{intensity}_{\text{complete}} = \frac{V}{Q + O} = \frac{200.0}{101.0} \approx 1.9801980$$
   $$P_{\text{complete}} = 1 - e^{-1.9801980} = 1 - 0.1380424 = 0.8619576... \approx \mathbf{86.20\%}$$
   Expected time to complete fill:
   $$E[T_{\text{complete}}] = \frac{Q + O}{\lambda} = \frac{101}{20} = \mathbf{5.05\text{ s}}$$

---

## 3. Theoretical Model vs Micro-Structure Reality

### 3.1 Exponential Block Waiting Model vs Poisson Count Process
A fundamental mathematical distinction must be maintained:
- **What the Code Implements**: The formula $1 - e^{-\lambda T / Q}$ evaluates the cumulative distribution function (CDF) of an **exponential random variable** $X \sim \text{Exp}(\mu = Q / \lambda)$. This models the entire queue depletion of $Q$ contracts as a single collective hazard event with mean waiting time $\tau = 5.0\text{ s}$.
- **What a Unit Poisson Arrival Process Predicts**: If trades arrive as single individual contracts under a Poisson point process with rate $\lambda = 20\text{ contracts/s}$, the number of arrivals $N(10)$ in 10 seconds is Poisson distributed with mean $\mu = 200$:
  $$N(10) \sim \text{Poisson}(200)$$
  The probability that at least $100$ contracts arrive is given by the Erlang-$100$ CDF:
  $$P(N(10) \ge 100) = 1 - \sum_{k=0}^{99} \frac{200^k e^{-200}}{k!}$$
  Because the mean is $200$ and the standard deviation is $\sigma = \sqrt{200} \approx 14.14$, a threshold of $100$ lies $(200 - 100) / 14.14 \approx 7.07$ standard deviations below the mean. The probability of exceeding 100 contracts under pure unit Poisson arrivals is $> 0.999999999999$ ($1 - 10^{-12}$).
- **Why the Exponential Block Assumption is Used**: In real order books, trades do not arrive as independent 1-contract Poisson steps. Instead, orders arrive in clusters, liquidity is consumed in lumps, and cancellations fluctuate. Modeling the queue depletion as an exponential block event with parameter $\tau = Q / \lambda$ reflects the empirical reality that trade flow may pause, market orders may stop, or price may tick away. However, it must be recognized as an aggregated engineering assumption, not a microscopic proof.

---

## 4. Separation of the Eight Granular Metrics

Under the validated configuration ($Q = 100$, $O = 1$, $\lambda = 20$, $T = 10$, Notional = $82.00$ USD, Target Profit = $0.15$ USD, Adverse Selection = $2.0$ bps):

1. **Probability of Any Fill ($P_{\text{any}}$)**: $86.47\%$ ($0.864665$)
2. **Probability of Complete Fill ($P_{\text{complete}}$)**: $86.20\%$ ($0.861958$)
3. **Expected Time to First Fill**: $5.00$ seconds
4. **Expected Time to Complete Fill**: $5.05$ seconds
5. **Expected Filled Quantity**:
   $$E[Q_{\text{fill}}] = O \cdot P_{\text{complete}} + \frac{O}{2} \cdot (P_{\text{any}} - P_{\text{complete}}) = 1 \cdot 0.861958 + 0.5 \cdot (0.864665 - 0.861958) = \mathbf{0.86\text{ contracts}}$$
6. **Cancellation / Expiration Probability ($P_{\text{unfilled}}$)**:
   $$P_{\text{unfilled}} = 1 - P_{\text{complete}} = 1 - 0.861958 = \mathbf{13.80\%}\ (0.138042)$$
7. **Adverse Selection Cost Conditional on Fill**:
   $$\text{Notional} \times \frac{2.0}{10000} = 82.00 \times 0.0002 = \mathbf{0.01640000\text{ USD}}$$
8. **Unfilled Opportunity Cost**:
   $$\text{Target Profit} \times P_{\text{unfilled}} = 0.1500 \times 0.138042 = \mathbf{0.02070630\text{ USD}}$$

**Classification**: `SIMULATION_ASSUMPTION` (No empirical claim without high-frequency order-level data).

---

## 5. Audit of Queue Depletion Scenarios

The simulator provides three scenarios to bound uncertainty:
1. **Conservative Scenario**:
   - Depth cancellations provide **0% credit** toward queue depletion.
   - Only executed trade volume at the resting limit price advances queue priority.
   - Protects against lookahead and optimistic queue clearing.
2. **Central Scenario**:
   - Depth cancellations provide **50% credit** toward queue depletion.
   - Represents the midpoint assumption where half of displayed cancellations occur ahead of our order.
   - Classified as a heuristic modeling assumption.
3. **Optimistic Scenario**:
   - Assumes immediate fill upon first price touch.
   - Strictly utilized as a sensitivity upper bound; prohibited from being cited as empirical evidence.

---

## 6. L2 Orderbook Limitations & Data Absence

1. **The 113 L2 Updates Archive**:
   The available high-frequency capture (`research/captures/phase167_recon/l2/delta_ob_updates_archive.json`) contains 113 aggregated Level-2 book frames from 2026-10-19.
2. **Inability to Derive Exact Queue Priority from L2**:
   - Aggregated L2 updates report total bid and ask depth at each price level. They do NOT contain individual order IDs, order arrival timestamps, or cancel events by order.
   - When displayed depth decreases between two L2 snapshots, an L2 feed cannot distinguish whether the reduction was caused by a trade fill or by a cancellation.
   - Therefore, true order priority and individual queue depletion cannot be proven from L2 data alone. Market-by-Order (MBO / Level 3) data or authenticated execution telemetry is strictly required.
3. **Data Absence Classification**:
   Multi-year 2024–2026 continuous tick-by-tick depth is absent from the repository and remains recorded as **`BLOCKED_EVIDENCE`** (`BLOCK-172-05`).
