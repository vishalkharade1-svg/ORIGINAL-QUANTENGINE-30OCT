# Phase 11G-D — Fresh-Data Evidence Expansion & Setup-Rate Validation

STAGE D ONLY. Frozen hypotheses, no modifications, no winners.
oos_fresh BTC (2499 bars) as the authorized fresh dataset. D3 sealed.
LIVE disabled. Production unchanged.

## A. Executive Summary

METHODOLOGY: GREEN (with one explicit YELLOW limitation: single-symbol
fresh data and WF-infeasible sample — the setup-rate core is fully
valid). FRESH DATA: FRESH (oos_fresh proven unused by 11G).
ECONOMIC EVIDENCE: INSUFFICIENT_EVIDENCE (8/8, zero fresh fills).
SETUP RATE: VERY SPARSE (0/1000 bars all hypotheses; one invalidated
order). Sparsity persists on independent data — Outcome A.

## B. Starting Git State

HEAD `fbabde4` (11G-C execution), branch `main`, tree clean except
pre-existing untracked muse notes. Parent chain verified.

## C. 11G-B Freeze Verification

8/8 IDs; hypothesis sha256 matches manifest (`e4905815…`); contracts,
capability, dataset-descriptor hashes match; costs/execution/WF
unchanged. No STOP condition.

## D. 11G-C Integrity

11G-C artifacts/results/tests untouched by 11G-D (separate `11gd/`
directory; no file in `results/` modified — verified by status).

## E. Fresh Dataset Lineage

`research/phase11e/data/oos_fresh.json`: Delta 1m candles, BTCUSDT,
2499 bars, fetched 2026-09-07T03:23Z post-11E-freeze (recorded sha
`9f25e6…`; frozen file-sha `6c5981fd…`, both recorded). Prior use: 11E
F4 fold for the BREAKOUT strategy only. Stored newest-first, unique
timestamps, zero gaps over exactly 2499 slots; sorted on load via the
certified loader.

## F. Freshness Audit

FRESH verdict rests on: (1) zero 11G reads before 11G-D execution —
the sole 11G-tree reference is a seal-test string asserting ABSENCE;
(2) all 11G thresholds are CLASS-A constants frozen outcome-blind,
never derived from this file; (3) 11E's F4 use concerned different
hypotheses/features and shaped no 11G rule (disclosed caveat:
same instrument/era, trivially small F4 sample). ETH: no fresh file
exists — reported UNAVAILABLE, no substitution (explicit YELLOW).

## G. Data Characteristics

2499 bars, BTCUSDT 1m, contiguous, single cold-start diagnostic slice
(WF needs 6175 → INSUFFICIENT_FRESH_SAMPLE, demonstrated not assumed:
`build_folds(2499)` raises; no fake folds constructed).

## H. Setup-Rate Analysis

| ID | Bars | Events | Signals | Orders | Fills | Rate/1k | Label |
|----|-----:|-------:|--------:|-------:|------:|--------:|-------|
| 001–004,006–008 | 2499 | 0 | 0 | 0 | 0 | 0.0 | VERY SPARSE |
| H11G-005 | 2499 | 1 | 1 | 1 | 0 | 0.0 | VERY SPARSE |

One 005 signal→order invalidated pre-fill (stop breach). No
hypothesis, no ablation, no cost variant produced a fill. Event
definition = frozen-confirmation signals (documented equivalence).

## I–P. H11G-001…008

001: 0 signals (no hierarchy sweep). 002: 0 (sweep-gated). 003: 0.
004: 0 (no BOS+OB retest; D1-BTC had 6 signals — regime-dependent
rarity, not contradiction). 005: 1 signal, invalidated, 0 fills.
006/007: no prior-range spring/upthrust with rvol≥1.5. 008: 0
(sweep-gated; HTF filter never reached). All INSUFFICIENT_EVIDENCE.

## Q. Fresh Fold Results

Single diagnostic slice per hypothesis × 4 costs (fills
cost-independent, verified). decision≤entry≤exit on all orders;
net=gross−fees−slippage everywhere (vacuous over zero trades, plus
the one invalidated order carries no P&L).

## R. Cost Analysis

