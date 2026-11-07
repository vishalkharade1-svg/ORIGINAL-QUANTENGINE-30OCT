# QUANTENGINE PHASE 183 — STOP-ROUNDING DECISION RECORD & MATHEMATICAL SPECIFICATION

**Phase**: 183  
**Date**: 2026-10-20  
**Status**: APPROVED SPECIFICATION | NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED  
**Release Gate Status**: `HOLD / BLOCKED_EVIDENCE`  

---

## 1. Executive Summary & Root Cause Analysis

During the independent Phase 182 release audit, an apparent contradiction was identified in the narrative adversarial test report:
> "Entry 60,000, Long raw stop 59,500.05, ceiling normalized to 59,500.10, Risk budget 500. Claim: Normalization causes a risk-budget breach."

Independent mathematical evaluation reveals:
- **Raw Distance to Stop**: $60,000.00 - 59,500.05 = 499.95 \text{ USD}$.
- **Raw Gross Loss**: $499.95 \times 1.0 = \$499.95000000$.
- **Normalized Distance (Ceiling)**: $60,000.00 - 59,500.10 = 499.90 \text{ USD}$.
- **Normalized Gross Loss**: $499.90 \times 1.0 = \$499.90000000$.

Under ceiling normalization, gross loss **decreases** from $\$499.95$ to $\$499.90$ (a risk contraction of $\$0.05$). It is mathematically impossible for ceiling normalization to cause a breach of a $\$500$ gross budget when the raw stop was $\$499.95$.

### Forensic Root Cause Determination
The forensic audit determined that this inconsistency resulted from a combination of:
1. **An Inaccurate Narrative Report Description**: The Phase 182 prose summary table stated that ceiling normalization to $59,500.10$ caused the breach. This narrative was mathematically erroneous.
2. **An Imprecise Test Assertion**: The underlying test (`test_scenario_01_raw_within_budget_normalized_exceeds`) did not test ceiling normalization; it applied `policy=TickRoundingPolicy.FLOOR` (which moved the stop to $59,500.00$). Furthermore, it set `budget = 549.25` and asserted `raw_gross_risk_usd < budget` ($499.97 < 549.25$), but normalized gross risk was $\$500.00$, which was *also* below the budget ($500.00 < 549.25$). The test passed only because round-trip *fees* ($49.265$) pushed the total normalized risk ($549.265$) over the budget. Thus, Scenario 1 (normalization expansion) was conflated with Scenario 2 (fee additive breach).
3. **Conceptual Conflation of Risk Measures**: The system conflated **Nominal Dollar Loss at Stop** with **Premature-Trigger (Whipsaw) Probability**.

---

## 2. Formal Tick-Rounding Mathematical Framework

Let tick size be $\Delta > 0$ (e.g. $\Delta = 0.10 \text{ USD}$ for BTCUSD Product ID 84).
Any price $P$ sent to the exchange orderbook must satisfy:
$$P \in \{ k \cdot \Delta \mid k \in \mathbb{Z}^+ \}$$

For an arbitrary unquantized price $P_{\text{raw}} = k \cdot \Delta + r$ where $0 \le r < \Delta$:
- If $r = 0$: $P_{\text{norm}} = P_{\text{raw}}$ (already aligned; zero displacement).
- If $r > 0$: Adjacent tick boundaries are:
  $$P_{\text{floor}} = k \cdot \Delta, \quad P_{\text{ceiling}} = (k + 1) \cdot \Delta$$

---

## 3. Order-Type & Position-Side Semantics

The table below defines the physical effect of tick normalization across every order type and side:

