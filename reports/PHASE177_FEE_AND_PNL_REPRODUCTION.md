# QuantEngine Phase 177 — Fee, Tax, Rebate & P&L Reproduction

## Executive Summary

This report presents an independent reproduction of fee schedules, Goods & Services Tax (GST), liquidity rebates, and net P&L calculations using exact `Decimal` arithmetic.

---

## 1. Fee Schedule & Tax Structure

### A. Rates
- **Standard Taker Commission**: $0.05\%$ ($5.0\ \text{bps}$) base.
- **Standard Maker Commission**: $0.02\%$ ($2.0\ \text{bps}$) base.
- **VIP Rebate Tier**: $-0.01\%$ ($-1.0\ \text{bps}$) base (simulation tier only; standard account earns zero rebates).
- **GST Rate**: $18.0\%$ applied strictly to brokerage commission fees.

### B. Effective Rates
- **Effective Taker**: $5.0\ \text{bps} \times 1.18 = 5.90\ \text{bps}$.
- **Effective Maker**: $2.0\ \text{bps} \times 1.18 = 2.36\ \text{bps}$.
- **Effective Rebate**: $-1.0\ \text{bps}$ (zero GST owed on rebates paid to trader).

---

## 2. Canonical Setup Scenarios (1 Contract, Multiplier = 0.001)

All scenarios evaluated at Entry \$82,000.00:

| Setup | Target (pts) | Stop (pts) | Gross Target | Taker RT Fee | Asym (Maker/Taker) Fee | Net Target (Taker) | Net Target (Asym) | Breakeven (Taker) | Breakeven (Asym) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Micro-Scalp** | 4.5 | 3.0 | \$0.0045 | \$0.0967 | \$0.0677 | -\$0.0922 | -\$0.0632 | 96.7 pts | 67.7 pts |
| **Tight Scalp** | 15.0 | 10.0 | \$0.0150 | \$0.0968 | \$0.0677 | -\$0.0818 | -\$0.0527 | 96.8 pts | 67.7 pts |
| **Mini Scalp** | 50.0 | 30.0 | \$0.0500 | \$0.0968 | \$0.0678 | -\$0.0468 | -\$0.0178 | 96.8 pts | 67.8 pts |
| **Intraday** | 150.0 | 75.0 | \$0.1500 | \$0.0968 | \$0.0678 | +\$0.0532 | +\$0.0822 | 96.8 pts | 67.8 pts |
| **Swing** | 500.0 | 200.0 | \$0.5000 | \$0.0971 | \$0.0679 | +\$0.4029 | +\$0.4321 | 97.1 pts | 67.9 pts |
| **Trend** | 1500.0 | 500.0 | \$1.5000 | \$0.0977 | \$0.0683 | +\$1.4023 | +\$1.4317 | 97.7 pts | 68.3 pts |

### Key Economic Takeaways:
1. Setups under 50 points are mathematically destroyed by friction under all execution styles.
2. The standard 150-point intraday target passes only under Asymmetric Maker entry (67.8 pt hurdle), but fails pure Taker execution (fee consumes 64.5% of target, breaching the 40% cap).
3. Breakeven hurdles are invariant to position size because fees and gross P&L scale linearly with contract quantity.
