# QUANTENGINE PHASE 173 — POST-COST BACKTEST REPRODUCTION & SETUP ANALYSIS

**Evaluation Date**: 2026-10-20  
**Auditor**: Independent Quantitative Execution Auditor  
**Status**: `REPRODUCED | NOT_PRODUCTION_READY`

---

## 1. Overview & Evaluation Mandate

This report provides the complete numerical reproduction and forensic breakdown of the post-cost backtesting evaluation conducted across the five comparative execution variants (Variants A through E) and six representative market setups.

The evaluation incorporates the verified Delta Exchange India fee schedule:
- **Taker Base Commission**: $0.05\%$ ($5.00$ bps)
- **Maker Base Commission**: $0.02\%$ ($2.00$ bps)
- **GST Rate**: $18.00\%$ applied strictly to brokerage commission
- **Effective Taker Rate**: $5.00 \times 1.18 = \mathbf{5.90\text{ bps}}$
- **Effective Maker Rate**: $2.00 \times 1.18 = \mathbf{2.36\text{ bps}}$
- **Contract Multiplier**: $0.001$ BTC per contract
- **Settlement Currency**: USD

---

## 2. Mathematical Definition of Terms and Units

To avoid unit mixing, all fields are formally defined:
1. **Entry Price ($P_{\text{entry}}$)**: USD per BTC (e.g. $82,000.00$).
2. **Target Price ($P_{\text{target}}$)**: USD per BTC.
3. **Stop Price ($P_{\text{stop}}$)**: USD per BTC.
4. **Target Points ($\Delta P_{\text{target}}$)**: Absolute points $|P_{\text{target}} - P_{\text{entry}}|$.
5. **Contract Multiplier ($M$)**: $0.001$ BTC per contract.
6. **Quantity ($Q$)**: Number of contracts (1 contract in benchmark runs).
7. **Gross Profit (USD)**: $\Delta P_{\text{target}} \times M \times Q$.
8. **Leg Notional (USD)**: Price $\times M \times Q$.
9. **Leg Fee (USD)**: $\text{Notional} \times \text{Base Rate} \times (1 + \text{GST})$.
10. **Round-Trip Fees (USD)**: $\text{Fee}_{\text{entry}} + \text{Fee}_{\text{exit}}$.
11. **Breakeven Points**: $\text{Total Fees} / (M \times Q)$.
12. **Fee-to-Gross Target Ratio (%)**: $(\text{Total Fees} / \text{Gross Target}) \times 100$.
13. **Post-Fee Risk-to-Reward (R:R)**: $\text{Net Target USD} / (\text{Gross Stop Loss USD} + \text{Total Fees})$.

---

## 3. Independent Numerical Reproduction Across Six Setups

### Setup 1: Micro-Scalp (4.5 Points)
- **Entry**: $82,000.00$ USD | **Target**: $82,004.50$ USD | **Stop**: $81,995.50$ USD
- **Gross Target USD**: $4.5 \times 0.001 \times 1 = \mathbf{0.00450000\text{ USD}}$
- **Variant A (Frictionless)**: Net = $+0.00450000$ USD | Hurdle: PASSED
- **Variant B (Taker)**:
  - Leg 1 Fee: $82.00 \times 0.0005 \times 1.18 = 0.04838000$ USD
  - Leg 2 Fee: $82.0045 \times 0.0005 \times 1.18 = 0.04838266$ USD
  - Total Fees: $\mathbf{0.09676266\text{ USD}}$
  - Net Profit: $0.00450000 - 0.09676266 = \mathbf{-0.09226266\text{ USD}}$
  - Fee / Target: $0.09676266 / 0.00450000 = \mathbf{2150.3\%}$
  - Hurdle: **REJECTED** (Fees exceed max allowed 40.0%)
- **Variant C (Maker Conservative)**:
  - Leg 1 Fee: $82.00 \times 0.0002 \times 1.18 = 0.01935200$ USD
  - Leg 2 Fee: $82.0045 \times 0.0002 \times 1.18 = 0.01935306$ USD
  - Total Fees: $\mathbf{0.03870506\text{ USD}}$
  - Adverse Selection (2.0 bps): $\mathbf{0.01640000\text{ USD}}$
  - Net Profit: $0.00450000 - 0.03870506 - 0.01640000 = \mathbf{-0.05060506\text{ USD}}$
  - Fee / Target: $0.03870506 / 0.00450000 = \mathbf{860.1\%}$
  - Hurdle: **REJECTED** (Fees consume 860.1% of target)

### Setup 2: Tight Scalp (15.0 Points)
- **Entry**: $82,000.00$ USD | **Target**: $82,015.00$ USD | **Stop**: $81,985.00$ USD
- **Gross Target USD**: $15.0 \times 0.001 \times 1 = \mathbf{0.01500000\text{ USD}}$
- **Variant B (Taker)**:
  - Total Fees: $\mathbf{0.09676885\text{ USD}}$
  - Net Profit: $\mathbf{-0.08176885\text{ USD}}$
  - Fee / Target: $\mathbf{645.1\%}$
  - Hurdle: **REJECTED** (Fees exceed max allowed 40.0%)
- **Variant C (Maker Conservative)**:
  - Total Fees: $\mathbf{0.03870754\text{ USD}}$
  - Adverse Selection (2.0 bps): $\mathbf{0.01640000\text{ USD}}$
  - Net Profit: $\mathbf{-0.04010754\text{ USD}}$
  - Fee / Target: $\mathbf{258.0\%}$
  - Hurdle: **REJECTED** (Fees consume 258.0% of target)

