# QUANTENGINE PHASE 175 — CANONICAL P&L RECALCULATION & RESULT AUDIT

**Audit Date**: 2026-10-20  
**Status**: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Precision**: Strict `Decimal` arithmetic, `ROUND_HALF_UP` to 8 decimal places  

---

## 1. Primary Canonical Model ($P_{\text{entry}} = \$82,000.00 \text{ USD}$, Multiplier = $0.001$, $Q = 1$)

### Summary Table across Canonical Variants

| Setup | Target (pts) | Gross Target | Pure Taker Net | Symmetric Maker Realized Cashflow | Symmetric Maker Modeled Net (-2.0 bps) | Asymmetric Maker/Taker Modeled Net | Hurdle Gate Decision |
|---|---|---|---|---|---|---|---|
| **Micro-Scalp** | 4.5 | $+\$0.00450000$ | $-\$0.09226266$ | $-\$0.03420506$ | $-\$0.05060506$ | $-\$0.09340790$ | **REJECTED** (Fee Ratio 860.1% > 40%) |
| **Tight Scalp** | 15.0 | $+\$0.01500000$ | $-\$0.08176885$ | $-\$0.02370754$ | $-\$0.04010754$ | $-\$0.08291640$ | **REJECTED** (Fee Ratio 258.0% > 40%) |
| **Small Intraday** | 50.0 | $+\$0.05000000$ | $-\$0.04678950$ | $+\$0.01128420$ | $-\$0.00511580$ | $-\$0.04794460$ | **REJECTED** (Fee Ratio 77.4% > 40%) |
| **Standard Intraday** | 150.0 | $+\$0.15000000$ | $+\$0.05315150$ | $+\$0.11126060$ | $+\$0.09486060$ | $+\$0.05197530$ | **APPROVED** (Passes Rules 1, 2, 3) |
| **Swing Target** | 400.0 | $+\$0.40000000$ | $+\$0.30300400$ | $+\$0.36120160$ | $+\$0.34480160$ | $+\$0.30176310$ | **APPROVED** (Passes Rules 1, 2, 3) |
| **Wide Trend** | 1000.0 | $+\$1.00000000$ | $+\$0.90264000$ | $+\$0.96106000$ | $+\$0.94466000$ | $+\$0.90161610$ | **APPROVED** (Passes Rules 1, 2, 3) |

---

## 2. Row-by-Row Forensic Component Decomposition ($P_{\text{entry}} = \$82,000.00 \text{ USD}$)

### Row 1: Micro-Scalp (4.5 points)
- **Exit Price**: $\$82,004.50 \text{ USD}$
- **Entry Notional**: $\$82.00000000 \text{ USD}$ | **Exit Notional**: $\$82.00450000 \text{ USD}$
- **Gross P&L**: $+\$0.00450000 \text{ USD}$
- **Pure Taker**:
  - Entry Fee: $\$0.04838000 \text{ USD}$ (Base: $\$0.04100000$, GST: $\$0.00738000$)
  - Exit Fee: $\$0.04838266 \text{ USD}$ (Base: $\$0.04100225$, GST: $\$0.00738041$)
  - Total Fees: $\$0.09676266 \text{ USD}$ | **Realized Cashflow**: $-\$0.09226266 \text{ USD}$
- **Symmetric Maker**:
  - Entry Fee: $\$0.01935200 \text{ USD}$ (Base: $\$0.01640000$, GST: $\$0.00295200$)
  - Exit Fee: $\$0.01935306 \text{ USD}$ (Base: $\$0.01640090$, GST: $\$0.00295216$)
  - Total Fees: $\$0.03870506 \text{ USD}$ | **Realized Cashflow**: $-\$0.03420506 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$ | **Modeled Post-Cost Net**: $-\$0.05060506 \text{ USD}$
- **Gate Evaluation**:
  - Fee / Target Ratio: $\mathbf{860.1\%}$ (Limit: $\le 40.0\%$) $\to$ **REJECTED**
  - Breakeven Multiple: $0.12\times$ (Required: $\ge 2.0\times$) $\to$ **FAIL**
  - Post-Fee R:R: $-0.77$ (Required: $\ge 1.25$) $\to$ **FAIL**

