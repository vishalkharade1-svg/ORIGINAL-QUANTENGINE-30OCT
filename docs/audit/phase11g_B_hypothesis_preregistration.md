# Phase 11G-B — Institutional Hypothesis Preregistration Report

STAGE B ONLY. Eight hypotheses REGISTERED and FROZEN. No execution, no
P&L, no winners. Economic edge: NOT TESTED.

## A. Executive Summary

STATUS: GREEN — 8/8 contracts machine-testable, outcome-blind,
frozen (sha256 `e4905815…`), family N=8 (Bonferroni 0.00625), single
NBO execution family, certified costs/risk/WF, 31 contract tests
green, main suite 2188 green, Gate A unchanged ×2, production
untouched, D3 sealed, LIVE disabled.

## B. Starting Git State

HEAD `1a73ac9` (11G-A feature engine), branch `main`, tree clean
except pre-existing untracked muse notes. 11G-A commit verified present.

## C. Phase 11F Integrity

Untouched (`git status -- research/phase11f` empty; enforced by test).
11F validation/costs/harness/manifests reused by reference only.

## D. Phase 11G-A Integrity

88/88 Stage-A tests green pre- and post-registration; no Stage-A file
modified in 11G-B (adapters referenced, never forked).

## E. Data Capability

1m OHLCV REAL only. Historical delta/CVD/footprint/absorption/
imbalance/volume-at-price/funding/OI/quotes/book: UNAVAILABLE.
No REAL order-flow hypothesis registered (§10 honored).

## F. Scientific Research Question

Do causal combinations of structure, liquidity, displacement,
FVG/OB mechanics, Wyckoff events, volume context, Fibonacci
confluence, and MTF structure contain robust edge after realistic
costs — distinguishing signal quality from economic profitability.

## G. Hypothesis Family

Eight, layered simple→confluence (L1 singles 001/004/005/006/007,
L2 pairs 002/008, L3 triplet 003). No composite score. No ML.

## H. H11G-001

Sweep + Reclaim. Hierarchy [prior_session, swing, equal_level];
0.1 ATR tolerance; NBO; stop sweep-extreme + 0.25 ATR; fixed 2.0R.
Ablation: no-sweep. REGISTERED.

## I. H11G-002

Sweep + Displacement (sweep within 3 bars incl. displacement bar,
2×ATR, same side); NBO; stop displacement extreme + buffer; 2.0R.
Ablations: no-sweep / no-displacement. REGISTERED.

## J. H11G-003

Sweep + Displacement + same-bar FVG; edge retest ≤5 bars (never setup
bar); NBO at bar i+1 (no limit-fill assumption); stop FVG far edge +
buffer; 2.0R. Ablations: no-sweep / no-displacement / no-fvg.
REGISTERED.

## K. H11G-004

BOS (close beyond last confirmed opposite swing extreme) + strictly-
prior opposite-candle OB; edge retest ≤5 bars; NBO; stop OB far +
buffer; 2.0R. Ablation: no-bos. REGISTERED.

## L. H11G-005

Breaker (close back through confirmed level) + retest ≤5 bars; NBO;
stop beyond level + buffer; 2.0R. Ablation: no-breaker (plain level
retest). REGISTERED.

## M. H11G-006

Prior-range spring + same-bar rvol_median ≥ 1.5 (trailing-20, frozen);
NBO; stop below spring low; measured target range high. Ablation:
no-volume. REGISTERED.

## N. H11G-007

Mirror upthrust (inherently bearish); stop above high; target range
low. Ablation: no-volume. REGISTERED.

## O. H11G-008

1m sweep (001 hierarchy) agreeing with latest CLOSED-15m trend; NBO;
stop + buffer; 2.0R. Ablation: no-htf. HTF bridge without independent
HTF data. REGISTERED.

## P. Parameter Policy

All CLASS-A frozen (ATR 14, buffers 0.25, RR 2.0, waits 5, ranges
50/30, volume 20/1.5, MTF 15m/50). No CLASS-B ranges opened. No
searches of any kind permitted.

## Q. Execution Contract

Single family model NEXT_BAR_OPEN (signal bar i → market fill i+1
open). Retest hypotheses confirm on the touch bar and enter next open
— no limit-fill assumptions, no exceptions, no model shopping.

