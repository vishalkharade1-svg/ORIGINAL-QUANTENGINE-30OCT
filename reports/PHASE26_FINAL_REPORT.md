# Phase 26 — Zero-Fill Root-Cause Investigation and Evidence Recovery

**Status:** COMPLETE (investigation) / GATES UNCHANGED
**Release gate:** HOLD
**Edge:** NOT ESTABLISHED
**Testnet/live execution:** NOT AUTHORIZED (none attempted; no orders placed)
**Zero-fill classification:** `LEGITIMATE_NO_FILL_OUTCOME` (confidence 1.0)
**Trading-logic changes:** none
**Evidence repairs:** opt-in lifecycle tracing; aligned-start funding recapture

---

## 1. Executive summary

The certified Phase-18 frozen OOS produced 32 orders and 0 fills. Phase 26
instrumented the canonical executor and traced every order end to end. The
zero-fill outcome is fully explained:

- **32/32 orders triggered** and each reached exactly one next-bar-open fill
  attempt. No order was rejected at creation, unfilled for lack of eligibility,
  or blocked by capacity.
- **30/32 fill attempts were refused by the frozen-era 1:6 realized-RR floor.**
  The breakout-continuation entry fills only after price has closed beyond the
  entry level. By then the stop is far from the fill and the remaining reward
  is small: the executable RR at the attempt was 0.009–2.94 (median 0.306),
  never near 6.
- **2/32 fill attempts were refused because the next open was already beyond
  the take-profit** (`directional_geometry_ok` false; the log verb
  `ORDER_SKIPPED_INVERTED_FILL` names the shared geometry gate, not a stop
  gap). 0 attempts gapped through the stop.
- **The fill path is not broken.** On the extended dataset the same frozen
  code fills twice with actual RR 9.57 and 34.74 and books trades; funding is
  applied to the held position. The certified dataset simply never presents a
  trigger whose executable geometry satisfies the unchanged 1:6 floor.

The mechanism is structural, not accidental: the median trigger occurs with
price already 82.8% of the way from the order's entry level to its target,
and the fill lands a median of 50 initial stop-widths beyond the entry. For a
tight-stop/far-target order (creation-time RR 21–363), any confirmed breakout
destroys realized RR. This is an **entry-model vs risk-floor incompatibility**,
not a software defect, and it must not be "fixed" by loosening the gate or
retuning against this OOS set.

A separate evidence defect was confirmed and repaired: the Phase-25 funding
capture started at 09:45Z, inside an 8-hour funding block, and Delta's public
endpoint drops the partial leading block, silently omitting six genuine
settlements (10:00–15:00Z). The aligned recapture closes the 22,500-second
head gap to zero and binds NEW artifacts to both frozen datasets. Phase-25
artifacts are untouched.

---

## 2. Constraints honored

- No live or testnet order was placed; no credentials were used for trading.
- No strategy logic, threshold, entry model or fill model was changed.
- No parameter was tuned or selected against the frozen OOS data.
- The certified datasets and all prior evidence were preserved byte-for-byte.
- Tests and guards were not weakened.
- Secrets were not printed; the `.env` finding remains owner-owned and redacted.
- New evidence lives under `reports/`; `git status -- research/` remains empty.

---

## 3. Baseline and provenance

| Item | Value |
|---|---|
| Branch / HEAD | `main` / `ffefa14a8729f6d2160db3735a06257cbb6ab48b` |
| Certified protocol | Phase 18 (6 cold-start periods + global run), Phase 22-certified |
| Certified commit recorded | `6eb35d8` (not an ancestor of HEAD; harness absent there) |
| Certified dataset | `data/history/BTCUSDT_1m_phase17_fresh.json` |
| Dataset identity / file sha256 | `247d8f11…c54` / `986fdae1…ef2ef` |
| Rows / span | 11,461 / 1788601500..1789289100 (Gate-A strict, 1788601440) |
| Extended dataset (transparency only) | `BTCUSDT_1m_oos_topup.json`, identity `520b849b…10b0`, 30,247 rows |
| Current strategy core | `26c2bead…c9666` |
| Current runtime infrastructure | `997a21f2…96294` |
| Current legacy 9-file pin (raw) | `473e5942…fc990` (does NOT match recorded `c52e648…3d5a6`) |
| Current legacy 9-file pin (canonical LF) | `05986916…5afda` |
| Phase-18 recorded artifact | `research/results/phase18_oos_validation.json`, sha16 `95cef0271ae746f2` |
| Phase-25 recorded artifact | `research/results/phase25_frozen_oos_validation.json`, sha16 `31c1184a13b229d4` |
| Phase-30 recorded artifact | `research/results/phase30_oos_evidence_accumulation.json`, sha16 `3e84879c1738fac2` |
| Phase-25 funding artifacts | `67c33b5538994d18` (OOS), `494d17a2821e6c82` (Phase 18) |

