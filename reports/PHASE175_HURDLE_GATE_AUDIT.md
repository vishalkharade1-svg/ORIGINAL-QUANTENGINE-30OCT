# QUANTENGINE PHASE 175 — FRICTION HURDLE GATE & DISPATCH INTEGRITY AUDIT

**Audit Date**: 2026-10-20  
**Status**: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Target Module**: [`core/execution/friction_hurdle_gate.py`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/core/execution/friction_hurdle_gate.py)  

---

## 1. Rule Architecture and Evaluation Hierarchy

The `FrictionHurdleGate` evaluates prospective order signals using three core economic rules:
1. **Rule 1 (Fee Ratio Hurdle)**:
   $$\text{Fee-to-Gross Target Ratio} = \frac{\text{Round-Trip Fees (USD)}}{\text{Gross Target (USD)}} \le 40.0\%$$
2. **Rule 2 (Breakeven Margin Multiple Hurdle)**:
   $$\text{Target Multiple} = \frac{\text{Gross Target Points}}{\text{Breakeven Hurdle Points}} \ge 2.0\times$$
3. **Rule 3 (Post-Fee Reward-to-Risk Hurdle)**:
   $$\text{Post-Fee Reward-to-Risk} = \frac{\text{Gross Target} - \text{Round-Trip Fees}}{\text{Gross Stop Loss} + \text{Round-Trip Fees}} \ge 1.25$$

---

## 2. Mathematical Proof of Rule 1 Subsumption of Rule 2

### Definitions in Codebase
In [`maker_execution_model.py`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/core/execution/maker_execution_model.py#L254-L256):
$$\text{Breakeven Points} \equiv \frac{\text{Total Fees (USD)}}{\text{Contract Multiplier} \times \text{Quantity}}$$
$$\text{Gross Target Points} \equiv \frac{\text{Gross Target (USD)}}{\text{Contract Multiplier} \times \text{Quantity}}$$

### Algebraic Substitution
Dividing Gross Target Points by Breakeven Points:
$$\text{Target Multiple} = \frac{\text{Gross Target Points}}{\text{Breakeven Points}} = \frac{\frac{\text{Gross Target (USD)}}{M \cdot Q}}{\frac{\text{Total Fees (USD)}}{M \cdot Q}} = \frac{\text{Gross Target (USD)}}{\text{Total Fees (USD)}} = \frac{1}{\text{Fee-to-Gross Target Ratio}}$$

### Evaluation of Thresholds
- **Rule 2 condition**:
  $$\text{Target Multiple} \ge 2.0 \iff \frac{1}{\text{Fee Ratio}} \ge 2.0 \iff \text{Fee Ratio} \le \frac{1}{2.0} = 50.0\%$$
- **Rule 1 condition**:
  $$\text{Fee Ratio} \le 40.0\% \implies \text{Target Multiple} \ge \frac{1}{0.40} = 2.50\times$$

### Conclusion
Because $2.50\times \ge 2.00\times$, **any trade that satisfies Rule 1 automatically satisfies Rule 2 with a safety buffer of at least $0.50\times$**. Rule 2 can never independently reject a trade that has passed Rule 1.

### Policy on Rule 2 Retention
While mathematically subsumed, Rule 2 is **explicitly retained** in the codebase for:
1. **Backwards Compatibility**: Existing test assertions and external monitoring consumers rely on serialized fields (`breakeven_multiple`, `breakeven_points`).
2. **Diagnostic Transparency**: Clear reporting to operators of the exact margin above breakeven.
3. **Defensive Invariant**: Guarding against potential future refactoring where breakeven incorporates non-fee terms (e.g., funding or slippage).

---

## 3. Independence of Rule 3

Rule 3 evaluates post-fee reward-to-risk. Unlike Rule 2, Rule 3 introduces an independent dimensional variable: **the stop loss distance ($\text{risk\_points}$)**.

Let $F$ be total round-trip fees, $T$ be gross target, and $R$ be gross risk.
$$\text{Post-Fee R:R} = \frac{T - F}{R + F} \ge 1.25$$
$$T - F \ge 1.25 R + 1.25 F \implies T \ge 1.25 R + 2.25 F$$
$$R \le \frac{T - 2.25 F}{1.25} = 0.80 T - 1.80 F$$

Even if a trade passes Rule 1 with a fee ratio of $25.0\%$ ($F = 0.25 T$):
$$R \le 0.80 T - 1.80 (0.25 T) = 0.80 T - 0.45 T = 0.35 T$$
If the trader sets a stop loss wider than $0.35 \times \text{Target}$, the trade will pass Rule 1 and Rule 2, but **FAIL Rule 3**.
Thus, Rule 3 is an **independent, binding economic constraint**.

---

## 4. Fail-Closed Boundaries & Safety Verification

The gate enforces fail-closed behavior via `_parse_finite_decimal`:
- `None` input $\to$ Immediate rejection (`HurdleVerdict.allowed = False`).
- `NaN` or `Infinity` $\to$ Immediate rejection.
- Negative price or negative quantity $\to$ Immediate rejection.
- Zero price distance (target = entry or stop = entry) $\to$ Immediate rejection.
- Zero contract multiplier $\to$ Immediate rejection.

### Dispatch Boundary Isolation
- In [`core/paper_trading/paper_trading_engine.py`](file:///F:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/core/paper_trading/paper_trading_engine.py#L32), when `evaluate_friction_hurdle` returns `allowed == False`, execution halts immediately. No order is constructed or added to the book.
- `assert_no_live_adapter_invocation()` is verified across all test executions. Zero network requests or live exchange orders can occur.
