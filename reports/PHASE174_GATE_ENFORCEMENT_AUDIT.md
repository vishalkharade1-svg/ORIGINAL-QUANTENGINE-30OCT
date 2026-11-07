# QUANTENGINE PHASE 174 — FRICTION HURDLE GATE ENFORCEMENT & INTEGRITY AUDIT

**Audit Date**: 2026-10-20  
**Status**: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Target Module**: `core/execution/friction_hurdle_gate.py` & `core/backtesting/post_cost_backtester.py`  
**Auditor**: Independent Quantitative Risk & Release-Integrity Specialist

---

## 1. Executive Summary

The `FrictionHurdleGate` serves as QuantEngine's primary defensive filter against negative-expectancy trade candidates. It intercepts orders **before paper dispatch or simulation execution**, ensuring that commissions, exchange GST, and execution slippage do not consume an unacceptable portion of expected alpha.

This audit provides formal mathematical proofs of rule hierarchy, validates boundary conditions, verifies fail-closed security properties, and confirms zero-bypass enforcement.

---

## 2. Formalization of the Three Hurdle Rules

Every proposed candidate with entry price $P_{\text{entry}}$, target price $P_{\text{target}}$, stop loss price $P_{\text{stop}}$, contract quantity $Q$, and contract multiplier $M$ is evaluated against three non-bypassable rules:

$$\text{Gross Target (USD)} = |P_{\text{target}} - P_{\text{entry}}| \times M \times Q$$
$$\text{Total Fees (USD)} = \text{Fee}_{\text{entry}} + \text{Fee}_{\text{target\_exit}}$$
$$\text{Net Target (USD)} = \text{Gross Target} - \text{Total Fees}$$
$$\text{Breakeven Points} = \frac{\text{Total Fees}}{M \times Q}$$
$$\text{Total Risk (USD)} = (|P_{\text{entry}} - P_{\text{stop}}| \times M \times Q) + \text{Total Fees}$$

### Rule 1: Fee-to-Target Hurdle ($\le 40.0\%$)
$$\text{Fee Ratio} = \left(\frac{\text{Total Fees}}{\text{Gross Target}}\right) \times 100 \le 40.0\%$$

### Rule 2: Breakeven Margin Multiple ($\ge 2.0\times$)
$$\text{Breakeven Multiple} = \frac{\text{Target Points}}{\text{Breakeven Points}} = \frac{\text{Gross Target}}{\text{Total Fees}} \ge 2.0\times$$

### Rule 3: Post-Fee Risk-to-Reward Ratio ($\ge 1.25$)
$$\text{Post-Fee R:R} = \frac{\text{Gross Target} - \text{Total Fees}}{\text{Stop Loss Risk} + \text{Total Fees}} \ge 1.25$$

---

## 3. Mathematical Proof: Rule 1 Strictly Subsumes Rule 2

### Theorem:
Under the exact definitions implemented in `core/execution/friction_hurdle_gate.py`, **Rule 1 strictly subsumes Rule 2**. Any candidate that satisfies Rule 1 is mathematically guaranteed to satisfy Rule 2.

### Proof:
1. Define the fee-to-target fraction as $f = \frac{\text{Total Fees}}{\text{Gross Target}}$.
2. Rule 1 requires:
   $$\text{Fee Ratio} = f \times 100 \le 40.0\% \iff f \le 0.40$$
3. Rule 2 requires:
   $$\text{Breakeven Multiple} = \frac{\text{Target Points}}{\text{Breakeven Points}} = \frac{|P_{\text{target}} - P_{\text{entry}}|}{\frac{\text{Total Fees}}{M \times Q}} = \frac{\text{Gross Target}}{\text{Total Fees}} = \frac{1}{f} \ge 2.0$$
   Taking the reciprocal of both sides (since $f > 0$):
   $$\frac{1}{f} \ge 2.0 \iff f \le \frac{1}{2.0} = 0.50 \iff \text{Fee Ratio} \le 50.0\%$$
4. Since $0.40 < 0.50$, the constraint $f \le 0.40$ is strictly tighter than $f \le 0.50$:
   $$f \le 0.40 \implies f \le 0.50 \implies \text{Rule 2 is ALWAYS satisfied whenever Rule 1 passes.}$$
