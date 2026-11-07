# Phase 11F-2 — Causality / Lookahead / Mutation / Determinism Certification

Certification gate only. No hypothesis run on D1/D2. D3 never opened
(not even for hashes). No rankings, no winner, no optimization, no
threshold tuning. Production untouched. LIVE disabled.

## 1. Scope

Prove the 11F-1 framework fails loudly under deliberately introduced
leakage/mutation and passes clean when restored — across causality,
confirmation timing, Fibonacci anchors, D3 sealing, frozen contracts,
cost semantics, determinism, serialization, and execution safety.

## 2. Starting commit

```text
126f73bca4641eed9235675767a6c5d78ba86b2e
research(phase11f): complete research architecture and contracts
```

Parent `dbf210e` (11E closure: RED / NO EDGE / LEGACY_REJECTED_CONTROL).

## 3. Files inspected

```text
research/phase11f/contracts.py, features.py, fibonacci.py, candidates.py,
harness.py, datasets.py, metrics.py, hypotheses.json, research_log.json,
freeze_manifest.json
research/phase11e/common.py, spec.json
core/analytics/performance.py, core/backtesting/accounting.py,
core/backtesting/trade_simulator.py, core/risk/position_sizer.py,
core/execution/live_safety_gate.py, config/settings.py, config/risk_settings.py
tests/test_edge_11e.py, tests/test_phase11f_*.py (11F-1), scripts/verify_gate_a.py
```

Direct source verification (not assumed from 11F-1 green):
candidates use only `bars[idx]` and `range(max(0,idx-3),idx+1)` — no
`idx+1` indexing; harness appends to history BEFORE calling candidate
signals (past-only feed); fibonacci scans `range(upto+1)`; equal
levels consume confirmed swings only; order-block lookup is strictly
exclusive of the reference bar.

## 4. Causality contract

`research/phase11f/causality.py` (new): `feature(t)` depends only on
information available at or before `t`. **CONFIRMATION TIME !=
STRUCTURE ORIGIN TIME** — availability timestamps are knowability
timestamps, never back-dated. Instruments: `HostileBars` (raises
`FutureAccessError` on any read past the decision bar) and
`assert_preregistered_state` (fails if any log entry left REGISTERED/0/null).

## 5. Confirmation-timestamp rules (from implementation evidence)

| Structure   | Origin | Confirmation | Earliest Legal Use | Backdating Allowed |
| ----------- | ------ | ------------ | ------------------ | ------------------ |
| Swing       | extreme bar e | e+right (default right=3) | e+right | NO |
| Equal level | swing extremes | each touch swing-confirmed; >=3 touches | first bar with >=3 confirmed touches | NO |
| Sweep       | wick beyond level + reclaim close, bar i | same bar i | i | NO |
| Displacement | range[i] > mult*ATR14[i] | same bar i | i | NO |
| FVG         | bars[i-2..i] gap | bar i | i | NO |
| Order Block | last opposite candle j < setup bar | displacement bar c | retest bars in (c, c+wait], never c | NO |
| Breaker level | confirmed swing extreme | close crossing back through level, bar c | retest bars in (c, c+wait], never c | NO |
| Range state | Donchian pair change bar | pair unchanged min_hold bars | first bar with hold >= min_hold | NO |
| Fibonacci anchor | anchor swing extremes | max(low_confirmed, high_confirmed) | max anchor confirmation bar | NO |
| Mitigation/pending | setup bar c | setup bar c (armed, not entered) | touch bars in (c, c+wait], never c | NO |

Verified: swing e=2 publishes at 3 (not 2); equal level needs 3
confirmed touches (bars 13/23 silent, 33 present, never back-dated to
10); FVG appears exactly at third bar; OB index always < reference;
fib timestamp == max anchor confirmation; breaker trigger requires a
prior arming bar (fresh instance at trigger bar emits nothing).

## 6. Future-bar tests

`tests/test_phase11f_causality.py` (8 tests): all 10 features + both
fib series + all 8 candidates (sequential stepping) recomputed at
bars 40/50/80/100/120 under five future perturbations (extreme OHLC,
volume x1000, volatility shocks, highs/lows shift, close drift) —
outputs at decision bar identical in every combination. Harness source
asserts history-append precedes candidate call.

## 7. Future-swing tests

`tests/test_phase11f_lookahead.py` (14 tests): future swing high/low,
equal level, sweep, displacement, FVG, and order block each proven
absent before confirmation and present at/after it; truncation twins
confirm no anticipation; crafted breaker cross-and-retest proves
(c, c+wait] semantics.

## 8. Fibonacci causality tests