## R. Risk Contract

Certified sizing byte-identical (2000 / 0.01 / 10× / $500 cap).
Signals only; risk/execution separate.

## S. Cost Contract

Frozen ladder A/B/C/D (0 / 0.05%+2bp / 0.059%+5bp / 2×C), funding 0,
certified accounting. No strategy-specific fees.

## T. Ablation Contract

11 preregistered removals (002×2, 003×3, 004×1, 005×1, 006×1, 007×1,
008×1; 001×1 no-sweep). Single-factor each. Ablations are not winners.

## U. Multiple Testing

N=8, Bonferroni 0.00625, BH-FDR q=0.10 exploratory. No ranking
selection; single passes are hypothesis-generating.

## V. Minimum Evidence

Pooled ≥30 / ≥3 folds / ≥2 active / ≥3 per regime cell; else
INSUFFICIENT_EVIDENCE. Unrelaxable.

## W. Dataset Lineage

D1/D2 disclosed CONTAMINATED_BY_PRIOR_RESEARCH; D3 SEALED (read/hash/
load 0). No new datasets.

## X. Causality

Per-hypothesis availability proofs green on synthetic bars: sweep/
displacement/FVG/OB-anchor/breaker/volume/Wyckoff/MTF timestamps all
≤ decision; future-liquidity/BOS/HTF mutations change nothing.

## Y. MTF Safety

008 proven: closed-15m only (availability ≤ 1m time); future-15m
mutation leaves earlier decisions identical; snapshot filter verified.

## Z. D3 Safety

Zero D3 strings in registry; seal tests green; no D3 in tests,
features, or contracts.

## AA. Immutability

12-field mutation battery trips hash mismatch per field; ±1
hypothesis trips; dataset mutation trips; on-disk hash re-verified.

## AB. Hash Manifest

`freeze_manifest.json`: hypothesis `e4905815…`, feature-contract,
capability, dataset-descriptor hashes; cost/execution/WF contracts;
counts; D3/production/live states; UTC freeze timestamp.

## AC. Tests

31 new contract/freeze/causality tests green. Three test-side
corrections during development (result-wording, ML-token context,
custom-fib context, entry_model field name) — all strengthened or
clarified assertions, none weakened; registry untouched throughout.

## AD. Gate A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## AE. Production Integrity

`core/ config/ data/ execution/ risk/ backtesting/ main.py`:
zero modifications (11G-B scope is `research/phase11g/` + report only).

## AF. Limitations

OHLCV-only history; no REAL order flow; D1/D2 contaminated; D3
sealed; MTF derived; Wyckoff newly formalized; 2.0R/structural targets
frozen without sensitivity exploration; zero-setup outcomes will read
as INSUFFICIENT (a setup-rate finding, not failure).

## AG. Stage-C Readiness

READY: 8 frozen contracts + manifest + log + 119 green 11G tests.
Stage C may implement signal executors against these contracts and run
the 256-fold matrix under 11F machinery. No threshold may move.

| ID | Hypothesis | Required Features | Entry | Ablations | Status |
|----|-----------|-------------------|-------|-----------|--------|
| H11G-001 | Sweep + Reclaim | Liquidity/Sweep | Next-bar | No-sweep | REGISTERED |
| H11G-002 | Sweep + Displacement | Sweep/Displacement | Next-bar | No-sweep/No-displacement | REGISTERED |
| H11G-003 | Sweep + Displacement + FVG | Sweep/Displacement/FVG | Next-bar | No-sweep/No-displacement/No-FVG | REGISTERED |
| H11G-004 | OB + BOS Retest | BOS/OB | Next-bar | No-BOS | REGISTERED |
| H11G-005 | Breaker Retest | Breaker | Next-bar | No-breaker | REGISTERED |
| H11G-006 | Spring + Volume | Spring/Volume | Next-bar | No-volume | REGISTERED |
| H11G-007 | Upthrust + Volume | Upthrust/Volume | Next-bar | No-volume | REGISTERED |
| H11G-008 | HTF Structure + LTF Liquidity | 15m/1m | Next-bar | No-HTF | REGISTERED |
