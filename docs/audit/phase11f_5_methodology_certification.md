# Phase 11F-5 — Walk-Forward Methodology Correction & Controlled Re-Certification

## A. Executive Summary

STATUS: GREEN (methodology) / NO EDGE (economics)
EVIDENCE: post-freeze review confirmed `build_folds()` generated rolling
train windows against the frozen expanding-origin spec; minimal correction
applied, 256 primary executions + full analysis re-run clean, 2188 tests
green, Gate A unchanged, D3 untouched, production untouched.
LIMITATION: pre-fix intra-commit observation ordering is NOT_VERIFIABLE
from git alone (recorded honestly; corroboration noted, not proof).
CERTIFICATION IMPACT: the 11F-4 verdicts are superseded but preserved;
corrected verdicts are identical (7× INSUFFICIENT_EVIDENCE, 1× FAIL).

## B. Starting Git State

STATUS: verified
EVIDENCE: HEAD `23125181` ("execute preregistered hypothesis research"),
parent `f782d9d` (protocol freeze), `f782d9d` proven ancestor
(`merge-base --is-ancestor` true), protocol commit precedes execution
commit topologically. Tree clean except pre-existing untracked
`muse suggetions*.md` (unrelated user work, never staged).
LIMITATION: none. CERTIFICATION IMPACT: phase sequencing valid.

## C. Phase 11F-3 Frozen Protocol

STATUS: intact
EVIDENCE: design "expanding-origin chronological folds", train_min 2000,
test 1000, purge 150, embargo 25, step 1000, n_folds 4, invariant
`train_end + purge + embargo <= test_start`. Expected trains:
[0,2000)/[0,3000)/[0,4000)/[0,5000).
LIMITATION: the spec text never wrote `train_start = 0` explicitly
(added as clarifying `train_rule`, no value changed). CERTIFICATION
IMPACT: spec is the source of truth; implementation was brought to it.

## D. Pre-Correction Fold Geometry

STATUS: FAIL (recorded, not hidden)
EVIDENCE: `research/phase11f/11f5_pre_correction_fold_geometry.json` —
actual trains [0,2000)/[1000,3000)/[2000,4000)/[3000,5000) vs expected
expanding; verdict FAIL saved pre-correction.
LIMITATION: none. CERTIFICATION IMPACT: discrepancy proven, not assumed.

## E. Actual vs Expected Walk-Forward Geometry

STATUS: discrepancy CONFIRMED (rolling, not expanding)
EVIDENCE: `train_start = k*step_bars` in `build_folds()`; test windows
identical under either geometry ([2175,3175)/[3175,4175)/[4175,5175)/
[5175,6175)). No historical evidence for rolling as intent (spec,
tests-of-intent, and report all say expanding).
LIMITATION: none. CERTIFICATION IMPACT: correction required; no
documentation rewrite performed.

## F. Whether the Original 11F-4 Execution Was Methodologically Valid

STATUS: NO
EVIDENCE: runner consumes `build_folds()` windows with no
transformation (test slices cold-start; train regions feed regime
terciles + RB k). 11F-4 therefore ran rolling trains. Strategy trades
are geometry-invariant (cold-start test slices), so the economic
evidence stands factually while the train-derived fits were
non-compliant. Original artifacts preserved byte-identical in
`research/phase11f/archive/11f4/` (14 files + README, hash-verified).
LIMITATION: none. CERTIFICATION IMPACT: 11F-4 superseded, preserved.

## G. A1 Bug and Provenance

STATUS: documented (`11f5_a1_amendment.json`, `docs/audit/phase11f_a1_amendment.md`)
EVIDENCE: `prepare()` wiped `pend/last_high/last_low` per bar on the
growing feed → stateful hyps (002/005/006/007) armed but never
triggered (2 direct signals vs 0 in-harness on identical bars).
Entered repo only in `2312518` (+17/−0 lines). Stateless hyps
provably unaffected (151/152 tests unchanged post-fix).
LIMITATION: none. CERTIFICATION IMPACT: repair, not optimization.

## H. A1 Pre-Fix Result Observation Status

STATUS: NOT_VERIFIABLE (honest classification)
EVIDENCE: git/artifacts cannot order intra-commit events.
Corroboration (not proof): pre-fix probes printed counts/timings only,
never economics; log stayed REGISTERED until the final step; first
artifact postdates the fix in session order.
LIMITATION: mtime/session evidence does not survive fresh clones.
CERTIFICATION IMPACT: none claimed beyond the fix's necessity, which
is proven mechanically (zero-signal impossibility).

