# QuantEngine Phase 177 — Contract Semantics Audit

## Executive Summary

This report documents the independent verification of contract semantics for Delta Exchange India BTCUSD (Product ID 84), audited against authoritative venue payloads and production mathematical implementations.

---

## 1. Authoritative Contract Specifications

Source: `data/fixtures/delta/delta_mcp_public_products_20260925.json` (Product ID 84):

| Specification Dimension | Venue Value | Model Implementation | Verification Status |
| :--- | :--- | :--- | :--- |
| **Product ID** | `84` | `84` | `VERIFIED` |
| **Symbol** | `BTCUSD` | `BTCUSD` | `VERIFIED` |
| **Contract Value (Multiplier)** | `0.001` BTC | `Decimal("0.001")` | `VERIFIED` |
| **Contract Unit** | `BTC` | `BTC` | `VERIFIED` |
| **Quoting Currency** | `USD` | `USD` | `VERIFIED` |
| **Settlement Currency** | `USD` | `USD` | `VERIFIED` |
| **Payoff Structure** | `vanilla` (Linear) | Linear Payoff | `VERIFIED` |
| **Quanto Status** | `False` | `False` | `VERIFIED` |
| **Tick Size** | `0.1` USD | `Decimal("0.10")` | `VERIFIED` |
| **Quantity Step** | `1` contract | `Decimal("1")` | `VERIFIED` |
| **Minimum Quantity** | `1` contract | `Decimal("1")` | `VERIFIED` |
| **Maker Commission Rate** | `0.0002` (2.0 bps) | `Decimal("0.0002")` | `VERIFIED` |
| **Taker Commission Rate** | `0.0005` (5.0 bps) | `Decimal("0.0005")` | `VERIFIED` |

---

## 2. Linear Payoff & Dimensional Analysis

### Payoff Formula
$$\text{Gross P\&L (USD)} = (P_{\text{exit}} - P_{\text{entry}}) \times M \times Q$$
Where:
- $P_{\text{exit}}, P_{\text{entry}}$ are in $\text{USD} / \text{BTC}$
- $M$ is the contract multiplier: $0.001\ \text{BTC} / \text{contract}$
- $Q$ is the position size in $\text{contracts}$

### Dimensional Verification
$$\left[\frac{\text{USD}}{\text{BTC}}\right] \times \left[\frac{\text{BTC}}{\text{contract}}\right] \times [\text{contracts}] = [\text{USD}]$$
Dimensional consistency is verified. The contract is strictly linear and non-quanto.

### Independent Mathematical Reproduction
Evaluated against `calculate_round_trip()`:
1. **Long Position Gain**: Entry \$82,000.00, Exit \$82,150.00, Qty 5, Multiplier 0.001:
   - $(82150 - 82000) \times 0.001 \times 5 = +0.75\ \text{USD}$ (Matches production `gross_pnl = 0.75000000`)
2. **Long Position Loss**: Entry \$82,000.00, Exit \$81,850.00, Qty 5, Multiplier 0.001:
   - $(81850 - 82000) \times 0.001 \times 5 = -0.75\ \text{USD}$ (Matches production `gross_pnl = -0.75000000`)
3. **Fractional Quantity**: Entry \$82,000.00, Exit \$82,150.00, Qty 0.5, Multiplier 0.001:
   - $(82150 - 82000) \times 0.001 \times 0.5 = +0.075\ \text{USD}$ (Matches production `gross_pnl = 0.07500000`)
