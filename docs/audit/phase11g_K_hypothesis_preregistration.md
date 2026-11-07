# Phase 11G-K — REAL Order-Flow Hypothesis Preregistration Report

OUTCOME-BLIND FREEZE. No economics computed. No winners. D3 sealed.
LIVE disabled. Production untouched.

## 1. Starting HEAD

`ad6c3735e300dc6618ff98a99bd4e398f7a41328` (11G-J replay certification),
branch `main`, tree clean (muse notes pre-existing). Chain verified.

## 2. Final HEAD

Recorded at commit (§41 block below).

## 3. Chain Verification

11G-I dataset (410,535 REAL trades, hash `440c9191…`) → 11G-J replay/
features (v1, certified) → 11G-K specs. Each link hash-pinned.

## 4. Input Dataset Lineage

Binance UM BTCUSDT 2026-09-05 aggTrades (public Vision archive,
CHECKSUM-verified). 11G-C/D sets excluded by contract. D3 sealed.

## 5. Certified Feature Inventory

11G-J v1: delta windows, CVD (+twin), $0.01 footprint, trade imbalance,
absorption form, aggression form; 11G-A causality/timestamp machinery;
11F OHLCV primitives. All reused, none rewritten.

## 6. REAL/DERIVED/PROXY/UNAVAILABLE

REAL: price/quantity/ms/side/IDs. DERIVED_FROM_REAL: delta, CVD,
volumes, footprint, imbalance, absorption/aggression indicators.
PROXY: none introduced. UNAVAILABLE: spread, depth, queue, resting
liquidity, L2 depletion, quote changes (book work stays synthetic).

## 7. Hypothesis Table

| ID | Concept | Entry | Ablations | Status |
|----|---------|-------|-----------|--------|
| H11GK-001 | Aggressor imbalance + BOS | NBO | A0–A3 | FROZEN |
| H11GK-002 | Delta reversal + displacement | NBO | A0–A3 | FROZEN |
| H11GK-003 | CVD divergence + structure | NBO | A0–A3 | FROZEN |
| H11GK-004 | Footprint POC response | NBO | A0–A2 | FROZEN |
| H11GK-005 | Absorption + displacement | NBO | A0–A2 | FROZEN |
| H11GK-006 | Aggression + displacement | NBO | A0–A2 | FROZEN |
| H11GK-007 | BOS + delta agreement | NBO | A0–A2 | FROZEN |
| H11GK-008 | Range + CVD slope | NBO | A0–A2 | FROZEN |

## 8. Exact Hypothesis Specifications

`research/phase11g_k/hypotheses/H11GK-*.json` (29-field schema each:
event/lookback/thresholds+provenance/entry/invalidation/stop/target/
holding/execution/costs/dedup/cooldown/evidence/ablations/controls/
RB/MC/regimes/causality/forbidden/datasets/falsification). Thresholds
are domain-structural CLASS-A constants (imbalance 0.6, delta fraction
0.4, vol mults 2–5, ATR multiples, bar counts) — none fitted.

## 9. Threshold Provenance

Every threshold carries a written provenance string (domain convention
or frozen certified form). Counts-only feasibility probe (442 extreme
minutes, 347 displacement bars) confirmed components exist; no
threshold moved (nothing to move toward — no economics observed).

## 10. Causality Contract

availability ≤ decision ≤ entry ≤ exit, per hypothesis, enforced on
prefix-only certified calls (synthetic + truncation proofs green).

## 11. Execution Contract

NBO family-wide (signal close → next open); SL-first; single position;
cooldown 30; max hold 120.

## 12. Cost Contract

11F ladder A/B/C/D, funding 0, certified accounting. Unchanged.

## 13. Sample-Size Policy

<10 NO EVIDENCE; 10–29 INSUFFICIENT; ≥30 eligible; ≥100 stronger;
30/3/2/3 minima frozen. Holdout required for certification.

## 14. Ablation Policy

A0 full + ≤3 preregistered removals each (27 total variants incl.
opposite-direction falsifications); diagnostic only.

## 15. Negative Controls

Reversed side, shuffled order, structure-only, orderflow-only —
declared per hypothesis; validation controls, not optimizers.

## 16. Random Baseline Specification

500 draws/fold, seeds 1108000+, $500 cap, cost C, frozen 2:1 exits,
train-median distance, fold-confined, MTM boundary.

## 17. Monte Carlo Specification

5000 shuffles (1107001) + 5000 bootstraps (1107002); P(loss),
expectancy CI, DD comparison, streaks.

## 18. Regime Specification

ATR14/close terciles + close/SMA50, training-fit only, ≥3/cell.

## 19. D3 Verification

Counters 0/0/0; registry refuses D3; no D3 content markers in any
11G-K file (scan); seal suites green.

## 20. Outcome-Blindness Verification

Tokenize-based code scan: no economic imports/calls/artifacts in
11G-K code; no results directories exist; feasibility probe computed
counts only (no fills/PnL/costs/metrics).

## 21. Mutation Results

MUT-1…14 substance green: future leakage (trade/CVD/bar), aggressor
flip, off-by-one windows, threshold/stop/cost/risk/dataset/execution/
ID/version mutations all detected; tree clean afterward.

## 22. Determinism Results

Freeze hashes reproduce byte-for-byte; canonical serialization stable;
manifest hash matches.

## 23. Production Diff

NONE. Scope: `research/phase11g_k/` + this report. `core/ config/
data/ execution/ risk/ backtesting/ main.py`, 11F/11G-A–J untouched.
ALLOW_LIVE/LIVE_EXECUTE false; write-scan clean; 0 exchange writes.

## 24. Test Results

New 34 (schema 13, causality 5, gates 16), 0 failed. Full research
suites: 358 passed. Main `tests/`: 2188 passed, 0 failed.
`compileall`: clean. `git diff --check`: clean. (Three test-side
corrections during development — over-broad token bans and one
arbitrary ablation cap — all strengthened assertions, none weakened;
registry untouched throughout.)

## 25. Gate A ×2

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 26. Freeze Manifest/Hash

`freeze/freeze_manifest.json` (8 canonical hypothesis hashes +
dataset/feature/transformation/schema versions) + `freeze_hash.txt`
(`f803fe7d…`). Any post-freeze edit trips verification.

## 27. Limitations

One day/one venue (Binance ≠ Delta basis caveat); aggregate (not
fill) resolution; ms precision; no historical book/quotes (book work
synthetic-only); thresholds structural, unvalidated economically;
family deliberately small (8).

## 28. Final Verdict

PHASE 11G-K = GREEN. HYPOTHESIS STATUS = FROZEN. TRADING EDGE =
NOT EVALUATED. D3 = SEALED. LIVE = DISABLED. PRODUCTION = UNTOUCHED.