**Revision assessment.** The certified funnel is reproduced *behaviorally*
count-for-count at HEAD. Byte-identical replay at the recorded revision is
infeasible: `6eb35d8` is not an ancestor, the Phase-18 harness does not exist
at that commit, and the current 9-file byte composite differs from the
recorded pin (intervening phases legitimately re-layered the runtime; the
Phase-165 identity layer decouples the alpha core). The lifecycle trace (32
orders, 32 triggers, 30 expiries, 2 invalidations, directional split 18/14) is
identical to the recorded Phase-18 evidence, which is the operative proof that
the same strategy behavior was executed.

---

## 4. Method

1. **Canonical executor only.** All runs use
   `core/research/oos_validation/execution.py:run_frozen_oos`; no
   reimplementation of order lifecycles or fills.
2. **Opt-in trace sink.** `run_frozen_oos(..., order_trace=[])` attaches a
   temporary root-log capture and serializes the frozen order registry plus
   the lifecycle events the backtester already emits. The capture is passive
   and the returned funnel is unchanged (regression-tested).
3. **Certified reproduction gate.** Dataset identity, file hash, freshness,
   integrity, per-period funnels and global funnel are compared against the
   recorded Phase-18 artifact before any evidence is written.
4. **Bar-domain correction.** The frozen pipeline's `bar` is 1-based relative
   to the run (`PipelineContext.add_candle` increments `replay_index` on the
   candle being processed). The trigger candle is row `bar-1`; the RULE-3 fill
   candle is row `bar`. The tracer records both domains and validates prices
   against the dataset.
5. **Distinct re-evaluation.** Phase-26 funding-aware results are written to a
   new artifact; Phase-18 and Phase-25 files are never modified.

---

## 5. Certified reproduction

| Run | Orders | Fills | Terminal |
|---|---|---|---|
| OOS_01 | 2 | 0 | EXPIRED 2 |
| OOS_02 | 0 | 0 | — |
| OOS_03 | 2 | 0 | EXPIRED 2 |
| OOS_04 | 3 | 0 | EXPIRED 3 |
| OOS_05 | 8 | 0 | EXPIRED 8 |
| OOS_06 | 0 | 0 | — |
| **Global** | **32** | **0** | **EXPIRED 30 / INVALIDATED 2** |

Global directional split: BEARISH 18, BULLISH 14. Every field matches
`phase18_oos_validation.json`. `scripts/phase26_order_trace.py` exits non-zero
if any invariant fails; the current run exits 0 with
`invariant_failures: []`.

---

## 6. Root-cause evidence

### 6.1 Terminal classifications (global, 32 orders)

| Classification | Count | Status |
|---|---|---|
| `TRIGGERED_REJECTED_RR_EROSION` | 28 | EXPIRED |
| `TRIGGERED_REJECTED_RR_EROSION_THEN_INVALIDATED` | 2 | INVALIDATED |
| `TRIGGERED_REJECTED_FILL_BEYOND_TARGET` | 2 | EXPIRED |
| **Fills** | **0** | — |

Per-period runs (15 orders total) partition as 14 erosion expiries + 1
erosion-then-invalidated; all 15 triggered; zero fills. The global run is a
continuous sanity run, not 32 independent opportunities; the per-period runs
are the primary evidence and agree exactly with Phase 18.