5. Conversely, if a candidate has a fee ratio of $45\%$ ($f = 0.45$):
   $$\text{Breakeven Multiple} = \frac{1}{0.45} \approx 2.22\times \ge 2.0\times \quad \text{(Passes Rule 2)}$$
   $$\text{Fee Ratio} = 45.0\% > 40.0\% \quad \text{(FAILS Rule 1)}$$
6. Therefore, Rule 1 is strictly dominant over Rule 2. $\blacksquare$

### Independence of Rule 3:
Rule 3 is **NOT** subsumed by Rule 1.
Consider a candidate with target $100$ pts, round-trip fees $40$ pts, and stop loss $50$ pts:
- Fee Ratio: $40 / 100 = 40.0\% \le 40.0\%$ (Passes Rule 1).
- Breakeven Multiple: $100 / 40 = 2.50\times \ge 2.0\times$ (Passes Rule 2).
- Post-Fee R:R:
  $$\text{Post-Fee R:R} = \frac{100 - 40}{50 + 40} = \frac{60}{90} \approx 0.67 < 1.25 \quad \mathbf{(FAILS\ Rule\ 3)}$$
Rule 3 acts as an independent constraint that penalizes wide stop losses even when fee ratios are acceptable.

---

## 4. Boundary Analysis & Threshold Behavior

Deterministic unit tests in `tests/test_phase174_economics_reconciliation.py` verify all boundary conditions:

| Parameter Evaluated | Value | Expected Verdict | Reason |
|---|---|---|---|
| Fee Ratio | $39.99\%$ | **ALLOWED** (if R:R $\ge 1.25$) | Below maximum $40.0\%$ threshold |
| Fee Ratio | $40.00\%$ | **ALLOWED** (boundary equality) | Exactly at $40.0\%$ maximum |
| Fee Ratio | $40.01\%$ | **REJECTED** | Exceeds $40.0\%$ threshold |
| Post-Fee R:R | $1.24$ | **REJECTED** | Below minimum $1.25$ requirement |
| Post-Fee R:R | $1.25$ | **ALLOWED** (boundary equality) | Exactly at $1.25$ requirement |
| Post-Fee R:R | $1.26$ | **ALLOWED** | Above minimum $1.25$ requirement |

---

## 5. Fail-Closed Validation Properties

In Phase 174, `evaluate_friction_hurdle` was fortified with safe input parsing (`_parse_finite_decimal`) to ensure the gate **fails closed** (returns `allowed=False`) on malformed inputs rather than raising unhandled exceptions:

1. **`None` Inputs**: `evaluate_friction_hurdle(None, 82150, 81900)` $\implies$ `allowed=False, reason="missing, malformed, or non-finite inputs"`.
2. **`NaN` / `Inf` Floating Point Values**: `float("nan")`, `float("inf")` $\implies$ `allowed=False`.
3. **Zero Price Distance**: $P_{\text{target}} == P_{\text{entry}}$ $\implies$ `allowed=False, reason="zero distance"`.
4. **Negative Prices**: $P_{\text{entry}} < 0$ $\implies$ `allowed=False, reason="non-positive price level"`.
5. **Non-Positive Quantity**: $Q \le 0$ $\implies$ `allowed=False, reason="non-positive quantity"`.
6. **Class Interface**: Provided `FrictionHurdleGate.evaluate(...)` as a direct wrapper for class-based call sites.

---

## 6. Zero-Bypass Dispatch Verification

In `core/backtesting/post_cost_backtester.py`, the hurdle gate is wired directly into `_friction_hurdle_gate_wrapper` and `evaluate_candidate`.
- Orders rejected by `FrictionHurdleGate` are recorded in `TradeSelectionTally`.
- The backtester simulator completely skips execution simulation for rejected candidates, resulting in **$0.00 realized P&L** and zero order dispatch.
- In `QueueAwarePaperExecutionEngine`, resting limit orders must pass post-only and instrument constraint guards before transitioning from `CREATED` to `RESTING`.
- No alternate dispatch path exists.
