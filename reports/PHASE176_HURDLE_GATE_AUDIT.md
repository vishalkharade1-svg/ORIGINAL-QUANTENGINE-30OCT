# PHASE 176 — Hurdle Gate Independent Audit

**Audit Status:** COMPLETE  
**System Posture:** `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Audit Date:** 2026-10-20  
**Input Baseline:** QuantEngine_PHASE175_RELEASE_CANDIDATE.zip  
**SHA-256:** `16aacbde562d3a39078e15d62d120810b2d72b0f426526856fd7d274b16954b4`

---

## 1. Purpose

Independent evaluation of the `FrictionHurdleGate` implementation including:
- Rule correctness and ordering
- Boundary conditions and fail-closed safety
- Rule subsumption proof verification
- Alternate signature correctness (points-based vs price-based)
- Numerical edge cases

---

## 2. Gate Architecture Overview

The `evaluate_friction_hurdle()` function enforces three sequential gates:

| Gate | Rule | Threshold |
|---|---|---|
| Gate 1 | Fee-to-target ratio | `fee_pct <= 40.0%` |
| Gate 2 | Breakeven margin multiple | `target / breakeven >= 2.0×` |
| Gate 3 | Post-fee R:R | `post_fee_rr >= 1.25` |

Gates are **sequential** — a setup failing Gate 1 never reaches Gate 2. If a setup passes all three gates, `HurdleVerdict.allowed = True`.

---

## 3. Rule 1 (Fee-to-Target Ratio) Audit

**Formula:**
```
fee_to_target_pct = (total_round_trip_fees / gross_target) × 100
Gate passes if: fee_to_target_pct <= 40.0
```

**Economic interpretation:** At most 40% of expected gross profit may be consumed by round-trip commissions.

**Boundary case analysis:**

Exact 40% threshold at $82k entry, maker fees, qty=1:
```
gross_target = target_pts × 0.001
fees = ~0.0387
0.0387 / (target_pts × 0.001) = 0.40
target_pts = 0.0387 / 0.0004 = 96.75 pts
```

A target of **96.75 pts** is the boundary. At 97 pts: fee ratio = 39.9% (PASS). At 96 pts: fee ratio = 40.3% (FAIL). The gate is correctly calibrated.

---

## 4. Rule 2 (Breakeven Margin Multiple) Audit

**Formula:**
```
breakeven_pts = total_fees / (multiplier × qty)
gate passes if: target_pts / breakeven_pts >= 2.0
```

**Phase 175 subsumption proof (independently verified here):**

```
breakeven_multiple = target / breakeven_pts
fee_to_target_pct  = fees / gross_target = fees / (target × cm)
                   = breakeven_pts / target
                   = 1 / breakeven_multiple

Therefore:
  fee_to_target_pct <= 0.40
  ⟺ 1 / breakeven_multiple <= 0.40
  ⟺ breakeven_multiple >= 2.50

Rule 2 threshold: breakeven_multiple >= 2.0
Rule 1 implied:  breakeven_multiple >= 2.50

Since 2.50 > 2.00, any setup passing Rule 1 automatically passes Rule 2.
Rule 1 strictly subsumes Rule 2.
```

**Verdict:** Rule 2 is mathematically redundant given Rule 1 with identical parameter values. It is retained for serialized output compatibility. This is correct behavior (retained technical debt). ✅

---

## 5. Rule 3 (Post-Fee R:R) Audit

**Formula:**
```
net_target   = gross_target - total_fees
total_risk   = (risk_pts × cm × qty) + total_fees
post_fee_rr  = net_target / total_risk
Gate passes if: post_fee_rr >= 1.25
```

**Independence from Rule 1:** Rule 3 introduces a new variable (stop_loss distance, `risk_pts`). It cannot be subsumed by Rule 1. Example:

- 100-pt target, 200-pt stop, $82k entry, maker: fee_ratio = 38.7% (PASS Rule 1)  
- `net_target = 0.10 - 0.0387 = 0.0613`  
- `total_risk = 0.200 + 0.0387 = 0.2387`  
- `post_fee_rr = 0.0613 / 0.2387 = 0.257` (FAIL Rule 3)

Rules 1 and 3 are correctly independent. ✅

---

## 6. Fail-Closed Safety Audit

### 6.1 None / Missing Inputs

**Code:** `_parse_finite_decimal(val)` returns `None` for `None` inputs.

```python
if ep is None or tp is None or sp is None or qty is None or cm is None:
    return _fail_closed("Friction hurdle failed: missing, malformed, or non-finite inputs")