### 6.2 Executable economics

| Metric (global) | min | median | max |
|---|---|---|---|
| Creation-time theoretical RR | 21.44 | 65.22 | 362.75 |
| RR at trigger close (all 32) | −0.11 | 0.150 | 2.94 |
| RR at next-open attempt (30 erosion) | 0.0092 | 0.306 | 2.94 |
| Trigger-close progress toward target (30) | 0.228 | 0.828 | 0.991 |
| Fill distance beyond entry, in initial stop-widths (30) | 6.5 | 50.1 | 255.0 |

Every creation-time RR passes the 1:6 gate by a wide margin; the gate is
non-binding at creation. Every executable RR at confirmation fails it; the
realized gate is absolutely binding. Zero of 32 trigger-close RRs reach 6.0.

Representative mechanisms:

- `-1m-BEARISH-OB-898…`: entry 79,920.00, stop 79,922.50 (2.5 points),
  target 79,712.00, theoretical RR 83.2. Trigger close 79,739.50 (already
  180.5 points through the level); next open 79,739.50; executable RR 0.150.
- `-1m-BEARISH-OB-643…`: trigger close 78,866.5 already below the target
  78,864.57; next open 78,708.0. The fill would start beyond the take-profit;
  geometry refuses it.
- `-1m-BEARISH-OB-634…`: trigger close 78,276.0, target 78,426.50; the
  trigger itself occurred 150.5 points beyond the target.

### 6.3 Why the erosion is superlinear

For a bullish fill at price `x` between entry `E` and target `T`
(`R0 = E − S`, `RR0 = (T − E)/R0`), with progress `p = (x − E)/(T − E)`:

```
remaining reward = (1 − p)(T − E) = (1 − p)·RR0·R0
risk at fill     = x − S = R0 + p(T − E) = R0(1 + p·RR0)
realized RR      = (1 − p)·RR0 / (1 + p·RR0)
```

With `RR0 ≈ 65` and `p ≈ 0.83`, realized RR ≈ 0.20 — matching the observed
median. Tight stops make the ratio worse, not better: every point of breakout
progress inflates the distance to the stop while shrinking the remaining
reward. The 1:6 creation gate is therefore irrelevant to executable economics
for this entry model.

### 6.4 What the code actually did (order of operations)

`backtesting/backtester.py`:

- `777–837` invalidation (structural stop) runs before any fill;
- `839–1088` breakout-continuation trigger (RULE 2, trigger-at-close) and
  next-bar-open fill (RULE 3);
- `897–915` directional geometry refusal (covers beyond-stop and
  beyond-target; log verb shared);
- `917–973` realized-RR erosion gate (frozen floor 6.0);
- expiry via `order_registry.advance` at 30 bars.

After an erosion refusal the trigger is consumed: the order rides to
expiry/invalidation and cannot re-trigger. This is documented design, not a
mutation of stops or targets.

### 6.5 Invariants that passed

- 32/32 trigger closes equal the trigger candle's recorded close (RULE 2).
- 30/30 erosion RR values exactly equal `realized_rr` at the **next candle's
  open**; 2/2 geometry-refused entries equal the next open (RULE 3, no
  lookahead).
- Every order has exactly one terminal status; trace statuses equal the frozen
  funnel counters.
- All 32 orders carry `entry_execution=NEXT_BAR_OPEN` and the active mode
  `BREAKOUT_CONTINUATION`; none was routed through a legacy/ungated path.

---