No fills → all ladders zero. Nothing headlined; zero-cost/gross
cannot rescue an empty sample. Ablations: gate-removed variants fire
sparsely (001/no-sweep 10/−$2.85, 002/no-sweep 16/−$7.50,
004/no-bos 2/−$1.19, 005/no-breaker 6/−$2.39, rest 0) — all negative,
consistent with 11G-C ablation behavior; reported, never selected.

## S. Regime Analysis

INSUFFICIENT_REGIME_EVIDENCE (no trades to classify; thresholds never
fit on fresh data — correctly, since fitting requires a train region
the diagnostic design has no use for).

## T. Random Baseline

INSUFFICIENT everywhere (no fills → no draws; train medians not
manufactured). Frozen seeds/caps/rules untouched.

## U. Monte Carlo

VACUOUS/INSUFFICIENT (n=0). Seeds/iters frozen. No intervals fabricated.

## V. Execution Robustness

Overlays computed (zeros); definitions frozen. Nothing to perturb.

## W. 11G-C vs Fresh Comparison

| ID | 11G-C trades | Fresh trades | 11G-C/1k | Fresh/1k | Interpretation |
|----|---:|---:|---:|---:|---|
| 001 | 0 | 0 | 0.000 | 0.000 | sparsity persists |
| 002 | 0 | 0 | 0.000 | 0.000 | sparsity persists |
| 003 | 0 | 0 | 0.000 | 0.000 | sparsity persists |
| 004 | 2 | 0 | 0.143 | 0.000 | sparsity persists |
| 005 | 2 | 0 | 0.143 | 0.000 | sparsity persists |
| 006 | 0 | 0 | 0.000 | 0.000 | sparsity persists |
| 007 | 0 | 0 | 0.000 | 0.000 | sparsity persists |
| 008 | 0 | 0 | 0.000 | 0.000 | sparsity persists |

Outcome A: extreme sparsity persists on independent data. The two
11G-C fills do not replicate — at 0.14/1000, absence in 2499 fresh
bars is the expected outcome, not a contradiction.

## X. Causality

Truncation proofs re-run ON the fresh prefix (all 8 green);
future-liquidity/swing/BOS/FVG/OB/breaker/Wyckoff/volume/HTF mutations
change nothing (11G-A battery green post-run); NBO decision≤entry≤exit
verified structurally.

## Y. Reproducibility

Independent repeat: identical trades/metrics (32/32) + truncation
proofs green. Artifact hashes pinned in `fresh_results_manifest.json`
(15 files).

## Z. Mutation Tests

Hypothesis/stop/cost/dataset mutations detected (hash/contract);
contaminated-as-fresh relabeling blocked (exact-name registry +
UNKNOWN default + D3 seal-trip); restoration verified.

## AA. D3 Integrity

READ 0 / HASH 0 / LOAD 0. No D3 content markers in any of 15
artifacts; runner never references D3 paths; seal tests green.

## AB. Production Integrity

`core/ config/ data/ execution/ risk/ backtesting/ main.py`: zero
modifications. Research in `research/phase11g/` only
(+ this report). ALLOW_LIVE/LIVE_EXECUTE false; write-scan clean.

## AC. Gate A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## AD. Test Suite

Main `tests/`: 2188 passed, 0 failed. 11G suite: 154 passed
(135 pre-existing + 7 freshness + 12 fresh-results),
0 failed. `compileall`: clean. `git diff --check`: clean.

## AE. Limitations

Single fresh symbol (ETH unavailable — YELLOW); 2499 bars (WF
infeasible — YELLOW, INSUFFICIENT_FRESH_SAMPLE for fold economics);
cold-start diagnostic only; funding 0; oos_fresh shares era with 11E
(disclosed); zero-fill economics vacuous by construction.

## AF. Scientific Interpretation

Outcome A. The frozen family is structurally rare: 0 setups/2499
fresh bars after 4 fills/14002 D1-D2 bars. Scarcity is a property of
the definitions at frozen thresholds, not of the sample. No edge
claim is possible; no failure claim is possible either — there is no
economic sample. The ablations show gates are load-bearing (removing
them adds only losses).

## AG. Recommendation

Do NOT extend data, relax thresholds, or composite winners — all
require NEW preregistered families. D3 stays sealed. The honest
terminal finding stands: NO CERTIFIED EDGE anywhere in 11F/11G;
setup sparsity is now independently confirmed.
