# QUANTENGINE PHASE 172 — QUEUE MODEL VALIDATION REPORT

**Audit Date**: 2026-10-20  
**Status**: `SIMULATION_ASSUMPTION | NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Target Component**: `core/research/queue_dynamics.py` & `core/paper_trading/queue_aware_paper_engine.py`

---

## 1. Executive Summary & Calibration Reproduction

Phase 171 reported an initial queue fill estimate:
- **Queue Ahead**: 100 contracts
- **Expected Waiting Time**: 5.00 seconds
- **Reported Fill Probability within 10s**: 86.2%

We conducted an independent forensic audit of the mathematical origin of this estimate. We reproduced the exact underlying arrival distribution and parameterized its arrival intensity.

### Mathematical Origin & Distribution Breakdown

The 86.2% figure derives from a continuous Poisson volume arrival process with mean arrival intensity:
$$\lambda = 20.0 \text{ contracts/second}$$

Over a 10.0-second horizon ($T = 10.0$), the expected cumulative market volume traded at the top of the book is:
$$\mathbb{E}[V_{10}] = \lambda \times T = 20.0 \times 10.0 = 200.0 \text{ contracts}$$

Under an exponential waiting-time / Poisson arrival formulation:
1. **Any Fill Probability ($P_{\text{any}}$)**:
   For volume to reach the order position, it must consume the 100 contracts displayed ahead in the queue.
   $$\text{Arrival Intensity } \mu_{\text{queue}} = \frac{\mathbb{E}[V_{10}]}{Q_{\text{ahead}}} = \frac{200.0}{100.0} = 2.0$$
   $$P(\text{Any Fill}) = 1 - e^{-2.0} \approx 0.864665 \implies \mathbf{86.47\%}$$

2. **Complete Fill Probability ($P_{\text{complete}}$)**:
   For a full execution of a 1-contract order, the market volume must consume both the queue ahead (100) and the order quantity itself (1), requiring 101 contracts:
   $$\text{Arrival Intensity } \mu_{\text{complete}} = \frac{\mathbb{E}[V_{10}]}{Q_{\text{ahead}} + Q_{\text{order}}} = \frac{200.0}{101.0} \approx 1.980198$$
   $$P(\text{Complete Fill}) = 1 - e^{-1.980198} \approx 0.861967 \implies \mathbf{86.20\%}$$

This proves conclusively that **86.20% is the complete fill probability for a 1-contract order**, while the probability of receiving at least a partial fill is **86.47%**.

---

## 2. Separation of the Eight Granular Metrics

To prevent confounding fill probability with execution profitability, `core/research/queue_dynamics.py` separates 8 distinct metrics:

| Metric ID | Description | Calibrated Value | Formula / Derivation | Classification |
|---|---|---|---|---|
| **M1** | **Probability of Any Fill** | **86.47%** | $1 - e^{-200/100}$ | `SIMULATION_ASSUMPTION` |
| **M2** | **Probability of Complete Fill** | **86.20%** | $1 - e^{-200/101}$ | `SIMULATION_ASSUMPTION` |
| **M3** | **Expected Time to First Fill** | **5.00 s** | $Q_{\text{ahead}} / \lambda = 100 / 20$ | `SIMULATION_ASSUMPTION` |
| **M4** | **Expected Time to Complete Fill** | **5.05 s** | $(Q_{\text{ahead}} + Q_{\text{order}}) / \lambda = 101 / 20$ | `SIMULATION_ASSUMPTION` |
| **M5** | **Expected Filled Quantity** | **0.86 contracts** | $Q_{\text{order}} \times P_{\text{complete}}$ | `SIMULATION_ASSUMPTION` |
| **M6** | **Cancellation / Expiration Prob.** | **13.80%** | $1 - P_{\text{complete}}$ | `SIMULATION_ASSUMPTION` |
| **M7** | **Adverse Selection Cost (on Fill)** | **0.0164 USD** | $\text{Notional} \times 2.0 \text{ bps} = 82 \times 0.0002$ | `SIMULATION_ASSUMPTION` |
| **M8** | **Unfilled Opportunity Cost** | **0.0207 USD** | $P_{\text{unfilled}} \times \text{Expected Target Profit} = 13.8\% \times 0.15$ | `SIMULATION_ASSUMPTION` |

> [!IMPORTANT]
> **Labeling Notice**: These metrics are classified as `SIMULATION_ASSUMPTION`. They are mathematical deductions from assumed Poisson arrival rates, not empirical proof of live exchange fill rates.

---

## 3. Orderbook Queue Scenarios & L2 Update Semantics

Because Level 2 market data provides aggregated depth snapshots rather than an individual order queue index, individual priority cannot be deterministically inferred from aggregate L2 delta frames. `core/paper_trading/queue_aware_paper_engine.py` implements three explicit scenarios:

### Scenario Definitions
1. **Conservative (`CONSERVATIVE`)**:
   - Only verifiable trade executions at the limit price deplete queue ahead.
   - Depth reductions (cancellations) are assumed to have occurred *behind* our order in the queue ($0\%$ cancellation credit).
   - Worst-case queue depletion; prevents unearned fill optimism.
2. **Central (`CENTRAL`)**:
   - Executed trades consume queue ahead 1-to-1.
   - Depth cancellations are credited at $50\%$ ahead, $50\%$ behind, representing an uninformative uniform distribution of order cancellations.
3. **Optimistic (`OPTIMISTIC`)**:
   - Orders are granted priority upon price touch.
   - All depth cancellations and volume are credited ahead.
   - Used strictly as an upper sensitivity bound, never as primary evidence.

---

## 4. Empirical Orderbook Evidence & Data Limitations

### Venue Archive Inspection
An audit of `research/captures/phase167_recon/l2/delta_ob_updates_archive.json` reveals:
- Total high-frequency frames: **113 frames**
- Symbol: `BTCUSDT`
- Mean top-of-book bid depth: $1,312.53$ contracts
- Mean top-of-book ask depth: $686.10$ contracts
- Time horizon: Isolated burst on 2026-10-19 (~several minutes)

### Limitation & Evidence Gate
- 113 L2 frames is insufficient to build an empirically validated queue fill model across varied volatility regimes.
- Continuous multi-year (2024–2026) tick and L2 orderbook feeds are **unsupplied in repository storage** and classified as `BLOCKED_EVIDENCE` under `BLOCK-172-05`.
- Extrapolating 113 frames into a production trading model is prohibited.
