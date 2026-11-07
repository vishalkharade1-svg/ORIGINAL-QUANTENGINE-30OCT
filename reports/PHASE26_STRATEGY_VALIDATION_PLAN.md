# Phase 26 — Strategy Validation Plan

**Status:** PROPOSED (requires owner review)
**Release gate:** HOLD
**Live/testnet execution:** NOT AUTHORIZED
**Purpose:** define the next legitimate evidence path after Phase 26 proved
that the frozen `BREAKOUT_CONTINUATION` entry model cannot satisfy the
unchanged 1:6 realized-RR floor on the certified OOS.

This plan is **not** a license to trade, and it does not modify the frozen
strategy. It preregisters new hypothesis families for evaluation on genuinely
unseen data. No parameter below may be changed after evaluation begins.

---

## 1. What Phase 26 established (and what it did not)

Established:

1. The zero-fill outcome is fully explained and legitimate under the frozen
   rules: 30/32 fill attempts refused by the 1:6 realized-RR floor, 2/32
   refused because the next open was already beyond the take-profit.
2. The fill path works: the same code fills twice on the extended dataset
   (actual RR 9.57 and 34.74) and books PnL and funding.
3. The failure is structural: the median trigger occurs 82.8% of the way to
   target, and the fill lands a median of 50 initial stop-widths beyond the
   entry. Creation-time RR (21–363) is not the binding constraint; realized
   RR (max 2.94) is.
4. Funding evidence is now complete (529 hourly events, zero head gap).

Not established:

- No edge, no profitability, no production readiness.
- No evidence that any replacement entry model will work.
- The certified OOS is now **seen data**. It cannot be used to select, tune
  or rank a replacement.

---

## 2. Non-negotiable rules

- The frozen strategy, its thresholds, and the 1:6 risk floor remain unchanged
  in this phase. New designs are separate hypothesis families with their own
  identities.
- The certified OOS set and the extended top-up are **seen**. Any new family
  must be evaluated on data that ends after every dataset used through Phase
  30 (last timestamp 2026-09-26T12:55Z).
- All families are preregistered before the first evaluation run. Every run is
  logged, including failures. No family may be silently dropped after peeking.
- No live or testnet orders during research. No credential-bearing code paths.
- Costs and funding are mandatory and must be attributed; zero-cost totals are
  never accepted as evidence.
- If the preregistered sample gate is missed, the verdict is
  `INSUFFICIENT_SAMPLE`, not "no edge" and definitely not "edge".
- One position at a time; no pyramiding, no martingale, no post-hoc stop
  widening.

---

## 3. Data governance

| Item | Requirement |
|---|---|
| Source | Delta Exchange `BTCUSD` perpetual, 1m |
| Holdout | Strictly after 2026-09-26T12:55Z; no overlap with any prior phase |
| Duration | ≥ 9 months or until ≥ 60 completed trades, whichever is later |
| Integrity | No gaps, duplicates, non-monotonic timestamps; OHLC consistency; Gate-A strict |
| Partition | Research/dev split inside the new window only (e.g., 60/40 by time), with the final 40% untouched until the family is frozen |
| Funding | Aligned-start capture, strict hourly continuity, zero head/tail gaps |
| Reference | New dataset identity + file hashes recorded before evaluation |
| Reuse | The certified Phase-18/Phase-30 sets remain evidence-only forever |

Data acquisition is a separate, owner-visible step. Until it exists, this plan
is blocked at Phase V0.

---

## 4. Preregistered hypothesis families

All families use the existing research executor patterns, the same 6-period
cold-start structure, one position at a time, next-bar execution where stated,
and conservative intrabar rules. Families differ only in the dimensions
listed; everything else is held fixed.

### H26-A — `LIMIT_RETEST` (primary candidate)

- **Rationale:** entering at the broken level instead of after the breakout
  preserves the original stop distance and therefore the executable RR.
- **Trigger:** same breakout condition as the frozen model (close beyond the
  level, RULE 2), but no immediate market fill.
- **Order:** buy/sell limit at the broken level (the level price, no offset).
- **Validity:** up to `MAX_WAIT_BARS=30`; cancel on structural invalidation.
- **Stop:** the original structural stop used at order creation.
- **Target:** the original structural target, provided the RR at the limit is
  ≥ 6.0; otherwise the setup is skipped at creation (no target stretching).
- **Fill model:** limit fills only if the bar trades through the level by at
  least one tick and the level is not gapped through in the adverse direction;
  fill price = limit (no price improvement). If the bar opens beyond the
  target side of the limit, the order is not filled at the limit.
- **Exit:** stop, target, or time stop; intrabar stop-first when both are
  touched.

### H26-B — `BREAKOUT_ATR_6R` (secondary candidate)

- **Rationale:** keep breakout timing but make risk and reward self-consistent
  at the fill instead of relying on a distant level target.
- **Trigger:** same breakout condition; entry at the next bar open.
- **Stop:** fill − 1.5 × ATR14 (long) / fill + 1.5 × ATR14 (short), fixed at
  fill.
- **Target:** fill + 9.0 × ATR14 (long) / fill − 9.0 × ATR14 (short), i.e.
  exactly 6:1 at fill.
- **Exit:** stop, target, or 30-bar time stop; stop-first if both touched.
- **Explicit:** ATR uses only completed bars; no lookahead.

### H26-C — `RETEST_ATR_6R` (exploratory)

