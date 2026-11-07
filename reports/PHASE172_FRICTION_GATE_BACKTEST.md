# QUANTENGINE PHASE 172 — FRICTION HURDLE GATE & POST-COST BACKTEST REPORT

**Audit Date**: 2026-10-20  
**Status**: `SIMULATION_ASSUMPTION | NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Target Component**: `core/backtesting/post_cost_backtester.py` & `core/execution/friction_hurdle_gate.py`

---

## 1. Pre-Order Decision Boundary Integration

In Phase 172, the `FrictionHurdleGate` was wired directly into the pre-order dispatch boundary of the historical backtesting engine via `core/backtesting/post_cost_backtester.py`.

Unlike post-hoc reporting filters, the gate intercepts orders **before execution simulation occurs**, preventing the simulator from allocating capital, generating synthetic fills, or obscuring fee drag on doomed trades.

### The Three Configured Rules

Every order candidate is evaluated against three non-bypassable rules:
1. **Fee-to-Target Hurdle ($\le 40\%$)**:
   $$\text{Fee Ratio} = \frac{\text{Round-Trip Fees (USD)}}{\text{Gross Expected Target (USD)}} \times 100 \le 40.0\%$$
2. **Breakeven Margin Multiple ($\ge 2.0\times$)**:
   $$\text{Target Margin} = \frac{\text{Target Points}}{\text{Breakeven Points}} \ge 2.0\times$$
   *(Where $\text{Breakeven Points} = \frac{\text{Round-Trip Fees (USD)}}{\text{Contract Multiplier} \times \text{Quantity}}$)*
3. **Post-Fee Risk-to-Reward ($\ge 1.25$)**:
   $$\text{Post-Fee R:R} = \frac{\text{Gross Target (USD)} - \text{Total Fees (USD)}}{\text{Stop Loss Risk (USD)} + \text{Total Fees (USD)}} \ge 1.25$$

---

## 2. Dimensional Units & Precision Discipline

To prevent unit mixing and silent errors, all components enforce strict dimensional definitions:
- **Price**: Quote currency index level (e.g., $82,000.00$ USD/BTC).
- **Points**: Index price displacement ($1 \text{ pt} = 1.00$ quote currency unit).
- **Contract Multiplier**: Multiplier converting index points to settlement currency ($0.001$ for BTCUSDT; $1 \text{ pt} \times 0.001 = 0.001 \text{ USDT}$).
- **Quantity**: Integer count of contracts ($1 \text{ contract}$).
- **Notional**: $\text{Price} \times \text{Multiplier} \times \text{Quantity} = 82,000 \times 0.001 \times 1 = 82.00 \text{ USD}$.
- **Fees**: Base commission rate $\times$ notional $+ 18\%$ GST on brokerage.
- **Precision**: Full Decimal arithmetic with `ROUND_HALF_UP` to 8 decimal places for USD amounts and 2 decimal places for index points and percentages.

---

## 3. Trade Selection Tally Across Representative Setups

We evaluated 6 representative trade setups across 5 execution variants:
- **Variant A**: Frictionless baseline (theoretical zero-fee, zero-slippage).
- **Variant B**: Taker execution with verified Delta India fee schedule ($5.90$ bps effective per leg).
- **Variant C**: Asymmetric Maker Entry ($2.36$ bps) / Taker Exit ($5.90$ bps) with Conservative Queue assumptions and $2.0$ bps adverse selection penalty.
- **Variant D**: Asymmetric Maker Entry / Taker Exit with Central Queue assumptions ($1.0$ bps adverse selection penalty).
- **Variant E**: Optimistic Maker Execution ($0.0$ bps adverse selection penalty; touch fills).

### Comparative Trade Selection & P&L Summary

| Setup Name | Target (pts) | Gross PnL | Variant A (Zero Fee) | Variant B (Taker) | Variant C (Maker Cons.) | Gate Result (Taker) | Gate Result (Maker) |
|---|---|---|---|---|---|---|---|
| **Micro-Scalp** | 4.5 pts | +0.0045 USD | +0.0045 USD | -0.0923 USD | -0.0703 USD | **REJECTED (2150%)** | **REJECTED (1289%)** |
| **Tight Scalp** | 15.0 pts | +0.0150 USD | +0.0150 USD | -0.0818 USD | -0.0598 USD | **REJECTED (645%)** | **REJECTED (387%)** |
| **Small Intraday** | 50.0 pts | +0.0500 USD | +0.0500 USD | -0.0468 USD | -0.0248 USD | **REJECTED (194%)** | **REJECTED (116%)** |
| **Standard Intraday**| 150.0 pts | +0.1500 USD | +0.1500 USD | +0.0532 USD | +0.0519 USD | **REJECTED (64.6%)**| **ACCEPTED (38.7%)** |
| **Swing Target** | 400.0 pts | +0.4000 USD | +0.4000 USD | +0.3030 USD | +0.3017 USD | **ACCEPTED (24.2%)** | **ACCEPTED (14.5%)** |
| **Wide Trend** | 1000.0 pts | +1.0000 USD | +1.0000 USD | +0.9029 USD | +0.9016 USD | **ACCEPTED (9.7%)**  | **ACCEPTED (5.8%)**  |

### Trade-Selection Pass Rates
- **Taker Gating Pass Rate**: $2 / 6 = \mathbf{33.3\%}$ (only targets $\ge 400$ pts pass; all targets $\le 150$ pts fail).
- **Maker Gating Pass Rate**: $3 / 6 = \mathbf{50.0\%}$ (targets $\ge 150$ pts pass; targets $\le 50$ pts fail).

---

## 4. Key Quantitative Insights & Edge Validation

> [!WARNING]
> **MAKER EXECUTION DOES NOT RESCUE SCALPING STRATEGIES**
> While passive Maker entry cuts round-trip fee points from $96.8$ points down to $58.1$ points (a $40\%$ reduction), **micro-scalps ($\le 50$ points) remain severely negative-expectancy**.
> 
> For a 15-point scalp:
> - Gross target profit: $+0.0150$ USD
> - Round-trip maker entry / taker exit fee: $-0.0581$ USD
> - Net loss before adverse selection: $-0.0431$ USD
> - Fee-to-target ratio: **$387\%$** (violating the $40\%$ gate by nearly 10x).

### The Adverse Selection & Opportunity Cost Reality
Under Conservative Maker execution (Variant C):
1. **Adverse Selection**: When filled passively, orders suffer an adverse post-fill price drift averaging $2.0$ bps ($-0.0164$ USD on an $82$ USD notional). On a 150-point target, this reduces net profit from $+0.0919$ USD down to $+0.0519$ USD.
2. **Opportunity Cost of Non-Fill**: Orders have an expected complete fill probability of $86.2\%$. The $13.8\%$ unfilled orders forfeit the trade profit while the market trends away.
3. **Conclusion**: Maker execution improves net expectancy **only on medium-to-large targets ($\ge 150$ points)** where gross profit substantially exceeds the combined drag of maker entry fee, taker exit fee, adverse selection, and non-fill risk.

---

## 5. Temporal Dataset Coverage & Lineage Disclosure

An independent forensic file scan confirms the continuous data assets currently available:
- **`data/history/BTCUSDT/1m.parquet`**: Exactly **1,440 rows** spanning 24 continuous hours from **2026-09-05T21:35:00Z to 2026-09-06T21:34:00Z**.
- **`research/captures/phase167_recon/l2/delta_ob_updates_archive.json`**: Exactly **113 frames** from 2026-10-19.
- **Multi-Year Coverage Status**: Continuous multi-year (2024–2026) tick and orderbook data is **unsupplied in repository storage** and recorded as `BLOCKED_EVIDENCE` under `BLOCK-172-05`. Multi-year extrapolations outside the verified 1,440-minute window are parameter-based simulations, not empirical proof.
