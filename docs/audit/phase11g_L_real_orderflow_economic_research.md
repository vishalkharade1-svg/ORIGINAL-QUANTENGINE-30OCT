# Phase 11G-L — REAL Order-Flow Economic Research Report

FROZEN-SPEC EXECUTION. No thresholds moved. No winners selected. No
D3. LIVE disabled. Production untouched. FAILs reported, never rescued.

## 1. Starting HEAD

`952f577faba0a16235b78f4c5b83abe74b468731` (11G-K freeze), branch
`main`. Final HEAD = the L commit carrying this report (see git log).

## 2. Chain Verification

11G-I dataset (410,535 REAL trades) → 11G-J replay/features v1 →
11G-K frozen specs (freeze `f803fe7d…`, 8 hashes verified in-gate) →
11G-L economics. Hard gate re-verified every run (hashes, D3
counters, LIVE flags, risk ladder, ablation map).

## 3. Dataset and Bars

Binance UM BTCUSDT 2026-09-05 aggTrades. 1440 1m bars built FROM the
trades (first/max/min/last price, sum qty per UTC minute); 0 gaps;
full-day span. Kline cross-check: max |close| diff 0.0 all 1440
minutes (corroboration only; klines never enter the pipeline).

## 4. Fold Geometry (L Execution Design)

K freezes evidence minima (30/3/2), not geometry. 11F-default
2000/1000/150/25/4 needs 6175 bars > 1440 available — infeasible.
Certified `V.build_folds` with train/step/test 300, purge 150,
embargo 25, 3 folds (largest round tests fitting 3 folds + certified
gaps with trains ≥ 300; chosen on arithmetic alone, pre-economics):
F0 [0,300)/[475,775), F1 [0,600)/[775,1075), F2 [0,900)/[1075,1375);
tail [1375,1440) unused. Validators assert empty every run.

## 5. Execution Contract

Certified 11G-C NBO path reused (subclass; only addition is the
causal flow bundle on the research candidate — production context is
slots-restricted and never written). Signal close → next open,
SL-first, single position. Costs A/B/C/D, funding 0. All 96 fills
`NEXT_BAR_OPEN`; entry_time − decision_time = 60 throughout; entry =
next-bar open; gross − commission − slippage = net (asserted).
OHLC-structure slice-cold-start (11G-C pattern); flow quantities from
the full-day causal bundle (train history is legitimate causal
history; thresholds never fit). Train supplies regime terciles +
RB medians only.

## 6. Certified-Path Limitations (Shared With 11G-C)

Positions exit on SL/TP only (no 120-bar time-stop exists in the
production path); no post-exit 30-bar cooldown gate; trades open at
a slice boundary are dropped, never MTM-fabricated. Counts: boundary
drops are observable as orders − trades gaps; no fabrication anywhere.

## 7. Pre-Economics Implementation Notes

Re-audit of code vs frozen events (before any fill observed) fixed:
001 signal bar = BOS bar; 002 15m-window medians (same-length, the
1m-median form was vacuous); 003 price = 60-bar extreme (not ROC);
004 touch = 0.1 ATR band; 005 stop = absorption-bar extreme; 006
event-literal has NO displacement (full = sweep+reclaim & aggression;
displacement_atr frozen-but-vestigial, proven unused); 008 touch =
contact + rejection. Ablation residues: retained level keeps its
frozen stop, else signal-bar extreme ± 0.25 ATR; 007-A2 degenerate
(= full, skipped); 008-A2 BLOCKED (CVD-alone has no bar-level stop
anchor — a new rule would have to be invented). Full-day census
(frozen outcome): 001:21, 002:5, 003:8, 004:126, 005:0, 006:0
(no equal-level sweeps under frozen semantics), 007:116, 008:0
(hold≥30 + touch never coincide). 005/006/008 silence is legitimate
sparsity (components verified present separately), reported as
NO EVIDENCE.

## 8. Primary Results (Cost C, 8×3 folds×4 costs = 96 runs)

