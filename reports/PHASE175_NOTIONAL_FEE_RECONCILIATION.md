# QUANTENGINE PHASE 175 — NOTIONAL & FEE RECONCILIATION REPORT

**Audit Date**: 2026-10-20  
**Status**: `SIMULATION_ASSUMPTION | NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Auditor**: Quantitative Execution Researcher & Trading-Cost Auditor  

---

## 1. The Notional Discrepancy Analysis

### Mathematical Formulation
For any linear derivative contract with contract multiplier $M$ and contract quantity $Q$:
$$\text{Notional Leg 1 (Entry)} = P_{\text{entry}} \times M \times Q$$
$$\text{Notional Leg 2 (Exit)} = P_{\text{exit}} \times M \times Q = (P_{\text{entry}} + \Delta P) \times M \times Q$$
$$\text{Gross P\&L} = \Delta P \times M \times Q$$

$$\text{Base Commission} = \text{Notional} \times \text{Base Rate}$$
$$\text{Commission Tax (GST)} = \text{Base Commission} \times 0.18$$
$$\text{Total Leg Fee} = \text{Base Commission} \times 1.18 = \text{Notional} \times (\text{Base Rate} \times 1.18)$$

### Comparative Evaluation across Three Price Regimes (50-Point Setup, $Q=1, M=0.001$)

| Parameter | Regime A: Canonical Code ($P_{\text{entry}} = \$82,000.00$) | Regime B: Narrative Header ($P_{\text{entry}} = \$42,082.00$) | Regime C: L2 Observed ($P_{\text{entry}} = \$82,082.50$) |
|---|---|---|---|
| **Entry Price** | `$82,000.00 USD` | `$42,082.00 USD` | `$82,082.50 USD` |
| **Exit Price (50 pts)** | `$82,050.00 USD` | `$42,132.00 USD` | `$82,132.50 USD` |
| **Contract Multiplier** | `0.001 BTC` | `0.001 BTC` | `0.001 BTC` |
| **Contract Quantity** | `1` | `1` | `1` |
| **Leg 1 Notional** | **`$82.00000000 USD`** | **`$42.08200000 USD`** | **`$82.08250000 USD`** |
| **Leg 2 Notional** | **`$82.05000000 USD`** | **`$42.13200000 USD`** | **`$82.13250000 USD`** |
| **Gross P&L** | **`$0.05000000 USD`** | **`$0.05000000 USD`** | **`$0.05000000 USD`** |
| **Maker Leg 1 Fee** | `$0.01935200 USD` | `$0.00993135 USD` | `$0.01937147 USD` |
| **Maker Leg 2 Fee** | `$0.01936380 USD` | `$0.00994315 USD` | `$0.01938327 USD` |
| **Total Round-Trip Maker Fees** | **`$0.03871580 USD`** | **`$0.01987450 USD`** | **`$0.03875474 USD`** |
| **Taker Leg 1 Fee** | `$0.04838000 USD` | `$0.02482838 USD` | `$0.04842868 USD` |
| **Taker Leg 2 Fee** | `$0.04840950 USD` | `$0.02485788 USD` | `$0.04845818 USD` |
| **Total Round-Trip Taker Fees** | **`$0.09678950 USD`** | **`$0.04968626 USD`** | **`$0.09688686 USD`** |
| **Historical Match** | **EXACT MATCH (`0.03871580`)** | Discrepant (0.513x) | Close (+0.1%) |

---

## 2. Invariance and Linearity Proofs

### Proof 1: Invariance of Gross Monetary P&L
Notice that Gross P&L is **strictly invariant** to the underlying price level:
$$\text{Gross P\&L} = (P_{\text{exit}} - P_{\text{entry}}) \times M \times Q = \Delta P \times M \times Q$$
Regardless of whether BTC trades at $\$42,082$ or $\$82,000$, a 50-point move on 1 contract ($0.001 \text{ multiplier}$) yields:
$$50 \times 0.001 \times 1 = \mathbf{\$0.05000000 \text{ USD}}$$

### Proof 2: Direct Linearity of Execution Fees
Because commissions are charged as an ad-valorem percentage of notional, fees scale directly with the price level:
$$\text{Fee}(P) = P \times M \times Q \times \text{Rate} \times 1.18$$
$$\frac{\text{Fee}(P_1)}{\text{Fee}(P_2)} = \frac{P_1}{P_2}$$
Comparing Leg 1 fees between Regime A and Regime B:
$$\frac{\text{Fee}(\$82,000)}{\text{Fee}(\$42,082)} = \frac{0.01935200}{0.00993135} = 1.948576 \dots$$
$$\frac{\$82,000.00}{\$42,082.00} = 1.948576 \dots$$
The ratio matches to the last decimal place.

---

## 3. Forensic Conclusion
1. The historical published round-trip maker fee of **`$0.03871580 USD`** was calculated using **`$82,000.00 USD`** as the entry price.
2. The figure **`$42,082.00 USD`** was an erroneous transcription of the L2 order book price **`$82,082.50 USD`**.
3. Under an actual $\$42,082.00$ entry price, round-trip maker fees would be **`$0.01987450 USD`** ($\approx 51.3\%$ of the reported fee).
4. Both calculations are deterministic, verified, and property-tested in [`tests/test_phase175_instrument_economics.py`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/tests/test_phase175_instrument_economics.py).
