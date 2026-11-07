# Phase 11F-3 — Walk-Forward / OOS / Cost / Validation Protocol Certification

Methodology-freeze phase only. No H11F-001…008 execution, no ranking,
no winner, no optimization, no threshold tuning. D3 never opened,
never hashed, never read. Production untouched. LIVE disabled.

## 1. Starting HEAD

```text
f9ccccd28a44895384cb2945a83e275d4cb34e13
research(phase11f): certify causality lookahead and determinism
```

11E RED/NO EDGE reaffirmed; 11F-1 GREEN/CLOSED; 11F-2 GREEN/CLOSED.
Manifest hashes re-verified ALL-MATCH at phase start; research log
pristine (8× REGISTERED/0/null).

## 2. Scope

Freeze HOW the eight hypotheses will later be evaluated: fold
geometry, isolation proofs, fit-region discipline, OOS meaning,
cost order, execution freeze, metric reuse, evidence minimums,
multiple-testing, random-baseline / Monte Carlo / regime / ablation
plans. New module `research/phase11f/validation.py` (pure index
arithmetic + frozen plans + validators; loads no market data) and 5
new test files (56 tests). Hypotheses are named only as registry
entries — never instantiated against data.

## 3. Walk-forward specification (frozen pre-results)

```text
design: expanding-origin chronological folds
train_min_bars: 2000 | test_bars: 1000 | purge_bars: 150
embargo_bars: 25 | step_bars: 1000 | n_folds: 4
invariant: train_end + purge + embargo <= test_start < test_end
```

Purge 150 covers Donchian-100 + swing confirmation (3) + max wait (5)
plus margin; embargo 25 exceeds any expiry tail (max wait 5);
train/test/step scales match the 11E clean-OOS regime. Fold 0 on an
8000-bar dataset is hand-pinned: train [0,2000), purge [2000,2150),
embargo [2150,2175), test [2175,3175). Infeasible datasets raise
ValueError (never silent truncation).

## 4. Fold isolation

Proven: train∩test/purge empty, purge/embargo∩test empty, tests
chronological and pairwise disjoint, rebuilding on longer data never
moves earlier folds (future-fold independence).

## 5. Purge/embargo

MUT-WF-2 (zeroed purge) and MUT-WF-3 (zeroed embargo) both trip
`validate_folds`; restoration validates clean. Purge/embargo sizes
are frozen constants, not tunables.

## 6. Parameter-fit isolation

`tercile_thresholds` takes training values only; `check_threshold_fit_region`
accepts iff fit_end <= test_start. MUT-WF-4 (train+test quantiles)
provably shifts cutoffs and is rejected; hostile future values cannot
move a training-only fit; MUT-OOS-1 (test used for fitting) rejected.

## 7. OOS definition

Chronologically later than all fitting/selection data; never used for
fitting, thresholds, or candidate selection. D3 is the final sealed
holdout and is explicitly NOT part of this phase.

## 8. Cost protocol

Scenarios frozen exactly (A zero; B 0.0005+2bp; C 0.059%+5bp primary;
D 2×C stress; no fifth scenario). Order frozen:
signal→entry→position→gross→commission→slippage→funding(0)→net.
`apply_cost_sequence` hand-pinned (PV 500/C: 0.295/0.5/0 → win 9.205,
loss −10.795); costs identical for winners and losers.

## 9. Execution protocol

`LIMIT_RETEST` research-only channel unchanged; per-hypothesis models
read back from the registry (H11F-001 NEXT_BAR_OPEN; 002/005/006/007
LIMIT retest; 003/004/008 NEXT_BAR_OPEN); no substitution permitted.

## 10. Metric definitions

Reuse only: `research.phase11e.common.trade_metrics` (parity-tested
vs PerformanceAnalytics) + `metrics.research_trade_metrics` funding
leg. Fields gross/fees/slippage/funding/net/returns/R/expectancy/PF/
drawdown/Sharpe/Sortino distinguished. Sharpe rests on pnl/notional
returns (uniform rescale leaves it unchanged; dollar-PnL figure
differs on non-uniform notionals — proven). Caught: gross-from-net
(consistency diff 1.5 vs ~0), dollar-for-return, omitted fees, BE
excluded from expectancy divisor (6/3=2.0, not 6/2).

## 11. Minimum evidence rules (frozen)

Pooled ≥30 trades (11E E6 rule, unchanged), ≥3 folds, ≥2 active
folds, ≥3 trades/regime cell. Zero-trade folds = EMPTY (reported,
never dropped); failed folds reported with metrics. `assess_evidence`
returns SUFFICIENT only above all minima.

