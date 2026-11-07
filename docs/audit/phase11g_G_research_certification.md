# Phase 11G-G — Independent Fresh-Data Replication & Evidence Expansion

RESEARCH-ONLY replication. Frozen 11G-F family, Tier-1 gap data, no tuning,
no winners. D3 sealed. LIVE disabled. Production unchanged.

## 1. Executive Summary

METHODOLOGY: GREEN. Tier-1 gap data (zero overlap vs all in-repo sets)
replicates the sparsity finding in stronger form: 0 signals for 7/8
hypotheses on BOTH symbols, 0 fills everywhere, 0 orders everywhere.
FAMILY: NO CERTIFIED EDGE (8× INSUFFICIENT_EVIDENCE).

## 2. Starting Commit

`56b777cc153cc901a7dab356fc58bf985e6224a` (11G-F), branch `main`,
clean tree (muse notes pre-existing). Parent chain verified.

## 3. Final Commit

Recorded at commit time (§35 verification block below).

## 4. Freeze Hash

Family `6181496e2551fc5a…` (11G-F manifest, re-verified pre-run and by
mutation battery post-run). 11G-G manifest references it; nothing
re-frozen, nothing rewritten.

## 5. Dataset Provenance

Tier-1 gap: Delta GET /v2/history/candles, windowed [1788175500,
1788301440] in halves, BTC+ETH 1m. BTC 2099 bars / ETH 2099 bars
(1 exchange-side gap minute each, enumerated). shas `a3965c79…` /
`2baaf484…`, acquired pre-execution. D2-overlap: 0 bars. Gate-A
overlap: 0 bars. oos_fresh era untouched by this fetch. Deleted
pre-observation overlapping 8000-bar probe fetches (counts only ever
observed; documented here, not hidden).

## 6. Freshness Determination

FRESH (Tier-1): requested-before-observed window defined purely by
avoidance-of-overlap; no 11G-F rule, threshold, or analysis ever saw
these bars (11G-F ran D1/D2 only — verified by history); no 11G-G
observation preceded any decision (fetch → prereg → tests → run).

## 7. Contamination Assessment

Registry: gap files FRESH; D1/D2/Gate-A/phase-7 CONTAMINATED;
D3 SEALED (refused); unknown → UNKNOWN (never usable). Hostile
relabel tests green. Tier-2 oos_fresh available-but-unused (shorter
independence story; preserved for future).

## 8. Hypothesis Registry

Frozen H11GF-001…008 by reference (no copy, no rename, no edits).

## 9. Fold Specification

WF_INFEASIBLE (2099 < 6175 demonstrated via `build_folds` raise — no
fake folds). Single cold-start diagnostic per hypothesis per symbol
per cost: 64 executions. Expanding-origin validator + rolling mutant
re-proven green.

## 10. Causality Evidence

Per-candidate truncation proofs re-run on gap prefixes (8/8 green);
future-bar/HTF mutations change nothing (11G-A battery green);
decision≤entry≤exit holds structurally (vacuous over zero trades,
plus the NBO mechanics proof).

## 11. Setup Rates

| ID | Bars | Events | Signals | Orders | Fills | /1k | Label |
|----|-----:|-------:|--------:|-------:|------:|----:|-------|
| all 8 × both symbols | 2099 | 0 | 0 | 0 | 0 | 0.0 | VERY_SPARSE |

Absolute silence — stronger than 11G-C (4 fills) and 11G-D fresh
(1 invalidated order). Expectation check: at 11G-C's 0.14–0.29/1k,
≈0–1 events in 4198 bars; observed 0. Consistent, not contradictory.

## 12. Economic Results

No fills → all ladders zero. No PASS/FAIL possible; all eight
INSUFFICIENT_EVIDENCE. Ablations: all variants 0 trades on gap data
(gate removals also starve here — informative: 11G-C ablation fills
came from D1/D2 regimes, not universal behavior).

## 13. Cost Robustness

Vacuous (no trades). Ladder frozen; nothing headlined.

## 14. Ablation Results

11 variants × A/C: 0 trades everywhere on gap data. Registry match
verified (no unregistered variants).

## 15. Random Baseline

INSUFFICIENT (no fills → no draws; medians not manufactured). Frozen
seeds/caps/rules.

## 16. Monte Carlo

VACUOUS/INSUFFICIENT. Seeds frozen. Nothing fabricated.

## 17. Regime Analysis

INSUFFICIENT_REGIME_EVIDENCE. Thresholds never fit on gap data.

## 18. Execution Robustness

Overlays computed on zeros. Definitions frozen.

## 19. Reproducibility

PASS: 64/64 runs + truncation proofs identical, independent process.
Hashes pinned (`gap_results_manifest.json`, 12 artifacts).

## 20. Mutation Results

Family/cost/dataset/rolling mutations all detected; restoration
verified (on-disk family hash == manifest); tree clean of mutations.

## 21. D3 Counters

READ 0 / HASH 0 / LOAD 0. Zero D3 markers in 12 artifacts; seal
suites green; lineage gap-only. (Post-oos D3 era deliberately
unapproached: gap window ends before Gate-A start.)

## 22. Production Diff

NONE. Scope: `research/phase11g_g/` + this report. 11F/11G-A–F
untouched. ALLOW_LIVE/LIVE_EXECUTE false; write-scan clean;
0 exchange writes (one new outbound surface: read-only GET candles
for the documented fetch).

## 23. Gate A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 24. Limitations

Single diagnostic slice per symbol (no folds); 2099 bars with 1 gap
minute; ETH gap same span; oos_fresh unused; funding 0; zero-fill
economics vacuous; Tier-1 window is one era (Aug31–Sep1).

## 25. Final Classification

PASS: 0 / FAIL: 0 / INSUFFICIENT_EVIDENCE: 8.
FAMILY: NO CERTIFIED EDGE. Sparsity finding now replicated on three
independent samples (D1/D2, oos_fresh, Tier-1 gap) — structural
property of the frozen definitions, not sample accident. No winner.
No validation candidate. D3 stays sealed.
