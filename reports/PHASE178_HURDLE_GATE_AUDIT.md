# QuantEngine Phase 178 — Hurdle Gate Subsumption & Enforcement Audit

## Executive Summary

Phase 178 re-verified the formal proof of subsumption for `FrictionHurdleGate` and audited the pre-order dispatch boundary to guarantee that candidates rejected by the hurdle gate cannot reach execution.

---

## 1. Mathematical Subsumption Proof

Under standard linear definitions:
- **Fee Ratio**: $\frac{\text{Round-Trip Fees}}{\text{Gross Target}} \le 40.0\%$
- **Target Multiple**: $\frac{\text{Gross Target}}{\text{Round-Trip Fees}} \ge 2.00\times$

Because $\text{Target Multiple} = \frac{1}{\text{Fee Ratio}}$:
$$\text{Fee Ratio} \le 40.0\% \iff \text{Target Multiple} \ge \frac{1}{0.40} = 2.50\times$$
Since $2.50\times > 2.00\times$, whenever Rule 1 passes, Rule 2 is unconditionally satisfied.

---

## 2. Dispatch Boundary Verification

1. In `core/backtesting/post_cost_backtester.py` and the live runtime decision loops, the `FrictionHurdleGate.evaluate()` verdict is evaluated before any order object is constructed.
2. If `verdict.allowed == False`, execution halts immediately.
3. No alternate code branch or retry mechanism exists that can bypass a rejected hurdle verdict.
4. Tick normalization and stop adjustment cannot make an otherwise rejected candidate executable without rerunning risk and friction checks.
