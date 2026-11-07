# QuantEngine Phase 178 — Fee, Tax, Rebate & P&L Reproduction

## Executive Summary

Phase 178 independently reproduced the canonical economics and fee accounting table using exact `Decimal` arithmetic.

---

## 1. Parameters & Accounting Formulation

- **Contract Multiplier**: $M = 0.001\ \text{BTC} / \text{contract}$
- **Base Fee Rates**: Maker = $0.02\%$ ($2.0\ \text{bps}$), Taker = $0.05\%$ ($5.0\ \text{bps}$), VIP Rebate = $-0.01\%$ ($-1.0\ \text{bps}$).
- **Exchange GST**: $18.0\%$ applied strictly to brokerage commission fees.
- **Effective Fee Rates**: Maker = $2.36\ \text{bps}$, Taker = $5.90\ \text{bps}$, Rebate = $-1.00\ \text{bps}$ (zero GST on rebates).

---

## 2. Canonical Setup Results (1 Contract, Entry $82,000.00)

| Setup | Target (pts) | Stop (pts) | Gross Target (USD) | Taker Fee (USD) | Asym Maker/Taker Fee (USD) | Net P&L Taker (USD) | Net P&L Asym (USD) | Breakeven Taker | Breakeven Asym |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Micro-Scalp** | 4.5 | 3.0 | \$0.00450 | \$0.09675 | \$0.06772 | -\$0.09225 | -\$0.06322 | 96.75 pts | 67.72 pts |
| **Tight Scalp** | 15.0 | 10.0 | \$0.01500 | \$0.09676 | \$0.06773 | -\$0.08176 | -\$0.05273 | 96.76 pts | 67.73 pts |
| **Mini Scalp** | 50.0 | 30.0 | \$0.05000 | \$0.09679 | \$0.06776 | -\$0.04679 | -\$0.01776 | 96.79 pts | 67.76 pts |
| **Intraday** | 150.0 | 75.0 | \$0.15000 | \$0.09685 | \$0.06782 | +\$0.05315 | +\$0.08218 | 96.85 pts | 67.82 pts |
| **Swing** | 500.0 | 200.0 | \$0.50000 | \$0.09706 | \$0.06803 | +\$0.40294 | +\$0.43197 | 97.06 pts | 68.03 pts |
| **Trend** | 1500.0 | 500.0 | \$1.50000 | \$0.09765 | \$0.06862 | +\$1.40235 | +\$1.43138 | 97.65 pts | 68.62 pts |

---

## 3. Discrepancy Reconciliation Across Phases

- **Phase 174 vs Phase 175**: The \$42,082 notional anomaly in Phase 174 was caused by omitting the 0.001 multiplier on 1 contract. Resolved in Phase 175 with explicit $82.00 USD notional.
- **Phase 176 vs Phase 177**: Phase 176 identified the 0.50 vs 0.10 narrative discrepancy in `FeeScheduleProvenance`. Resolved in Phase 177 with authoritative 0.10 tick size.
- **Phase 178**: Confirmed zero discrepancy in fee arithmetic, linear scaling, and net P&L calculations.
