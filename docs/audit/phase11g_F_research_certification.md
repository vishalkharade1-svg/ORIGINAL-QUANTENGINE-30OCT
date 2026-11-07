# Phase 11G-F — New Institutional Family Research Certification

NEW family (H11GF-001…008) in `research/phase11g_f/`. Preregistration-first,
outcome-blind. No tuning, no winners. D3 sealed. LIVE disabled.

## EXECUTIVE SUMMARY

METHODOLOGY: GREEN — freeze verified, 256/256 expanding-origin runs,
NBO channel certified, cold-start isolation, frozen costs/metrics/RB/
MC/regimes/exec, 256/256 reproduced, causality + mutations green,
suites green (2188 + 245), Gate A unchanged ×2, production untouched.
ECONOMIC EDGE: INSUFFICIENT_EVIDENCE (8/8 below 30 trades; 4 fills,
all cost-dominated). Family verdict: NO CERTIFIED EDGE.

## REPOSITORY STATE

Start `95c5d38`, branch `main`, clean (muse notes pre-existing).
11F/11G-A–E verified intact pre-work; 11G-F adds one new tree only.

## HYPOTHESIS REGISTRY

Eight §9 concepts as H11GF-001…008 (sweep+reclaim, sweep+disp,
sweep+disp+FVG, BOS+OB, breaker, spring+vol, upthrust+vol, HTF+LTF).
Single NBO family; CLASS-A frozen params; A/B/C/D costs; certified
risk (2000/0.01/10×/500); 11 preregistered ablations; N=8,
Bonferroni 0.00625. No REAL order flow, no scores, no ML, no custom fib.

## FREEZE HASH

`6181496e2551fc5a` (manifest-recorded; re-verified pre-execution and
by mutation battery post-execution).

## DATASETS

D1+D2 universe (BTC/ETH 1m, 7001/symbol, contiguous, time-aligned,
content-hashed, contaminated lineage disclosed). 826-bar tail unused.
D3 sealed (0/0/0).

## DATA PROVENANCE

11E/11F/11G-E chain reused by import (never forked). HTF 15m exactly
resampled from closed 1m (REAL derived). No new market data.

## FEATURE CAPABILITY

REAL: structure/liquidity/displacement/FVG/OB/breaker/mitigation/
volume-aggregates/Wyckoff-events/MTF-derived. PROXY: candle-directional
estimates only (labeled; unused by this family). UNAVAILABLE: all REAL
order flow (no hypothesis requires it).

## CAUSALITY

Availability ≤ decision everywhere (Stage-A engine + per-candidate
truncation proofs, full + sequential, all 8 green); NBO decision ≤
entry ≤ exit on all 4 real trades; hostile future mutations (11G-A
battery) green post-run.

## WALK-FORWARD

Expanding trains [0,2000)→[0,5000) in artifacts; tests disjoint/
chronological; purge 150/embargo 25; cold-start engines (fresh
candidate + Backtester per run); rolling mutant detected; train-only
fits (regime terciles, RB stop/hold medians).

## SETUP RATE

| ID | Bars | Events | Signals | Orders | Fills | /1k | Label |
|----|-----:|-------:|--------:|-------:|------:|----:|-------|
| 001/002/003/006/007/008 | 14002 | 0 | 0 | 0 | 0 | 0.0 | VERY SPARSE |
| H11GF-004 | 14002 | 8 | 8 | 8 | 2 | 0.14 | VERY SPARSE |
| H11GF-005 | 14002 | 4 | 4 | 4 | 2 | 0.14 | VERY SPARSE |

Sweep-gated families starve (equal/session sweeps absent at frozen
tolerance); OB/breaker retests fill ~1/3500 bars.

## ECONOMIC RESULTS

| ID | Trades | Folds | Cost A | Cost B | Cost C | Cost D | Exp C | PF C | Sharpe C | MaxDD C | Class |
|----|--------|-------|--------|--------|--------|--------|-------|------|----------|---------|-------|
| 001/002/003/006/007/008 | 0 | 0 act | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |
| H11GF-004 | 2 | 2 act | −0.54 | −1.44 | −2.13 | −3.72 | −1.06 | 0.00 | — | 2.13 | INSUFFICIENT_EVIDENCE |
| H11GF-005 | 2 | 2 act | +0.05 | −0.85 | −1.54 | −3.13 | −0.77 | 0.00 | — | 1.54 | INSUFFICIENT_EVIDENCE |

Fills cost-independent; net=gross−fees−slippage on every trade.
The lone zero-cost win (005/A, 1W/1L) inverts by Cost B.

## COST ROBUSTNESS

Ladders strictly decreasing; zero-cost never headlined as edge.

## ABLATIONS

| Primary | Ablation | Δtr | Δnet | Δexp |
|---------|----------|-----|------|------|
| 001 (0) | no-sweep (64) | +64 | −29.14 | −0.46 |
| 002 (0) | no-sweep (78) | +78 | −57.12 | −0.73 |
| 002/003/006/007/008 | gate removals | 0 | 0 | — |
| 004 (2,−2.13) | no-bos (8) | +6 | −0.93 | — |
| 005 (2,−1.54) | no-breaker (16) | +14 | −4.96 | — |

Removing gates adds only losses. Diagnostic, never selective.

## RANDOM BASELINE

500 draws/fold, frozen seeds/fits/caps/rules. Folds without train
fits or fills → INSUFFICIENT (most). Ran where valid; single-trade
percentiles reported as noise, claimed as nothing.

## MONTE CARLO

Vacuous at n≤2 (5000/5000, seeds frozen). No intervals fabricated.

## REGIME ANALYSIS

Train-fit terciles + SMA50; all evaluable cells thin/flagged, never
pooled. No rescue regime; no regime claims.

## EXECUTION ROBUSTNESS

V1/V2/V3 overlays on pooled C stay negative. Definitions frozen.

## REPRODUCIBILITY

Independent repeat: 256/256 folds + metrics identical. Hashes pinned
(`results_manifest.json`, 13 artifacts).

## MUTATION TESTS

Hypothesis/stop/cost/dataset/ID/model/rolling-WF mutations all
detected; restoration verified; tree clean.

## D3 INTEGRITY

READ 0 / HASH 0 / LOAD 0. Zero D3 markers in 10 artifacts + manifests;
seal suites green; lineage D1/D2 only.

## PRODUCTION INTEGRITY

`core/ config/ data/ execution/ risk/ backtesting/ main.py`: zero
modifications. 11F/11G-A–E untouched. ALLOW_LIVE/LIVE_EXECUTE false;
write-scan clean; 0 exchange writes.

## GATE A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## LIMITATIONS

Two-symbol 1m; setup-starved (4 fills); oos_fresh unused here;
funding 0; cold-start warmup; RB neutral exits; zero-cost grosses
never edges; family mirrors 11G concepts by mandate (§9), so
sparsity replication is corroboration, not surprise.

## SCIENTIFIC CONCLUSION

PASS: 0 / FAIL: 0 / INSUFFICIENT_EVIDENCE: 8.
FAMILY: NO CERTIFIED EDGE. The substrate honest answer stands:
these precise institutional patterns, as frozen, occur too rarely on
1m BTC/ETH to evaluate — and the rare fills lose to costs. No winner.
No validation candidate. D3 stays sealed.