## 12. Multiple-hypothesis methodology (frozen)

No run-8-pick-best: a hypothesis passes only its own pre-registered
gates; any single pass is hypothesis-generating pending D3
replication. Bonferroni reference 0.00625 + BH-FDR q=0.10 exploratory
(hand-verified incl. ties/empty); no `select_winner`/`rank_hypotheses`
exists. Limitation (no family-wise confirmatory claim without D3)
documented in-protocol.

## 13. Random-baseline protocol (defined only, not executed)

Per-fold (11E corrected): 500 draws, seeds 1108000–1108499, entries
uniform over fold TEST bars, frozen 2:1 exits with training-median k,
$500 cap, scenario C, MTM-at-boundary, never crosses a boundary
(`check_random_trade_within_fold` + MUT-RANDOM-1 cross-fold rejection).

## 14. Monte-Carlo protocol (defined only)

Trade-order shuffle 5000/seed 1107001 + bootstrap 5000/seed 1107002;
stats P(net<0), p5/p50/p95, maxDD, P(DD>obs), streaks; percentile CIs;
null = no edge beyond costs. Seeds/iterations frozen.

## 15. Regime protocol (defined only)

ATR14/close terciles (cutoffs from TRAINING bars only) + close-vs-SMA50
trend; ≥3 trades/cell else INSUFFICIENT. Full-sample quantiles,
future-aware thresholds, post-hoc definitions, and result-driven
selection prohibited (MUT-REGIME-1 future fit rejected).

## 16. Ablation protocol (defined only, not run)

Registry unchanged (002: no-sweep/no-FVG; 005: no-sweep; 007:
no-trend/no-FVG); code matches registry; non-ablated expose full
only. MUT-ABLATION-1 (smuggled second override) detected: certified
variants carry exactly one override key.

## 17. D3 sealing verification

Discovery exposes no holdout path; loader raises unconditionally;
generic/wildcard D3 paths blocked; no research source references D3;
lineage validator clean. D3 arrays unopened — no reads, no hashes,
no timestamps, no statistics.

## 18. Mutation battery (all detected, then restored)

MUT-WF-1 overlap, MUT-WF-2 purge removal, MUT-WF-3 embargo removal,
MUT-WF-4 future threshold fit, MUT-WF-5 future-fold contamination,
MUT-COST-1 fee omission, MUT-COST-2 slippage double-count (+ reversed
slippage, double-applied costs, gross/net inversion), MUT-METRIC-1
gross-from-net, MUT-METRIC-2 wrong return denominator (+ omitted fees,
wrong expectancy divisor), MUT-RANDOM-1 cross-fold trade,
MUT-REGIME-1 future threshold, MUT-ABLATION-1 hidden second change,
MUT-OOS-1 test-used-for-fitting. Mutants were test-local; the
repository was never altered.

## 19. Determinism

Fold plans + frozen-plan SHA-256 + cost/metric/BH outputs identical
across 3 runs (single digest); per-file suites re-run identically.

## 20. Research safety

`validation.py` contains no execution/credential tokens; exchange
`execute` monkeypatched to raise — validators complete with zero
calls; research log asserted untouched (REGISTERED/0/null×8);
ALLOW_LIVE/LIVE_EXECUTE false; safety gate file untouched.

## 21. Full-suite results

```text
walk_forward:        13 passed
validation_protocol: 21 passed
cost_protocol:        9 passed
metric_contract:      7 passed
multiple_testing:     6 passed
new total:           56 passed
full suite:        2161 passed in 225.75s (2105 prior + 56 new), 0 failed
compileall:        clean
git diff --check:  clean
```

## 22. Gate A results (x2 + internal x2)

```text
Orders: 27 / Fills: 11 / Wins: 6 / Losses: 5 / Breakevens: 0 / Net: +0.117534
Trade/order IDs identical between runs. [PASS] twice externally.
```

## 23. Production-diff proof

```text
git diff --stat / --name-only -> empty pre-report
git status -> only untracked research/phase11f/validation.py,
              5 new tests/test_phase11f_*.py, this report
              (+ pre-existing untracked muse notes, excluded)
```

Forbidden areas (`core/`, `config/`, `data/`, `backtesting/`,
`main.py`, exchange adapters) untouched.

## 24. Limitations

Fold sizes are protocol defaults for ~8k-bar datasets; later phases
apply (not resize) them; thin-data infeasibility raises rather than
adapts. Random/MC/regime/ablation are frozen plans, not executed
evidence. Cost funding stays 0 (perps minute-scale holds).

## 25. Final verdict

```text
PHASE 11F-3 STATUS: GREEN
```