| Order / Position Type | Geometry Constraint | Rounding Policy | Normalized Grid Formula | Distance to Entry / Market | Nominal Cash Loss / Cost | Premature Trigger / Fill Probability |
|---|---|---|---|---|---|---|
| **Long Protective Stop** | $P_{\text{stop}} < P_{\text{entry}}$ | `CONSERVATIVE` (Ceiling) | $P_{\text{ceiling}} = \lceil P_{\text{raw}} / \Delta \rceil \cdot \Delta$ | **Contracts** ($P_{\text{entry}} - P_{\text{norm}} < \Delta P_{\text{raw}}$) | **Decreases** (Loss shrinks) | **Increases** (Tighter stop, higher whipsaw risk) |
| **Long Protective Stop** | $P_{\text{stop}} < P_{\text{entry}}$ | `FLOOR` (Buffer Expansion) | $P_{\text{floor}} = \lfloor P_{\text{raw}} / \Delta \rfloor \cdot \Delta$ | **Expands** ($P_{\text{entry}} - P_{\text{norm}} > \Delta P_{\text{raw}}$) | **Increases** (Loss expands) | **Decreases** (Wider buffer, lower whipsaw risk) |
| **Short Protective Stop** | $P_{\text{stop}} > P_{\text{entry}}$ | `CONSERVATIVE` (Floor) | $P_{\text{floor}} = \lfloor P_{\text{raw}} / \Delta \rfloor \cdot \Delta$ | **Contracts** ($P_{\text{norm}} - P_{\text{entry}} < \Delta P_{\text{raw}}$) | **Decreases** (Loss shrinks) | **Increases** (Tighter stop, higher whipsaw risk) |
| **Short Protective Stop** | $P_{\text{stop}} > P_{\text{entry}}$ | `CEILING` (Buffer Expansion) | $P_{\text{ceiling}} = \lceil P_{\text{raw}} / \Delta \rceil \cdot \Delta$ | **Expands** ($P_{\text{norm}} - P_{\text{entry}} > \Delta P_{\text{raw}}$) | **Increases** (Loss expands) | **Decreases** (Wider buffer, lower whipsaw risk) |
| **Buy Limit Order** | Entry / Maker Bid | `CONSERVATIVE` (Floor) | $P_{\text{floor}} = \lfloor P_{\text{raw}} / \Delta \rfloor \cdot \Delta$ | Moves lower (cheaper) | **Improves** (Pays $\le P_{\text{raw}}$) | **Decreases** (Sits deeper in bid queue) |
| **Sell Limit Order** | Entry / Take Profit | `CONSERVATIVE` (Ceiling) | $P_{\text{ceiling}} = \lceil P_{\text{raw}} / \Delta \rceil \cdot \Delta$ | Moves higher (richer) | **Improves** (Receives $\ge P_{\text{raw}}$) | **Decreases** (Sits deeper in ask queue) |

---

## 4. The Policy Duality: Loss-Cap vs. Buffer-Preservation

The engineering audit establishes two distinct, mutually exclusive interpretations of "conservative" risk management:

### Policy Paradigm A: "Capital-Preservation / Loss-Cap" Policy (Engine Default: `CONSERVATIVE`)
- **Long Stop**: Round UP ($\text{Ceiling}$).
- **Short Stop**: Round DOWN ($\text{Floor}$).
- **Core Invariant**: $\text{Gross Loss}_{\text{norm}} \le \text{Gross Loss}_{\text{raw}}$.
- **Operational Reality**: Normalization *never increases nominal cash loss*. Consequently, under Paradigm A, if raw gross loss is within budget, normalized gross loss is mathematically guaranteed to remain within budget. Normalization can **never** cause a gross loss breach under this policy.
- **Trade-off**: The stop is placed closer to the entry price, sacrificing market noise buffer and increasing the probability of being stopped out prematurely.

### Policy Paradigm B: "Buffer-Preservation / Noise-Immunity" Policy (`FLOOR` for Long, `CEILING` for Short)
- **Long Stop**: Round DOWN ($\text{Floor}$).
- **Short Stop**: Round UP ($\text{Ceiling}$).
- **Core Invariant**: $\text{Stop Distance}_{\text{norm}} \ge \text{Stop Distance}_{\text{raw}}$.
- **Operational Reality**: Preserves the trader's desired noise buffer. However, normalization *always increases nominal cash loss*.
- **Consequence**: A setup whose raw stop was close to the risk budget **will be pushed over the risk budget by normalization**, triggering a fail-closed risk rejection.

---

## 5. Formal Risk Accounting Equations

Let:
- $P_{\text{entry}}$ = Entry fill price
- $P_{\text{stop, norm}}$ = Normalized stop price
- $Q$ = Order quantity in contracts
- $M$ = Contract multiplier in underlying base currency per contract
- Effective Position Size $S = Q \times M$
- $r_{\text{maker}}$ = Maker fee rate inclusive of GST ($0.000236$ = 2.36 bps)
- $r_{\text{taker}}$ = Taker fee rate inclusive of GST ($0.000590$ = 5.90 bps)

### Equations
1. **Gross Stop Loss**:
   $$\text{GrossLoss}_{\text{norm}} = |P_{\text{entry}} - P_{\text{stop, norm}}| \times Q \times M$$

2. **Entry Fee (Maker)**:
   $$\text{Fee}_{\text{entry}} = P_{\text{entry}} \times Q \times M \times r_{\text{maker}}$$

3. **Stop Exit Fee (Taker)**:
   $$\text{Fee}_{\text{exit, norm}} = P_{\text{stop, norm}} \times Q \times M \times r_{\text{taker}}$$

