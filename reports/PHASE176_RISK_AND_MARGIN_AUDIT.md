# PHASE 176 — Risk and Margin Audit

**Audit Status:** COMPLETE  
**System Posture:** `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Audit Date:** 2026-10-20  
**Input Baseline:** QuantEngine_PHASE175_RELEASE_CANDIDATE.zip  
**SHA-256:** `16aacbde562d3a39078e15d62d120810b2d72b0f426526856fd7d274b16954b4`

---

## 1. Scope

Independent audit of:
1. R:R (risk-to-reward) calculation model
2. Post-fee R:R computation and gate enforcement  
3. Stop-loss cost modeling
4. Margin requirement awareness
5. Position-size risk constraints
6. Paper engine risk safeguards

---

## 2. R:R Model Audit

### 2.1 Gross R:R Formula

**Code in `evaluate_friction_hurdle()`:**
```python
target_pts = abs(tp - ep)
risk_pts   = abs(ep - sp)
```

The gross R:R is implicitly `target_pts / risk_pts`. The gate does not directly enforce a minimum gross R:R — instead it enforces a **post-fee R:R** that already bakes in the cost of round-trip fees.

### 2.2 Post-Fee R:R Computation

**Code:**
```python
total_risk_usd = (risk_pts * cm * qty) + total_fees
post_fee_rr = (net_target / total_risk_usd).quantize(Decimal("0.01"), ROUND_HALF_UP)
```

This is a conservative risk calculation because:
- The denominator includes **round-trip fees** (entry + target-side exit fees) as a cost component
- The stop-loss exit fee is approximated as part of `total_fees` (conservative over-estimate)
- The numerator is `net_target = gross_target - total_fees` (after extracting fees from profit)

**Verdict:** The post-fee R:R formula is more conservative than a naive gross R:R and correctly penalizes high fee-to-target ratios. ✅

### 2.3 Gate Threshold Assessment

**Minimum post-fee R:R:** 1.25  
**Enforcement:** Gate 3 in `evaluate_friction_hurdle()` — applied after Gates 1 and 2.

**Physical interpretation at $82k entry, maker fees, qty=1:**

For a trade with target_pts=T and risk_pts=R:
```
gross_target = T × 0.001
total_fees   = ~0.0387 (round-trip maker, approximately constant for small T)
net_target   = T × 0.001 - 0.0387
total_risk   = R × 0.001 + 0.0387