### Row 2: Tight Scalp (15.0 points)
- **Exit Price**: $\$82,015.00 \text{ USD}$
- **Entry Notional**: $\$82.00000000 \text{ USD}$ | **Exit Notional**: $\$82.01500000 \text{ USD}$
- **Gross P&L**: $+\$0.01500000 \text{ USD}$
- **Pure Taker**:
  - Total Fees: $\$0.09676885 \text{ USD}$ | **Realized Cashflow**: $-\$0.08176885 \text{ USD}$
- **Symmetric Maker**:
  - Total Fees: $\$0.03870754 \text{ USD}$ | **Realized Cashflow**: $-\$0.02370754 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$ | **Modeled Post-Cost Net**: $-\$0.04010754 \text{ USD}$
- **Gate Evaluation**:
  - Fee / Target Ratio: $\mathbf{258.0\%}$ (Limit: $\le 40.0\%$) $\to$ **REJECTED**
  - Breakeven Multiple: $0.39\times$ (Required: $\ge 2.0\times$) $\to$ **FAIL**
  - Post-Fee R:R: $-0.44$ (Required: $\ge 1.25$) $\to$ **FAIL**

### Row 3: Small Intraday (50.0 points)
- **Exit Price**: $\$82,050.00 \text{ USD}$
- **Entry Notional**: $\$82.00000000 \text{ USD}$ | **Exit Notional**: $\$82.05000000 \text{ USD}$
- **Gross P&L**: $+\$0.05000000 \text{ USD}$
- **Pure Taker**:
  - Total Fees: $\$0.09678950 \text{ USD}$ | **Realized Cashflow**: $-\$0.04678950 \text{ USD}$
- **Symmetric Maker**:
  - Total Fees: $\$0.03871580 \text{ USD}$ | **Realized Cashflow**: $+\$0.01128420 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$ | **Modeled Post-Cost Net**: $-\$0.00511580 \text{ USD}$
- **Gate Evaluation**:
  - Fee / Target Ratio: $\mathbf{77.4\%}$ (Limit: $\le 40.0\%$) $\to$ **REJECTED**
  - Breakeven Multiple: $1.29\times$ (Required: $\ge 2.0\times$) $\to$ **FAIL**
  - Post-Fee R:R: $0.13$ (Required: $\ge 1.25$) $\to$ **FAIL**

### Row 4: Standard Intraday (150.0 points)
- **Exit Price**: $\$82,150.00 \text{ USD}$
- **Entry Notional**: $\$82.00000000 \text{ USD}$ | **Exit Notional**: $\$82.15000000 \text{ USD}$
- **Gross P&L**: $+\$0.15000000 \text{ USD}$
- **Pure Taker**:
  - Total Fees: $\$0.09684850 \text{ USD}$ | **Realized Cashflow**: $+\$0.05315150 \text{ USD}$
- **Symmetric Maker**:
  - Total Fees: $\$0.03873940 \text{ USD}$ | **Realized Cashflow**: $+\$0.11126060 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$ | **Modeled Post-Cost Net**: $+\$0.09486060 \text{ USD}$
- **Asymmetric Maker Entry / Taker Exit**:
  - Total Fees: $\$0.06782050 \text{ USD}$
  - Non-Fill Opportunity Cost Drag: $-\$0.01380420 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$
  - Modeled Net: $+\$0.05197530 \text{ USD}$ (Truncated: $+\$0.0519$, Rounded: $+\$0.0520$)
- **Gate Evaluation (Symmetric Maker)**:
  - Fee / Target Ratio: $\mathbf{25.8\%}$ (Limit: $\le 40.0\%$) $\to$ **PASS**
  - Breakeven Multiple: $3.87\times$ (Required: $\ge 2.0\times$) $\to$ **PASS**
  - Post-Fee R:R: $1.41$ (for 40 pt stop) $\to$ **APPROVED**

