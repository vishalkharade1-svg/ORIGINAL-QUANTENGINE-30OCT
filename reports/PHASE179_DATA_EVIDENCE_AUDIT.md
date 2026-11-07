# QuantEngine Phase 179 — Data Evidence & Statistical Limitations Audit

## Executive Summary

Phase 179 audited historical dataset continuity, testnet execution sample sizes, orderbook queue simulation assumptions, and fee/tax schedules.

In accordance with strict empirical standards, all simulation assumptions are separated from authenticated empirical observations.

---

## 1. Data Evidence Inventory & Lineage Discontinuity

| Dataset Artifact | Start Timestamp (UTC) | End Timestamp (UTC) | Record Count | Evidence Type | Limitation Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`BTCUSDT/1m.parquet`** | 2026-09-05T00:00:00Z | 2026-09-05T23:59:00Z | 1,440 1m bars | Historical Candles | `TEMPORAL_DISJOINT` (44 days before L2 feed) |
| **`phase170_delta_l2_book.parquet`** | 2026-10-19T06:00:00Z | 2026-10-19T06:30:00Z | High-frequency snapshots | L2 Orderbook Depth | `LIMITED_WINDOW` (30 minutes duration) |
| **`phase80_authenticated_fills.json`** | 2026-09-25T14:12:00Z | 2026-09-25T14:15:00Z | $N = 2$ executed fills | Authenticated REST/WS | `UNDERPOWERED` ($N=2 \ll 30$) |

### A. The 44-Day Temporal Gap (`BLOCK-179-03`)
- The 1-minute historical continuous candles cover **September 5, 2026**.
- The Level-2 order book depth updates cover **October 19, 2026**.
- There is a **44-day non-overlapping disjoint gap** between the alpha signal dataset and the microstructure execution dataset.
- Signal generation on September 5 cannot be replayed against October 19 orderbooks without violating contemporaneous market causality.

### B. Statistical Underpowering ($N=2$) (`BLOCK-179-04`)
- Valid authenticated India Testnet fill evidence remains strictly limited to $N=2$ BTCUSD fills.
- A sample of $N=2$ possesses negligible statistical power and cannot establish fill probability, slippage distributions, adverse selection drag, or strategy profitability.

### C. Queue Dynamics Simulation Classification (`BLOCK-179-02`)
- The Poisson queue depletion heuristic:
  $$P(\text{Fill}) = 1 - \exp\left(-\frac{\lambda \cdot t}{Q}\right)$$
  is classified as a **`SIMULATION_ASSUMPTION`**, not empirical truth.
- True exchange matching priority depends on order placement sequence, hidden orders, market-by-order (MBO) priority queues, and high-frequency cancellation flows.

### D. Fee, Rebate & Tax Status (`BLOCK-179-07`)
- The Delta Exchange VIP maker rebate tier (-1.0 bps) is modeled as a counterfactual research scenario.
- Standard base fees (Maker 2.0 bps, Taker 5.0 bps) and 18% GST (effective Maker 2.36 bps, Taker 5.90 bps) are verified from public documentation fixtures, but account-specific VIP qualification, TDS withholding, and volume-tier reductions remain open empirical gaps.