## 7. Alternative causes ruled out

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Wrong strategy version | Behavioral match; byte drift disclosed | Exact Phase-18 funnels; 9-file pin mismatch documented |
| Wrong/short dataset | Rejected | Identity, file hash, 11,461 rows, freshness, 0 dupes/gaps/OHLC violations |
| Lookahead or same-bar fill | Rejected | 32/32 trigger closes at trigger candle; 30/30 fills at next open |
| Fill path broken | Rejected | Extended dataset: 2 fills, RR 9.57/34.74, PnL booked, funding applied |
| Sizing/risk gate blocked | Rejected | Orders created and sized; no capacity/eligibility block recorded |
| RR gate applied incorrectly | Rejected | Geometry checked first; gate compares executable RR to 6.0; no bypass or re-anchoring |
| Stops/targets mutated to force fills | Rejected | No mutation; 2 later invalidations show original stop respected |
| Costs/funding consumed the fills | Rejected | No fills existed; gate refusals precede any trade simulation |
| Funding gap caused the no-fills | Rejected | 0 fills means no holding interval; funding is NOT_APPLICABLE_NO_FILLS |
| Protocol/config changed | Rejected | Same counts, statuses, directions, per-period split as Phase 18 |
| Missing evidence (artifact gap) | Confirmed | Phase-18 persisted terminal counts only; repaired by the trace sink |

---

## 8. Funding evidence repair (P26-D)

**Confirmed issue.** The Phase-25 request window began at 09:45Z (08:45Z pad,
unaligned). Delta's public `FUNDING:BTCUSDT` history (served through
`/v2/history/candles`) returns only whole 8-hour-aligned blocks at the head;
the partial leading block is dropped. The Phase-25 artifact therefore began
at 16:00Z and declared a 22,500-second head gap. Six genuine settlements
(10:00–15:00Z on 2026-09-05, rate −0.00214795) were absent.

**Repair.** New script `scripts/capture_funding_evidence_phase26.py` aligns the
request start down to an 8-hour boundary with an 8-hour pad, verifies strict
hourly continuity and head/tail coverage, and writes new strict artifacts:

- `reports/evidence/phase26/btcusdt_funding_bound_to_phase18.json` (sha16 `b8e6473fec4e1b62`)
- `reports/evidence/phase26/btcusdt_funding_bound_to_oos.json` (sha16 `4c18bb37940f938a`)
- `reports/evidence/phase26/raw_funding_evidence.json` (sha16 `3737e311c635dae3`)

**Verification.**

| Check | Phase 25 | Phase 26 |
|---|---|---|
| Events | 502 | 529 |
| First settlement | 2026-09-05T16:00Z | 2026-09-05T00:00Z |
| Strict hourly continuity | yes | yes |
| Head gap vs OOS start (09:45Z) | 22,500 s | 0 s |
| Recovered settlements | — | 6 (10:00–15:00Z) |
| Market-data binding | yes | yes (both datasets) |

Phase-25 artifacts remain byte-identical (`67c33b5538994d18`,
`494d17a2821e6c82`). Phase-26 funding-aware runs use the new schedule; all six
certified periods are `funded_full_period` (31–32 settlements in interval).
Funding P&L is 0 because there are no fills — not because the schedule is
empty.

---

## 9. Cost and funding accounting

- Preregistered 11F ladders A–D: attribution status
  `NOT_APPLICABLE_NO_FILLS` for every scenario; no cost was applied to the OOS.
- A configured-arithmetic check on a $60,000 notional (all four scenarios) is
  recorded as `CONFIGURED_ASSUMPTION_CHECK_ONLY_NOT_OOS_EVIDENCE`.
- Zero OOS commission/slippage/funding totals are an absence of transactions,
  not a measurement of free execution.
- Venue fee schedule for Delta perps remains unknown offline; owner-blocked.
- Funding machinery itself is exercised on the extended dataset: one held
  position accrues 0.25005 in funding, proving the holding-interval logic.

---

## 10. Repairs and regression tests

| Repair | Type | Evidence |
|---|---|---|
| Opt-in `order_trace` sink in the canonical executor | Observability only; funnel unchanged | `core/research/oos_validation/order_trace.py`; `tests/test_order_lifecycle_phase26.py::test_trace_preserves_funnel_and_classifies_every_order` |
| Per-order lifecycle artifact | Evidence | `reports/PHASE26_ORDER_LIFECYCLE.json` |
| Aligned funding recapture | Evidence/configuration | New artifacts; 6 settlements recovered; continuity test |
| Distinct funding-aware re-evaluation | Evidence | `reports/PHASE26_OOS_REEVALUATION.json` |

No trading-code change was made: none was justified by the evidence. The
misleading `ORDER_SKIPPED_INVERTED_FILL` verb is retained for compatibility
and documented as the shared directional-geometry refusal.