- **Rationale:** combine level retest with volatility-scaled risk.
- **Trigger:** same breakout condition; limit at the broken level.
- **Stop:** level − 1.5 × ATR14 (long) / level + 1.5 × ATR14 (short).
- **Target:** level + 9.0 × ATR14 (long) / level − 9.0 × ATR14 (short).
- **Fill/validity:** same as H26-A.
- **Status:** exploratory; lower prior; included to test the interaction, not
  to maximize the number of candidates.

### H26-D — `NO_TRADE` (control)

- Zero exposure; used to verify cost/funding attribution plumbing and to
  anchor reporting. It cannot "win", but its inclusion prevents the illusion
  that a positive number is automatically meaningful.

**Multiplicity control:** three candidate families plus one control. Report all
results; use Holm correction at family-wise α = 0.05 for the primary
expectancy test. No family may be promoted on a secondary metric alone.

---

## 5. Evaluation protocol

1. **Freeze the implementation.** Record strategy identity, file hashes, config
   snapshot and data identity before the first run. Any change after freezing
   invalidates the run.
2. **Per-period runs first.** Six cold-start periods over the new window; the
   global continuous run is a sanity check only, never the primary evidence.
3. **Canonical accounting.** Use the existing order lifecycle and accounting
   modules; do not reimplement fills, RR or PnL.
4. **Conservative fills.**
   - Limit orders: require trade-through by ≥ 1 tick; fill at the limit, no
     price improvement; queue position ignored (documented optimistic
     assumption).
   - Stops: if stop and target are both touched in the same bar, assume the
     stop first.
   - No intrabar perfect-fill assumptions.
5. **Costs.** Apply all four preregistered 11F ladders (A–D) to every family.
   Report gross, each cost component, and net separately. Venue fees remain a
   configured assumption until the owner supplies the schedule.
6. **Funding.** Apply only at settlement timestamps inside holdings; use the
   aligned Phase-26 capture pattern; reject any schedule with a head/tail gap.
7. **Minimum sample.** ≥ 60 completed trades and trades in ≥ 5 of 6 periods.
   Between 30 and 59 trades the verdict is `INSUFFICIENT_SAMPLE`; below 30 the
   family is `REJECTED_NO_TRADES`, not "no edge".
8. **Primary test.** Net expectancy per trade after all costs; 10,000-sample
   block bootstrap by period; require the 95% lower bound > 0.
9. **Secondary gates (all required).** Profit factor > 1.2; max drawdown
   ≤ 20% of starting balance; no single period contributes > 50% of net
   profit; median realized RR ≥ 4.5; complete funding/cost attribution.
10. **Stability.** Repeat on the held-out 40% without refitting. A family that
    passes only in-sample is rejected.
11. **Confirmation.** Any promoted family requires a second, disjoint unseen
    window before a testnet proposal.

---

## 6. Decision rules

| Outcome | Verdict |
|---|---|
| Gates met on both windows | `CANDIDATE_FOR_FORWARD_VALIDATION` |
| Sample met but lower CI ≤ 0 or any secondary gate fails | `EDGE_NOT_ESTABLISHED` |
| 30–59 trades | `INSUFFICIENT_SAMPLE` (acquire more unseen data) |
| < 30 trades | `REJECTED_NO_TRADES` |
| Data/funding integrity violation | `INVALID_EVIDENCE` (rerun after repair) |
| Implementation identity changed mid-run | `INVALID_EVIDENCE` |

A `CANDIDATE_FOR_FORWARD_VALIDATION` verdict does not authorize testnet. It
authorizes an owner review and, only with written approval, a minimal testnet
phase with hard limits.

---

## 7. Testnet progression (owner-gated)

Prerequisites: two independent unseen windows pass; owner authorization;
credential rotation evidence; fee schedule; instrument metadata; kill switch;
daily loss cap; monitoring and incident runbook.

Constraints: minimum size, one position, no leverage escalation, no automated
promotion, immediate halt on any reconciliation mismatch. Production remains
out of scope.

---

## 8. Reporting

Every run produces a machine-readable artifact with:
dataset identity, config snapshot, implementation hashes, all per-order
records, full cost/funding attribution, per-period and global funnels, primary
and secondary metrics, multiplicity adjustment, and an explicit verdict from
the table above. Evidence classes must distinguish exchange-sourced data,
configured assumptions, and synthetic fixtures.

The Phase-26 artifacts (`PHASE26_ORDER_LIFECYCLE.json`,
`PHASE26_OOS_REEVALUATION.json`, funding evidence) are the reference format.

---

## 9. Non-goals

- No retuning of the frozen strategy.
- No gate relaxation to manufacture fills.
- No reuse of the certified OOS for selection.
- No profitability claim from the extended dataset's two fills.
- No live trading under this plan.

---

## 10. Sequence

| Step | Deliverable | Gate |
|---|---|---|
| V0 | Owner approval + new data acquisition | plan accepted; data integrity pass |
| V1 | Preregistration freeze (families, parameters, metrics) | hashes recorded |
| V2 | Per-period evaluation, all cost ladders | artifacts complete |
| V3 | Held-out 40% confirmation | no refitting |
| V4 | Second unseen window | independent replication |
| V5 | Owner review | testnet decision (still NOT AUTHORIZED until then) |

Until V0–V5 complete, the release gate remains **HOLD** and edge remains
**NOT ESTABLISHED**.