4. **Total Normalized Risk**:
   $$\text{TotalRisk}_{\text{norm}} = \text{GrossLoss}_{\text{norm}} + \text{Fee}_{\text{entry}} + \text{Fee}_{\text{exit, norm}}$$

5. **Risk Expansion**:
   $$\Delta_{\text{expansion}} = \text{GrossLoss}_{\text{norm}} - \text{GrossLoss}_{\text{raw}}$$
   - $\Delta_{\text{expansion}} < 0$: Risk contracted (Stop moved closer to entry).
   - $\Delta_{\text{expansion}} > 0$: Risk expanded (Stop moved farther from entry).

6. **Premature Trigger Displacement**:
   - Long Position: $\Delta_{\text{trigger}} = P_{\text{stop, norm}} - P_{\text{stop, raw}}$
   - Short Position: $\Delta_{\text{trigger}} = P_{\text{stop, raw}} - P_{\text{stop, norm}}$
   - $\Delta_{\text{trigger}} > 0$: Stop is closer to market (Higher whipsaw risk).
   - $\Delta_{\text{trigger}} < 0$: Stop is farther from market (Added buffer).

---

## 6. Worked Examples & Boundary Verifications

### Example 1: Contraction Under `CONSERVATIVE` (Long Position)
- Inputs: $P_{\text{entry}} = 60,000.00$, $P_{\text{stop, raw}} = 59,500.05$, $Q = 1,000$, $M = 0.001$, $\Delta = 0.10$.
- Normalized Stop: $P_{\text{stop, norm}} = 59,500.10$.
- Raw Gross Loss: $(60,000.00 - 59,500.05) \times 1.0 = \$499.95000000$.
- Normalized Gross Loss: $(60,000.00 - 59,500.10) \times 1.0 = \$499.90000000$.
- Risk Expansion: $\$499.90 - \$499.95 = -\$0.05000000$.
- Premature Trigger Delta: $+0.05 \text{ pts}$.
- Total Normalized Risk:
  $$\text{Fee}_{\text{entry}} = 60,000 \times 0.000236 = \$14.16000000$$
  $$\text{Fee}_{\text{exit}} = 59,500.10 \times 0.000590 = \$35.10505900$$
  $$\text{TotalRisk}_{\text{norm}} = 499.90 + 14.16 + 35.105059 = \mathbf{\$549.16505900}$$
- Status: Valid if Budget $\ge \$549.16505900$. Gross risk contracts.

### Example 2: Expansion Under `FLOOR` (Long Position)
- Inputs: Same parameters, but `policy = TickRoundingPolicy.FLOOR`.
- Normalized Stop: $P_{\text{stop, norm}} = 59,500.00$.
- Raw Gross Loss: $\$499.95000000$.
- Normalized Gross Loss: $(60,000.00 - 59,500.00) \times 1.0 = \$500.00000000$.
- Risk Expansion: $\$500.00 - \$499.95 = +\$0.05000000$.
- Premature Trigger Delta: $-0.05 \text{ pts}$ (Buffer increased).
- Total Normalized Risk:
  $$\text{TotalRisk}_{\text{norm}} = 500.00 + 14.16 + (59,500.00 \times 0.000590) = 500.00 + 14.16 + 35.105 = \mathbf{\$549.26500000}$$
- If Budget is calibrated to $\$549.24$:
  - Raw Total Risk = $499.95 + 14.16 + 35.1050295 = \$549.2150295 \le \$549.24$ (Raw WITHIN budget).
  - Normalized Total Risk = $\$549.26500000 > \$549.24$ (Normalized EXCEEDS budget).
- Status: Rejected fail-closed solely due to normalization expansion.

---

## 7. Operational Policy & Release Gate Decision

1. **Production Engine Status**: `NOT_PRODUCTION_READY`.
2. **Strategy Status**: `EDGE NOT ESTABLISHED`.
3. **Release Gate**: `HOLD / BLOCKED_EVIDENCE`.
4. **Policy Verdict**:
   - `core/execution/maker_execution_model.py` and `QueueAwarePaperExecutionEngine` default to `CONSERVATIVE` (Capital-Preservation / Loss-Cap), which ceilings Long stops and floors Short stops.
   - The engine correctly exposes `TickRoundingPolicy.FLOOR` and `TickRoundingPolicy.CEILING` for operators who prioritize noise buffer over strict cash loss contraction.
   - Both paradigms are mathematically sound and deterministic. All boundary behaviors are rigorously tested in `tests/test_phase183_stop_rounding_and_risk_validity.py`.