## I. Exact Correction

STATUS: minimal
EVIDENCE: `validation.py`: `train_start = 0`,
`train_end = train_bars + k*step_bars` (+`train_rule` spec line,
+`validate_expanding()`); test/purge/embargo/step/counts untouched.
`validate_folds` untouched (still passes). `datasets.py`: audit
counters only. Nothing in strategies, thresholds, costs, risk, data,
seeds, or production changed (change-surface grep proves absence).
LIMITATION: expanding trains now include past test bars as future
training data — that IS the frozen expanding-origin definition.
CERTIFICATION IMPACT: methodology restored with smallest possible diff.

## J. Semantic Tests

STATUS: PASS (12 new: TEST-WF-001…010 + determinism + shrinking-train)
EVIDENCE: `tests/test_phase11f_wf_semantics.py` — train_start==0,
monotonic/nested trains, chronological/disjoint tests, purge/embargo
gaps, overlap impossibility, fit-region discipline, determinism.
LIMITATION: none. CERTIFICATION IMPACT: meaning tested, not wording.

## K. Mutation Tests

STATUS: PASS — ROLLING-WINDOW MUTATION: DETECTED AND FAILED
EVIDENCE: `train_start = k*step` mutant fails `validate_expanding`
("rolling, not expanding") while the old isolation-only validator
passes it clean — proving why the semantic suite was necessary.
Restoration green. All 11F-4 mutation batteries still green.
LIMITATION: none. CERTIFICATION IMPACT: insufficient-test failure mode closed.

## L. Causality

STATUS: PASS (unchanged)
EVIDENCE: 11F-2 suites (50 tests: future-bar invariance ×5
perturbations, hostile accessor, confirmation timing, fib A–E) green
post-correction; correction touches no feature/timestamp logic.
LIMITATION: none. CERTIFICATION IMPACT: 11F-2 certification stands.

## M. D3 Access Audit

STATUS: PASS — D3 READ COUNT = 0, D3 HASH COUNT = 0, D3 LOAD COUNT = 0
EVIDENCE: no code path reads/hashes/loads D3 (source-scan test over all
9 research modules); `D3_ACCESS` counters exist and read 0/0/0;
refusals raise pre-I/O; artifacts contain no "D3"/"oos_fresh" strings;
fold lineage D1/D2 only. Counters are in-memory (fresh process reads
0/0/0); the structural guarantee is the absence of any read path,
not the counter value.
LIMITATION: in-memory counters do not persist across processes.
CERTIFICATION IMPACT: seal proven by construction + scan, honestly bounded.

## N. Dataset Lineage

STATUS: PASS
EVIDENCE: `11f5_execution_manifest.json` — BTC/ETH 7001 bars,
D1[0:4001]+D2[4001:7001], contiguous, time-aligned, content hashes
recorded (D1/D2 hashing permitted). No refetch, no replacement.
LIMITATION: 826-bar tail unused by frozen geometry; oos_fresh reserved.
CERTIFICATION IMPACT: frozen data used exactly.

## O. Eight Hypothesis Results (corrected geometry)

STATUS: recorded — 7× INSUFFICIENT_EVIDENCE, 1× FAIL
EVIDENCE: `11f5_hypothesis_results.json` — 001–007: 0 pooled trades;
008: 117 trades, net(C) −$55.06, exp −$0.47, PF 0.28. Strategy trades
**bit-identical** to archived 11F-4 (canonical-hash equality over all
256 fold-cost runs) — the correction provably cannot be economic
optimization.
LIMITATION: zero-setup hyps remain economically unjudgeable.
CERTIFICATION IMPACT: evidence recertified under compliant geometry.

## P. Ablations

STATUS: PASS (protocol-compliant)
EVIDENCE: only 002(no-sweep/no-fvg), 005(no-sweep), 007(no-trend/no-fvg);
single removals; 002 variants 0 trades, 005/no-sweep 6 trades −$2.93,
007/no-trend 0, 007/no-fvg 28 trades −$11.27. None rescue.
LIMITATION: none. CERTIFICATION IMPACT: no hidden variants.

## Q. Regime Results

STATUS: PASS (train-fit only)
EVIDENCE: per-fold expanding-train terciles; all sufficient cells
negative except two n=4 noise cells; insufficient cells explicit.
LIMITATION: thin cells. CERTIFICATION IMPACT: no rescue regime.

## R. Random Baseline

