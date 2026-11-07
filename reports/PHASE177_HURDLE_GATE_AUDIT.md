# QuantEngine Phase 177 — Hurdle Gate Subsumption & Boundary Audit

## Executive Summary

This report delivers a rigorous mathematical and implementation audit of `FrictionHurdleGate` (`core/execution/friction_hurdle_gate.py`). It formally proves that Rule 1 strictly subsumes Rule 2 under standard default parameters, investigates boundary behavior, and certifies fail-closed dispatch protection.

---

## 1. Formal Proof of Subsumption: Rule 1 vs. Rule 2

### Definitions:
- Gross Target: $G = \text{target\_points} \times M \times Q$
- Total Round-Trip Fees: $F$
- Breakeven Points: $BE = \frac{F}{M \times Q}$
- Target Multiple:
  $$\text{Target Multiple} = \frac{\text{target\_points}}{BE} = \frac{\text{target\_points} \times M \times Q}{F} = \frac{G}{F}$$
- Fee Ratio:
  $$\text{Fee Ratio} = \frac{F}{G} = \frac{1}{\text{Target Multiple}}$$

### Rules:
- **Rule 1 (Fee Ratio Hurdle)**:
  $$\text{Fee Ratio} \le 40.0\% \iff \frac{F}{G} \le 0.40 \iff \frac{G}{F} \ge \frac{1}{0.40} = 2.50\times$$
- **Rule 2 (Breakeven Margin Multiple Hurdle)**:
  $$\text{Target Multiple} \ge 2.00\times \iff \frac{G}{F} \ge 2.00\times$$

### Subsumption Theorem:
Because $2.50 > 2.00$:
1. Whenever Rule 1 passes ($\frac{G}{F} \ge 2.50$), Rule 2 is guaranteed to pass ($\frac{G}{F} \ge 2.50 > 2.00$).
2. Whenever Rule 2 fails ($\frac{G}{F} < 2.00$), Rule 1 has already failed ($\frac{G}{F} < 2.00 < 2.50$).
3. Under default parameters, there is no scenario where Rule 1 passes but Rule 2 fails. Rule 1 strictly subsumes Rule 2.

### Rationale for Retaining Both Rules:
1. **Configurable Independence**: Operators may independently adjust `min_breakeven_margin_multiple` (e.g. to $3.0\times$), in which case Rule 2 becomes the stricter binding constraint.
2. **Contract Compatibility**: Serialized reports, downstream consumers, and historical test contracts check `HurdleVerdict.rule2_target_multiple_pass`. Removing Rule 2 would break external contract expectations.
3. **Conclusion**: Retained as technical debt (`BLOCK-177-08`).

---

## 2. Rule 3: Post-Cost Reward-to-Risk

Rule 3 evaluates:
$$\text{Post-Fee R:R} = \frac{G - F}{\text{Stop Risk (USD)} + F} \ge 1.25$$
This is an independent binding constraint that incorporates the stop-loss distance. Even if a setup satisfies Rule 1 ($G/F \ge 2.5$), a wide stop-loss will cause Rule 3 to reject the trade.

---

## 3. Boundary & Edge Case Behavior

Tested in `tests/test_phase177_tick_remediation.py`:
- Fee Ratio = 40.00% -> `ALLOWED`
- Fee Ratio = 40.01% -> `REJECTED` (Rule 1 fails)
- Post-Fee R:R = 1.25 -> `ALLOWED`
- Post-Fee R:R = 1.24 -> `REJECTED` (Rule 3 fails)
- Zero Fees -> `ALLOWED`
- Maker Rebates (negative fee) -> `ALLOWED`
- Non-finite or invalid inputs (None, NaN, $\pm\infty$, $\le 0$ prices, $\le 0$ quantities, zero target distance) -> `FAIL CLOSED` immediately.
