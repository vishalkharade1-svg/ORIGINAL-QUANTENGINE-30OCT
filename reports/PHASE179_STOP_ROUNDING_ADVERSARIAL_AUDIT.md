# QuantEngine Phase 179 — Stop-Rounding Adversarial Audit Report

## Executive Summary

Phase 179 independently audited and stress-tested `normalize_price_to_tick()` and `audit_and_recalculate_stop_risk()` across adversarial boundaries, directional asymmetry, tick-grid quantizations, and post-normalization risk budget recalculations.

---

## 1. Directional Asymmetry and Order Mechanics

| Attribute | Long Position Stop | Short Position Stop |
| :--- | :--- | :--- |
| **Position Direction** | Long (`BUY`) | Short (`SELL`) |
| **Closing Order Side** | `SELL` | `BUY` |
| **Stop Order Type** | Stop-Market / Stop-Limit | Stop-Market / Stop-Limit |
| **Trigger Mechanism** | Mark price $\le$ Stop Price | Mark price $\ge$ Stop Price |
| **Trigger Reference** | Mark Price (preferred to prevent wick manipulation) | Mark Price (preferred to prevent wick manipulation) |
| **Conservative Rounding Policy** | `ROUND_CEILING` (Ceil upward towards entry) | `ROUND_FLOOR` (Floor downward towards entry) |
| **Distance to Entry Impact** | Narrows by $\Delta \le \text{tick\_size}$ | Narrows by $\Delta \le \text{tick\_size}$ |
| **Distance to Current Market** | Narrows by $\Delta \le \text{tick\_size}$ | Narrows by $\Delta \le \text{tick\_size}$ |
| **Planned Gross Loss** | Strictly preserved or reduced ($\text{Loss}_{\text{norm}} \le \text{Loss}_{\text{raw}}$) | Strictly preserved or reduced ($\text{Loss}_{\text{norm}} \le \text{Loss}_{\text{raw}}$) |
| **Premature Trigger Risk** | Increased sensitivity by up to $0.10$ USD | Increased sensitivity by up to $0.10$ USD |

---

## 2. Adversarial Test Matrix & Mathematical Formulations

### A. Mathematical Formulation
For a contract with multiplier $M$ and quantity $Q$:
- **Long Gross Risk:**
  $$\text{Gross Risk}_{\text{raw}} = (P_{\text{entry}} - P_{\text{stop, raw}}) \times M \times Q$$
  $$\text{Gross Risk}_{\text{norm}} = (P_{\text{entry}} - P_{\text{stop, norm}}) \times M \times Q$$
- **Short Gross Risk:**
  $$\text{Gross Risk}_{\text{raw}} = (P_{\text{stop, raw}} - P_{\text{entry}}) \times M \times Q$$
  $$\text{Gross Risk}_{\text{norm}} = (P_{\text{stop, norm}} - P_{\text{entry}}) \times M \times Q$$
- **Total Planned Risk:**
  $$\text{Total Risk}_{\text{norm}} = \text{Gross Risk}_{\text{norm}} + \text{Fee}_{\text{entry}}(\text{Maker}) + \text{Fee}_{\text{stop}}(\text{Taker})$$

### B. Adversarial Boundary Results
1. **Raw Stop Within Budget, Normalized Stop Within Budget:**
   - Long: Entry $82,000, Raw Stop $81,950, Norm Stop $81,950.00. Total risk = $0.1177 USD $\le$ Budget $0.1500 USD $\implies$ `APPROVED`.
2. **Raw Stop Within Budget, Normalized Stop Breaches Budget (Adversarial Rounding Away from Entry):**
   - When policy is set to `FLOOR` on a Long position, $81,900.09 floors down to $81,900.00. Gross loss expands from $0.09991 to $0.10000 USD.
   - Total risk expands to $0.16767 USD, breaching a tight $0.16760 USD budget $\implies$ `REJECTED_RISK`.
3. **Raw Stop Already Outside Budget:**
   - 1000-point stop ($81,000) against $0.2000 USD budget. Gross risk $1.00 USD $\implies$ `REJECTED_RISK`.
4. **Exact Tick Boundary Traversal:**
   - Long at $81,950.10 and Short at $82,050.50 normalize with $\Delta = 0.00$, preserving exact distance $\implies$ `APPROVED`.
5. **Multiple Quantities and Multipliers:**
   - Tested $Q = 10$ ($M = 0.001$) and $Q = 1$ ($M = 0.01$), confirming linear scaling ($0.50 USD gross loss) $\implies$ `APPROVED`.
6. **Zero, Negative, Missing, and Non-Finite Inputs:**
   - Evaluated `0`, negative prices, negative quantities, `NaN`, `Inf`, and `None`. All fail closed deterministically $\implies$ `REJECTED_RISK`.

---

## 3. Critical Disclaimer: Stop Order Execution Realism

> [!WARNING]
> A normalized stop-loss price **DOES NOT** guarantee a maximum realized loss.  
> 
> Stop orders are conditional triggers:
> 1. **Gapping Risk:** If the market gaps through the stop price between orderbook updates, the order triggers and executes at the next available bid/ask, which may be significantly worse than the trigger price.
> 2. **Execution Slippage:** Under high volatility or orderbook illiquidity, crossing market orders sweep multiple depth tiers.
> 3. **Latency:** Network delays between mark price breach and exchange matching engine receipt allow adverse price moves.
> 
> Therefore, post-normalization risk recalculation models **planned conditional risk**, not guaranteed realized loss.