```

**Verdict:** Missing inputs trigger fail-closed rejection. ✅

### 6.2 NaN and Infinity

**Code:** `_parse_finite_decimal()` checks `d.is_nan() or d.is_infinite()` → returns `None`.

```python
d = Decimal(str(val))
if d.is_nan() or d.is_infinite():
    return None
```

**Verdict:** NaN and Infinity inputs trigger fail-closed rejection. ✅

### 6.3 Non-Positive Prices

```python
if ep <= Decimal("0") or tp <= Decimal("0") or sp <= Decimal("0"):
    return _fail_closed("Friction hurdle failed: non-positive price level", ...)
```

**Verdict:** Zero or negative price inputs trigger fail-closed rejection. ✅

### 6.4 Zero Target or Stop Distance

```python
target_pts = abs(tp - ep)
risk_pts   = abs(ep - sp)
if target_pts <= Decimal("0") or risk_pts <= Decimal("0"):
    return _fail_closed("Invalid target or stop price (zero distance)", ...)
```

**Verdict:** Entry == target or entry == stop triggers fail-closed rejection. ✅

### 6.5 Division-by-Zero Guard

The `calculate_round_trip()` called within the gate requires strictly positive notional:
```python
if n <= Decimal("0"):
    raise ValueError("Notional must be strictly positive")
```

Since qty and cm are checked for positivity before `calculate_round_trip()` is called, no division by zero can occur in the fee calculation path. ✅

---

## 7. Alternate Signature (Points-Based) Audit

The `evaluate_friction_hurdle()` function supports two call signatures:

**Standard (price levels):**
```python
entry_price=82000.0, target_price=82100.0, stop_price=81950.0
```

**Alternate (explicit points):**
```python
gross_target_points=100.0, round_trip_fee_points=38.70, stop_loss_points=50.0
```

**Alternate path audit:**

```python
fee_to_target_pct = (fee_pts / target_pts) × 100
be_pts = fee_pts  # breakeven = round-trip fee in points
be_mult = target_pts / be_pts
net_pts = target_pts - fee_pts
total_risk_pts = risk_pts + fee_pts
post_fee_rr = net_pts / total_risk_pts
```

**Reproduction (100 pt target, 38.70 fee pts, 50 pt stop):**
```
fee_to_target_pct = 38.70 / 100 × 100 = 38.70% (PASS <= 40%)
be_mult = 100 / 38.70 = 2.584× (PASS >= 2.0×)
net_pts = 100 - 38.70 = 61.30 pts
total_risk_pts = 50 + 38.70 = 88.70 pts
post_fee_rr = 61.30 / 88.70 = 0.691 (FAIL < 1.25)
```

**Verdict:** Alternate path correctly enforces all three gates using pre-computed points. The path handles all fail-closed edge cases identically to the standard path. ✅

---

## 8. `HurdleVerdict` Property Consistency

**Properties that derive from main fields:**

| Property | Formula | Consistent? |
|---|---|---|
| `passed` | `self.allowed` | YES |
| `fee_ratio_pct` | `self.fee_to_target_pct` | YES |
| `breakeven_multiple` | `target_pts / breakeven_pts` (if > 0) | YES |
| `rule1_fee_ratio_pass` | `fee_to_target_pct <= 40.0` | YES |
| `rule2_target_multiple_pass` | `breakeven_multiple >= 2.0` | YES |
| `rule3_post_fee_rr_pass` | `post_fee_rr >= 1.25` | YES |

**Verdict:** All `HurdleVerdict` derived properties are internally consistent. ✅

---

## 9. Summary

| Item | Verdict |
|---|---|
| Gate 1 (fee ratio <= 40%) | CORRECT |
| Gate 2 (multiple >= 2.0x) | CORRECT, SUBSUMED BY GATE 1 |
| Gate 3 (post-fee R:R >= 1.25) | CORRECT AND INDEPENDENT |
| Fail-closed on None | VERIFIED |
| Fail-closed on NaN/Inf | VERIFIED |
| Fail-closed on non-positive prices | VERIFIED |
| Fail-closed on zero target/stop | VERIFIED |
| Division-by-zero safety | VERIFIED |
| Alternate (points) signature | CORRECT |
| HurdleVerdict property consistency | CONSISTENT |
| Rule 1 subsumes Rule 2 (proof) | INDEPENDENTLY VERIFIED |

**Final posture: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`**