### 10.1 Verification

| Check | Result |
|---|---|
| Phase-26 tests | 9 passed (105.94 s) |
| Full suite, pre-final-manifest | 4839 passed, 14 skipped, 466 subtests, 4861 collected |
| Full-suite failures | 8, all stale-manifest assertions (expected before regen) |
| Manifest/snapshot tests, post-regen | 31 passed, 20 subtests; guard clean |
| Snapshot guard post-regen | `tree_pristine_at_session_start=true`; no files added by tests |
| Frozen research status | `git status --porcelain -- research/` empty |
| Final manifest | regenerated after the last content write; 2437 entries; `MANIFEST_PASS (0 problems)` |

The eight pre-regen failures were the manifest contract, snapshot neutrality,
release consistency, and release manifest suites detecting the intentional
Phase-26 file additions and the modified executor. All pass once the manifest
is regenerated; no code or test was weakened.

---

## 11. Verdict and what would change it

- `final_decision: OOS_BLOCKED` — unchanged.
- `edge: NOT ESTABLISHED` — unchanged; the frozen strategy produces no trades
  on the certified OOS.
- `release_gate: HOLD`; production readiness false; testnet/live not authorized.
- The zero-fill outcome is legitimate under the frozen rules; the incompatibility
  is a design constraint requiring a **new preregistered hypothesis family**
  (entry model/stop-target construction), tested on genuinely unseen data.
- The certified OOS set is now "seen": it cannot be used to select or tune a
  replacement. Any new family needs a new holdout and the 9M sample gates
  (≥60 completed trades, ≥5 surviving periods).
- The extended dataset's 2 fills (net −0.3369 after funding, RR 9.57/34.74)
  are transparency evidence only; they are different-revision, small-sample,
  and must not be presented as edge.

---

## 12. Limitations and owner blockers

- Byte-exact historical replay is infeasible (`6eb35d8` not an ancestor;
  Phase-18 harness absent). Behavioral reproduction is exact.
- `.env` contains non-empty known-secret lines (redacted); owner must rotate.
- Testnet/live authorization and venue fee schedules remain owner decisions.
- Dev/pre-Gate-A partition is absent from the delivery; dev-partition
  sensitivity remains blocked.
- Delta instrument metadata in the paper session is a synthetic spot fallback.
- Sample sufficiency is unmet by construction (0 trades).

---

## 13. Reproduction commands

```
python scripts/phase26_order_trace.py
python scripts/capture_funding_evidence_phase26.py
python scripts/phase26_oos_reevaluation.py
python -m pytest tests/test_order_lifecycle_phase26.py -q
python -m pytest tests -q
python scripts/generate_manifest.py --root . --write BUILD_MANIFEST.sha256
python scripts/generate_manifest.py --root . --verify
```

The trace script fails closed on dataset identity, reproduction, timing or
classification inconsistencies. The capture script fails closed on empty,
non-hourly, non-covering or non-head-covering funding evidence.

---

## 14. Deliverables

| Artifact | Status |
|---|---|
| `reports/PHASE26_FINAL_REPORT.md` | this document |
| `reports/PHASE26_ORDER_LIFECYCLE.json` | complete per-order trace, 32 global + 15 per-period |
| `reports/PHASE26_EVIDENCE_LEDGER.json` | evidence inventory and hashes |
| `reports/PHASE26_BLOCKER_REGISTER.md` | open/resolved blockers |
| `reports/PHASE26_STRATEGY_VALIDATION_PLAN.md` | next evidence path, no tuning |
| `reports/PHASE26_OOS_REEVALUATION.json` | distinct funding-aware re-evaluation (supporting) |
| `scripts/phase26_order_trace.py` | reproducible tracer |
| `scripts/capture_funding_evidence_phase26.py` | aligned recapture |
| `scripts/phase26_oos_reevaluation.py` | re-evaluation runner |
| `tests/test_order_lifecycle_phase26.py` | 9 regression tests |

No live orders. No testnet orders. No secret exposure. No retuning.