Cases A–E all pass: (A) unconfirmed future swing yields no levels;
(B) levels appear at confirmation with hand-checked values (0.5 →
105.0 on low=90/high=120); (C) wild future bars leave history
unchanged; (D) forced future anchor rejected (incl. via HostileBars);
(E) custom ratios raise; frozen sets intact
(0.382/0.50/0.618/0.786/1.272/1.618).

## 9. D3 isolation tests

`tests/test_phase11f_seal.py` (10 tests): discovery exposes no holdout
path; `load_holdout_candles()` raises unconditionally;
direct/generic/wildcard D3 paths all blocked; no research source
references D3 or oos_fresh; lineage validator clean; meta-guard proves
no test reads D3 contents. D3 arrays unopened — no hashes, no peeks.

## 10. Frozen-parameter tests

CLASS-D dims (symbol/timeframe/costs/holdout) forbidden and pinned;
runtime override (`rr=9.99`) detected by mismatch guard while class
defaults stay immune; in-memory JSON mutation provably cannot rewrite
the file; contract schema re-validates clean.

## 11. Cost/accounting tests

`net = gross - fees - slippage - funding` with funding explicitly 0;
scenario C hand-check (PV 500 → commission 0.295, slippage 0.5);
harness formula pinned to contract terms; metrics adapter equals
certified 11E values; sign-reversal and gross-from-net corruptions
both detected.

## 12. Mutation battery (each detected, then restored)

| ID | Mutation | Detection evidence |
|----|----------|-------------------|
| MUT-1 | feature uses t+1 | perturbed future moves mutant, certified fixed |
| MUT-2 | unconfirmed swing published | certified None vs mutant present at bar 6 |
| MUT-3 | fib on unconfirmed anchor | certified [] vs fabricated levels at bar 5 |
| MUT-4 | D3 seal disabled | bypass path raises SealedHoldoutError |
| MUT-5 | net = gross + costs / gross-from-net | identity check fails |
| MUT-6 | frozen rr changed at runtime | mismatch guard trips; class default immune |
| MUT-7 | unseeded randomness / set ordering | repeat runs differ; canonical hash stable |
| MUT-8 | research-side place_order/execute | scanner flags snippet; 8 sources clean |

Mutants lived only as test-local variables; repository never altered
(`git diff` tracked empty throughout the phase until this report).

## 13. Determinism tests

`tests/test_phase11f_determinism.py` (6 tests): full feature/fib/
8-candidate snapshot + harness run bit-identical across 3 runs
(SHA-256 single digest); setup IDs stable; logged hypothesis/
parameter/dataset hashes and manifest file hashes all reproduce.

## 14. Research safety tests

Textual scan of all 8 research sources clean (denylist block
excluded); `DeltaOrderExecutor.execute` + `BrokerEngine.__init__`
monkeypatched to raise — harness run completes with zero calls;
ALLOW_LIVE/LIVE_EXECUTE false; `live_safety_gate.py` untouched.

## 15. Production-diff proof

```text
git diff --stat        -> empty (no tracked modification)
git diff --name-only   -> empty
git status --porcelain -> only untracked research/phase11f/causality.py,
                         5 new tests/test_phase11f_*.py, this report
                         (+ pre-existing untracked muse notes, excluded)
git diff --check       -> clean
```

Forbidden areas (`core/`, `config/`, `data/`, `backtesting/`,
`main.py`, exchange adapters) untouched.

## 16. Full-suite results

```text
test_phase11f_causality:    8 passed
test_phase11f_lookahead:   14 passed
test_phase11f_mutations:   12 passed
test_phase11f_determinism:  6 passed
test_phase11f_seal:        10 passed
new total:                 50 passed
full suite:              2105 passed in 217.04s (2055 prior + 50 new), 0 failed
compileall:              clean
```

## 17. Gate A results (x2 + internal x2)

```text
Orders: 27 / Fills: 11 / Wins: 6 / Losses: 5 / Breakevens: 0 / Net: +0.117534
Trade/order IDs identical between runs. [PASS] twice externally.
```

No production change made to obtain it.

## 18. Research execution status

```text
H11F-001..008: REGISTERED / variants_tested 0 / result null / failure_reason null
```

`assert_preregistered_state` passes on disk; trips on a mutated copy.

## 19. D3 status

SEALED. Unopened. No evaluation, no hashes, no candle reads.

## 20. Limitations

Synthetic bars only (no market-microstructure realism claimed);
harness determinism shown on a one-shot fixture, not on the 8
hypotheses against real data (forbidden this phase); exchange-write
safety proven for the harness path via monkeypatch + scan, not by
exercising live credentials (which must never exist here).

## 21. Final verdict

```text
PHASE 11F-2 STATUS: GREEN
```