STATUS: PASS (protocol-compliant)
EVIDENCE: 500 draws/fold, seeds 1108000+, train-median k, $500 cap,
cost C, fold-confined, MTM-boundary; 008 at 99–100th percentile of a
deeply-negative random distribution (losing less than random ≠ edge).
LIMITATION: neutral 2:1 exit convention (documented).
CERTIFICATION IMPACT: no value beyond trivial alternatives.

## S. Monte Carlo

STATUS: PASS
EVIDENCE: 5000/5000, seeds 1107001/1107002: 008 P(loss)=1.0, streak 15,
maxDD obs $57.51 vs p50 $55.36. Others INSUFFICIENT (no trades).
LIMITATION: none. CERTIFICATION IMPACT: certain loss at realistic costs.

## T. Execution Robustness

STATUS: PASS
EVIDENCE: V1 −$57.99 / V2 −$50.25 / V3 −$60.91 vs −$55.06 baseline.
Stays failed; execution not decisive.
LIMITATION: first-order arithmetic (documented 11E method).
CERTIFICATION IMPACT: none overturned.

## U. Cost Robustness

STATUS: PASS (frozen ladder)
EVIDENCE: 008 A +37.95 → B −14.70 → C −55.06 → D −148.08; wins 28→10.
Scenarios byte-identical to freeze; no fifth scenario.
LIMITATION: funding 0 (explicit). CERTIFICATION IMPACT: costs destroy
the zero-cost gross edge — same signature as 11E.

## V. Economic Metrics

STATUS: consistent (certified adapter)
EVIDENCE: every recorded trade balances net=gross−fees−slippage;
fills cost-independent; expectancy/PF/Sharpe/Sortino/drawdown via
reused 11E implementation. 008 Sharpe −5.79, Sortino −15.83.
LIMITATION: none. CERTIFICATION IMPACT: no metric invention.

## W. Reproducibility

STATUS: PASS
EVIDENCE: clean second process, all 256 fold-cost runs repeated:
`11f5_reproducibility.json` 256/256 folds + 256/256 metrics identical.
`11f5_hash_manifest.json`: 13 artifacts + 12 sources + env pinned.
LIMITATION: same-machine rerun (OS recorded in manifest).
CERTIFICATION IMPACT: full repeatability demonstrated.

## X. Gate A Regression

STATUS: PASS ×2 (+2 internal)
EVIDENCE: 27/11/6/5/0/+0.117534, identical trade/order IDs, twice
externally. Methodology correction touched no production path.
LIMITATION: none. CERTIFICATION IMPACT: production behavior unchanged.

## Y. Production Diff

STATUS: PRODUCTION MODIFIED = NO
EVIDENCE: final diff touches only `research/phase11f/**`,
`tests/test_phase11f_*.py`, `docs/audit/**`. No `core/`, `config/`,
`data/`, `backtesting/`, `main.py`, adapters.
LIMITATION: none. CERTIFICATION IMPACT: research-only containment holds.

## Z. Network/Live Safety

STATUS: PASS — REAL EXCHANGE ORDER CALLS = 0
EVIDENCE: ALLOW_LIVE=false, LIVE_EXECUTE=false; runner static scan
clean; all runs offline Backtester path; historical reads only
(preregistered D1/D2); credentials never printed, never in artifacts.
LIMITATION: local `.env` presence acknowledged, never used.
CERTIFICATION IMPACT: live safety preserved.

## AA. Repository/Artifact Integrity

STATUS: PASS
EVIDENCE: full suite 2188 green (2174 + 14 new/audit tests… precisely:
2188 = 2174 prior + 12 semantic + 2 seal-audit), compileall clean,
`git diff --check` clean, line-ending-stable canonical hashes for
evidence (raw-byte CRLF/LF archive lesson documented in §F note:
archive stores exact blobs).
LIMITATION: none. CERTIFICATION IMPACT: chain complete:
protocol → 11F-4 execution → diagnosis → amendment → correction →
tests → clean execution → repro → this report.

## AB. Limitations

Single-machine rerun; 1m two-symbol universe; 826-bar unused tail;
cold-start warmup per fold; oos_fresh unused; funding unmodeled;
RB neutral exits; seven hyps setup-less at frozen thresholds;
intra-commit pre-fix ordering NOT_VERIFIABLE; D3 counters in-memory.

## AC. Final Certification Decision

```text
METHODOLOGY: GREEN
ECONOMIC EDGE: FAIL (008) / INSUFFICIENT_EVIDENCE (001-007)
LIVE READINESS: DISABLED
PHASE 11F-5 STATUS: GREEN
```