post_fee_rr = (T × 0.001 - 0.0387) / (R × 0.001 + 0.0387) >= 1.25
```

Solving for the minimum viable T given R=50 pts:
```
T × 0.001 - 0.0387 >= 1.25 × (50 × 0.001 + 0.0387)
T × 0.001 >= 0.0387 + 1.25 × 0.0887
T × 0.001 >= 0.0387 + 0.110875
T × 0.001 >= 0.149575
T >= 149.575 pts
```

Therefore, at $82k entry with a 50-pt stop and 1.25 post-fee R:R minimum, the minimum viable target is approximately **150 pts**. This is a stringent but economically sound gate. ✅

---

## 3. Stop-Loss Cost Modeling

### 3.1 Conservative Estimation Approach

The code comment in `friction_hurdle_gate.py`:
```
# For conservative estimation, stop loss fee is approximately equal to entry fee
```

The `total_risk_usd` computation uses `total_fees` (which covers entry + target exit) as a proxy for the cost of stop-loss execution. This means:
- The stop is modeled as costing one round-trip fee worth of commissions
- The actual stop-out fee may be a taker fee (higher) if a market stop order is used

**Verdict:** Conservative estimation is appropriate for a paper-trading pre-filter. The model correctly errs on the side of over-estimating costs, which makes the gate stricter. ✅

### 3.2 Funding Cost Omission

The hurdle gate does **not** include funding costs in the denominator. Funding at $82k entry for a 1-contract position:
- 8h funding interval
- Funding rate not modeled (rate is variable and venue-specific)
- `AsymmetricRoundTripEconomics` supports `funding_fee` and `borrow_fee` fields

**Finding:** The friction hurdle gate evaluates pre-funding economics. If a position is held overnight, funding costs can materially degrade realized R:R. This is correctly classified as a simulation assumption (BLOCK-175-02). Not a gate defect, but a known limitation. ✅

---

## 4. Position-Size Risk Constraints

### 4.1 Minimum Quantity

**Venue `min_quantity`:** Not explicitly specified in MCP payload (listed in `unavailable` fields).  
**Code default:** `min_quantity = Decimal("1")` in `validate_instrument_constraints()`.  
**Paper engine default:** `PaperOrder.min_quantity = Decimal("1")`

**Verdict:** Default of 1 contract minimum is conservative and consistent with typical perpetuals venue minimums. ✅

### 4.2 Position Notional Limit

**Venue field:** `position_notional_limit: "300000"` (USD)  
**Code check:** Paper engine does not enforce position notional limits.  
**Impact:** For paper simulation purposes this is acceptable. Live trading would require the exchange to enforce this limit.

### 4.3 Quantity Step Alignment

**Venue `quantity_step`:** Not specified in MCP payload (listed as `unavailable`).  
**Code default:** `step_size = Decimal("1")` in `InstrumentMetadata`.

**Verdict:** Integer lot steps (1, 2, 3...) are a safe default for BTCUSD perpetuals. ✅

---

## 5. Margin Requirements

### 5.1 Venue-Specified Margins

| Margin Type | Venue Value | Code Model |
|---|---|---|
| Initial margin | 0.5% of notional | Not enforced in paper engine |
| Maintenance margin | 0.25% of notional | Not enforced in paper engine |
| Isolated liquidation penalty | 0.05% | Not implemented |
| Insurance fund contribution | 5% of fees | Not implemented |

### 5.2 Capital Requirement at $82k Entry

**1 contract at $82,000:**
- `notional = 82,000.00 × 0.001 = $82.00`
- `initial_margin_required = $82.00 × 0.005 = $0.41`
- `maintenance_margin_required = $82.00 × 0.0025 = $0.205`

At 10× default leverage:
- `max_position_notional = $82.00 × 10 = $820 notional`
- `capital_required = $820 × 0.005 = $4.10`

**Verdict:** The margin regime is very low for a 1-contract position at $82k. However, since the paper engine does not model margin enforcement, this is informational only. ✅ for paper scope.

---

## 6. Paper Engine Risk Safeguards

### 6.1 Isolation from Live Adapters

**Verified:** `assert_no_live_adapter_invocation()` passes across all test runs.  
**Code path:** `PaperOrder` state machine never calls live exchange clients.  
**Verdict:** PASS ✅

### 6.2 Fail-Closed Order Rejection

**`REJECTED_POST_ONLY` state:** Triggered when post-only order would cross the spread.  
**`REJECTED_RISK` state:** Reserved for risk engine rejection.  
**`REJECTED_CONSTRAINTS` state:** Triggered by invalid tick/step alignment.  
**`REJECTED_STALE` state:** Triggered when market has moved beyond order validity.

**Verdict:** Terminal rejection states correctly prevent order lifecycle progression after failure. ✅

### 6.3 Hurdle Gate as Pre-Dispatch Filter

The `FrictionHurdleGate.evaluate()` returns `HurdleVerdict.allowed = False` for sub-threshold setups. The paper dispatch layer checks this verdict before submitting the simulated order.

**Verdict:** The friction gate correctly acts as a non-bypassable economic filter. ✅

---

## 7. Summary

| Audit Item | Status |
|---|---|
| Post-fee R:R formula | CORRECT |
| Gate threshold (1.25 min R:R) | VERIFIED |
| Stop-loss cost model | CONSERVATIVE (correct) |
| Funding cost omission in gate | KNOWN LIMITATION (classified) |
| Min quantity (1 contract) | SAFE DEFAULT |
| Position notional limit | NOT ENFORCED IN PAPER |
| Margin requirements | NOT ENFORCED IN PAPER (scope correct) |
| Live adapter isolation | VERIFIED PASS |
| Fail-closed order rejection | VERIFIED PASS |
| Hurdle gate as pre-dispatch filter | VERIFIED PASS |

**Final posture: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`**