### Row 5: Swing Target (400.0 points)
- **Exit Price**: $\$82,400.00 \text{ USD}$
- **Entry Notional**: $\$82.00000000 \text{ USD}$ | **Exit Notional**: $\$82.40000000 \text{ USD}$
- **Gross P&L**: $+\$0.40000000 \text{ USD}$
- **Symmetric Maker**:
  - Total Fees: $\$0.03879840 \text{ USD}$ | **Realized Cashflow**: $+\$0.36120160 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$ | **Modeled Post-Cost Net**: $+\$0.34480160 \text{ USD}$
- **Gate Evaluation**:
  - Fee / Target Ratio: $\mathbf{9.7\%}$ $\to$ **PASS**
  - Breakeven Multiple: $10.31\times$ $\to$ **PASS**
  - Post-Fee R:R: $1.51$ (for 200 pt stop) $\to$ **APPROVED**

### Row 6: Wide Trend (1000.0 points)
- **Exit Price**: $\$83,000.00 \text{ USD}$
- **Entry Notional**: $\$82.00000000 \text{ USD}$ | **Exit Notional**: $\$83.00000000 \text{ USD}$
- **Gross P&L**: $+\$1.00000000 \text{ USD}$
- **Symmetric Maker**:
  - Total Fees: $\$0.03894000 \text{ USD}$ | **Realized Cashflow**: $+\$0.96106000 \text{ USD}$
  - Adverse Selection Drag: $-\$0.01640000 \text{ USD}$ | **Modeled Post-Cost Net**: $+\$0.94466000 \text{ USD}$
- **Gate Evaluation**:
  - Fee / Target Ratio: $\mathbf{3.9\%}$ $\to$ **PASS**
  - Breakeven Multiple: $25.68\times$ $\to$ **PASS**
  - Post-Fee R:R: $1.78$ (for 500 pt stop) $\to$ **APPROVED**

---

## 3. Diagnostic Comparison Table ($P_{\text{entry}} = \$42,082.00 \text{ USD}$)

For complete audit transparency, this table shows what the exact results would be if an execution occurred under the diagnostic hypothesis price regime of **`$42,082.00 USD`** (Entry Notional = **`$42.08200 USD`**):

| Setup | Target (pts) | Gross Target | Pure Taker RT Fees | Pure Taker Net | Symmetric Maker RT Fees | Symmetric Maker Realized Cashflow | Hurdle Gate Decision |
|---|---|---|---|---|---|---|---|
| **Micro-Scalp** | 4.5 | $+\$0.00450000$ | $\$0.04965935$ | $-\$0.04515935$ | $\$0.01986374$ | $-\$0.01536374$ | **REJECTED** (Fee Ratio 441.4% > 40%) |
| **Tight Scalp** | 15.0 | $+\$0.01500000$ | $\$0.04966254$ | $-\$0.03466254$ | $\$0.01986502$ | $-\$0.00486502$ | **REJECTED** (Fee Ratio 132.4% > 40%) |
| **Small Intraday** | 50.0 | $+\$0.05000000$ | $\$0.04967316$ | $+\$0.00032684$ | $\$0.01986926$ | $+\$0.03013074$ | **APPROVED** (Fee Ratio 39.7% <= 40%)* |
| **Standard Intraday** | 150.0 | $+\$0.15000000$ | $\$0.04970349$ | $+\$0.10029651$ | $\$0.01988139$ | $+\$0.13011861$ | **APPROVED** (Fee Ratio 13.3% <= 40%) |
| **Swing Target** | 400.0 | $+\$0.40000000$ | $\$0.04977931$ | $+\$0.35022069$ | $\$0.01991172$ | $+\$0.38008828$ | **APPROVED** (Fee Ratio 5.0% <= 40%) |
| **Wide Trend** | 1000.0 | $+\$1.00000000$ | $\$0.04996129$ | $+\$0.95003871$ | $\$0.01998451$ | $+\$0.98001549$ | **APPROVED** (Fee Ratio 2.0% <= 40%) |

*\*Notice: Under the $42,082 notional regime, the 50-point setup would pass Rule 1 because round-trip maker fees ($0.01987 USD) consume 39.7% of gross profit ($0.0500 USD), which is below 40.0%. This highlights why using the correct $82,000 market price is economically material: at $82k, the 50-point setup is strictly REJECTED (77.4% fee ratio).*