| ID | Verdict | pooled | folds/active | net(C) | expectancy |
|----|---------|--------|--------------|--------|------------|
| H11GK-001 | INSUFFICIENT_EVIDENCE | 6 | 3/3 | −5.9644 | −0.9941 |
| H11GK-002 | INSUFFICIENT_EVIDENCE | 2 | 3/2 | −2.4128 | −1.2064 |
| H11GK-003 | INSUFFICIENT_EVIDENCE | 1 | 3/1 | −1.1006 | −1.1006 |
| H11GK-004 | FAIL | 43 | 3/3 | −33.0507 | −0.7686 |
| H11GK-005 | INSUFFICIENT_EVIDENCE | 0 | 3/0 | +0.0000 | +0.0000 |
| H11GK-006 | INSUFFICIENT_EVIDENCE | 0 | 3/0 | +0.0000 | +0.0000 |
| H11GK-007 | FAIL | 43 | 3/3 | −35.5092 | −0.8258 |
| H11GK-008 | INSUFFICIENT_EVIDENCE | 0 | 3/0 | +0.0000 | +0.0000 |

Cost ladder monotonic everywhere (004: A +1.13 / B −18.22 /
C −33.05 / D −67.24; 007: A −1.32 / B −20.67 / C −35.51 /
D −69.69). 004 gross ≈ zero (Cost-A +1.13 over 43); costs destroy
it. 007 negative at every cost.

## 9. Gated Analysis

RB (500 draws, seeds 1108000+, Cost C, train-median exits): strategy
nets sit inside the random band (004-F1 pct 0.986 yet net −14.31;
007-F1/F2 pct 0.002/0.000). Random 2:1 trading bleeds the same costs
— strategy ≈ random-entry-plus-costs, no edge anywhere. MC (5000
shuffles 1107001 + 5000 bootstraps 1107002): p_loss = 1.000 for 004
and 007; bootstrap mean CIs entirely negative ([−0.84,−0.70],
[−0.88,−0.77]). Regimes (train-fit ATR terciles + SMA50): every
sufficient cell negative (PF mostly 0.0). Exec overlays (V1/V2/V3)
all negative for both FAILs. No robustness anywhere.

## 10. Ablations (17 coherent × 3 folds × A/C = 102 runs)

Pooled Cost-C nets all ≤ 0: deepest negatives are variants that
remove selectivity (004-A1 range-retest: 140 trades, −112.37;
001-A1/007-A1 BOS-only: 48, −39.59; 006-A2 aggression-only: 41,
−35.56; 005-A1 disp+volume: 31, −27.76). 003-A1/005-A2/006-A1/008-A1:
0 trades. Diagnostic only; nothing rescues the FAILs.

## 11. Multiple Testing

Bonferroni reference 0.00625, BH-FDR q = 0.10. No ranking, no
selection; verdicts are per-hypothesis against the frozen rule.

## 12. Reproducibility

Full rerun: 96/96 folds bit-identical (canonical hash) with
identical metrics. Determinism test green.

## 13. Mutation Results (MUT-L, 22 L tests)

Threshold/stop/cost/risk/dataset/execution/ID/freeze/ablation-map/
D3/LIVE/geometry mutants all detected; bundle prefix-stability,
window arithmetic, aggressor-flip sensitivity, fold-offset
independence, NBO timing, 2R target, pinned census all green.

## 14. Test Results

L 22/22. Research suites 380/380 (358 prior + 22 L). Main `tests/`
2181 OK, 0 failures, tree-clean (count vs K's 2188 is collection
difference; tests/ untouched since e3e6f4b, verified clean).
`compileall` clean. `git diff --check` clean.

## 15. Gate A ×2

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs (production path
untouched by L wiring).

## 16. Scope and Seals

Production (`core/ config/ data/ execution/ risk/ backtesting/
main.py`) untouched — `git status` clean. D3 counters 0/0/0; no D3
markers in any L file. ALLOW_LIVE/LIVE_EXECUTE unset (false).
11G-C/D sets never loaded.

## 17. Scale Note

$500 allocation cap on ~$79k BTC binds every trade (≈$500 notional,
≈$0.6 risk/trade): absolute nets are small and Cost-C fees
(~$1.1 round-trip) dominate. Expectancy/PF verdicts are scale-free
and unaffected.

## 18. Limitations

One day/one venue; aggregate (not fill) resolution; ms precision; no
book/quotes; adapted (unfrozen) fold geometry; §6 path limits;
005/006/008 zero-signal outcomes (sparsity, not malfunction).

## 19. Final Verdict

PHASE 11G-L = COMPLETE. H11GK-004 = FAIL. H11GK-007 = FAIL.
H11GK-001/002/003 = INSUFFICIENT_EVIDENCE. H11GK-005/006/008 =
NO EVIDENCE (zero signals under frozen specs). TRADING EDGE = NONE
FOUND. D3 = SEALED. LIVE = DISABLED. PRODUCTION = UNTOUCHED.