### Setup 3: Small Intraday (50.0 Points)
- **Entry**: $82,000.00$ USD | **Target**: $82,050.00$ USD | **Stop**: $81,950.00$ USD
- **Gross Target USD**: $50.0 \times 0.001 \times 1 = \mathbf{0.05000000\text{ USD}}$
- **Variant B (Taker)**:
  - Total Fees: $\mathbf{0.09678950\text{ USD}}$
  - Net Profit: $\mathbf{-0.04678950\text{ USD}}$
  - Fee / Target: $\mathbf{193.6\%}$
  - Hurdle: **REJECTED** (Fees exceed max allowed 40.0%)
- **Variant C (Maker Conservative)**:
  - Total Fees: $\mathbf{0.03871580\text{ USD}}$
  - Adverse Selection (2.0 bps): $\mathbf{0.01640000\text{ USD}}$
  - Net Profit: $\mathbf{-0.00511580\text{ USD}}$
  - Fee / Target: $\mathbf{77.4\%}$
  - Hurdle: **REJECTED** (Fees consume 77.4% of target)

### Setup 4: Standard Intraday (150.0 Points)
- **Entry**: $82,000.00$ USD | **Target**: $82,150.00$ USD | **Stop**: $81,900.00$ USD
- **Gross Target USD**: $150.0 \times 0.001 \times 1 = \mathbf{0.15000000\text{ USD}}$
- **Variant B (Taker)**:
  - Total Fees: $\mathbf{0.09684850\text{ USD}}$
  - Net Profit: $\mathbf{+0.05315150\text{ USD}}$ ($\approx +\$0.0532$)
  - Fee / Target: $\mathbf{64.6\%}$
  - Hurdle: **REJECTED** (Fee ratio 64.6% exceeds 40.0%)
- **Variant C (Maker Conservative)**:
  - Total Fees: $\mathbf{0.03873940\text{ USD}}$
  - Adverse Selection (2.0 bps): $\mathbf{0.01640000\text{ USD}}$
  - Conditional Net Profit: $\mathbf{+0.09486060\text{ USD}}$
  - Fee / Target: $25.8\% \le 40.0\%$ (Passes Rule 1)
  - Target / Breakeven: $150.0 / 38.74 = 3.87\text{x} \ge 2.0\text{x}$ (Passes Rule 2)
  - Post-Fee R:R: $(0.1500 - 0.0387) / (0.1000 + 0.0387) = 0.1113 / 0.1387 = \mathbf{0.80}$
  - Hurdle: **REJECTED** (Post-fee R:R 0.80 is below required 1.25)

---

## 4. Deep Dive: Why Conservative Maker yields +$0.0519 while Taker yields +$0.0532

On the 150-point setup:
1. **Taker Execution**:
   - Takes liquidity on entry and exit.
   - Fill probability: $100\%$ (immediate fill).
   - Adverse selection post-fill: $0.00$ bps (spread crossed aggressively).
   - Fees: $0.04838 + 0.04847 = 0.09685$ USD.
   - Net Profit: $0.1500 - 0.09685 = \mathbf{+\$0.0532\text{ USD}}$.
2. **Conservative Maker Execution (Asymmetric Entry + Taker Exit + Risk Drag)**:
   - Maker entry saves $0.0290$ USD in commission ($0.0484 - 0.0194$).
   - Asymmetric round-trip fees: $0.01935 + 0.04847 = \mathbf{0.06782\text{ USD}}$.
   - Adverse selection drag: $-2.0$ bps on $82.00$ USD notional $= \mathbf{-0.01640\text{ USD}}$.
   - Non-fill probability: $13.8042\%$ ($P_{\text{unfilled}} = 1 - 0.861958$).
   - Opportunity cost: $13.8042\% \times 0.1000$ USD target fraction $= \mathbf{-0.01380\text{ USD}}$.
   - Expected Net Outcome:
     $$\text{Gross} - \text{Fees} - \text{Adverse Selection} - \text{Non-Fill Drag} = 0.1500 - 0.06782 - 0.01640 - 0.01380 = \mathbf{+\$0.05198\text{ USD}}\ (\approx +\$0.0519)$$
3. **Core Conclusion**:
   $$+\$0.0532\text{ (Taker)} > +\$0.0519\text{ (Maker)}$$
   The commission savings of maker entry ($+\$0.0290$) are completely erased by adverse selection and non-fill drag ($-\$0.0302$), leaving passive execution inferior to aggressive taker execution.

---

## 5. Trade Selection Effects & Gate Hierarchy

Across the six setups:
- **Taker Hurdle Pass Rate**: $1 / 6\ (16.7\%)$ (Only Wide Trend 1000 pts passes).
- **Maker Hurdle Pass Rate**: $2 / 6\ (33.3\%)$ (Swing 400 pts and Wide Trend 1000 pts pass).

### Mathematical Gate Hierarchy
1. $\text{Rule 1}: \text{Fees} / \text{Target} \le 40.0\%$
2. $\text{Rule 2}: \text{Target} \ge 2.0 \times \text{Breakeven} \iff \text{Fees} / \text{Target} \le 50.0\%$
3. $\text{Rule 3}: \text{Post-Fee R:R} \ge 1.25$

Because $40\% < 50\%$, Rule 1 is strictly stricter than Rule 2. Any setup violating Rule 2 will always fail Rule 1 first. Rule 3 filters out trades with tight stops where gross R:R is insufficient to overcome round-trip friction.
