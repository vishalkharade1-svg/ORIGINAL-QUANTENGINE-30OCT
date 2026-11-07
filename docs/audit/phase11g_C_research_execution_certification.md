# Phase 11G-C — Preregistered Institutional Research Execution Certification

FIRST 11G economic execution. Frozen family, no modifications, no winners.
D3 sealed (0/0/0). LIVE disabled. Production unchanged.

## A. Executive Summary

METHODOLOGY: GREEN — freeze verified, expanding-origin WF executed
(256/256 runs), NBO channel certified, cold-start isolation, costs/
metrics/RB/MC/regimes/exec per frozen plans, 256/256 reproduced,
causality + mutations green, suite 2188+135 green, Gate A unchanged.
ECONOMIC EDGE: INSUFFICIENT_EVIDENCE (8/8 hypotheses below the
preregistered 30-trade minimum; 4 fills total, all cost-dominated).

## B. Starting Git State

HEAD `a50ec8d` (11G-B preregistration), branch `main`, tree clean
except pre-existing untracked muse notes. Parent chain verified.

## C. Freeze Verification

8/8 IDs unchanged; hypothesis sha256 `e4905815…` matches manifest;
feature-contract, capability, dataset-descriptor hashes match; cost/
execution/WF contracts byte-identical; D3 sealed; production/live
states unchanged. No STOP condition triggered.

## D. Hash Verification

Pre-run manifest check passed all entries. Post-run: `run_manifest.json`
(source/dataset/contract hashes) + `results_manifest.json` (11 artifact
hashes). Results reference the frozen hypothesis hash; freeze manifest
never rewritten.

## E. Dataset Lineage

BTC/ETH: D1 (4001, IS lineage) + D2 (3000, validation lineage),
contiguous (D1.last+60 == D2.first), time-aligned, 7001 bars/symbol.
Content-bound dataset hashes recorded. 826-bar tail unused (frozen
geometry). oos_fresh unused. D1/D2 disclosed CONTAMINATED, never fresh.

## F. Data Capability

1m OHLCV REAL only (reaffirmed). No REAL order flow historically;
no proxy masquerading (provenance tests green).

## G. Execution Matrix

256/256 primary fold/cost executions complete (8×2×4×4). Fills proven
cost-independent per fold. NBO channel on every order
(entry_execution=NEXT_BAR_OPEN); decision→entry→exit timestamps ordered
on every trade; net=gross−fees−slippage on every trade.

## H–O. Hypothesis Results

| ID | Trades | Folds | Cost A | Cost B | Cost C | Cost D | Exp C | PF C | Sharpe C | MaxDD C | Class |
|----|--------|-------|--------|--------|--------|--------|-------|------|----------|---------|-------|
| H11G-001 | 0 | 0 active | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |
| H11G-002 | 0 | 0 active | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |
| H11G-003 | 0 | 0 active | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |
| H11G-004 | 2 | 2 active | −0.54 | −1.44 | −2.13 | −3.72 | −1.06 | 0.00 | — | 2.13 | INSUFFICIENT_EVIDENCE |
| H11G-005 | 2 | 2 active | +0.05 | −0.85 | −1.54 | −3.13 | −0.77 | 0.00 | — | 1.54 | INSUFFICIENT_EVIDENCE |
| H11G-006 | 0 | 0 active | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |
| H11G-007 | 0 | 0 active | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |
| H11G-008 | 0 | 0 active | 0 | 0 | 0 | 0 | — | — | — | — | INSUFFICIENT_EVIDENCE |

H11G-001 (sweep+reclaim): 0 setups — equal/session sweeps absent at
frozen tolerance (11F rarity finding extends to 11G hierarchy).
H11G-002/003: sweep-gated, 0. H11G-004: 4 signals→4 orders→1 BTC fill
(−$0.97) + 1 ETH fill (−$1.16). H11G-005: 2 signals→2 orders→2 BTC
fills (−$0.74, −$0.80). Ladders: 004 A −0.54 (0W/2L) → D −3.72;
005 A +0.05 (1W/1L) → D −3.13 — the lone zero-cost win inverts by
Cost B. H11G-006/007: no prior-range spring/upthrust
with rvol≥1.5. H11G-008: sweep-gated, 0 (HTF filter never reached).
All four fills are single-cost-round-trip losses — costs, not signal.

## P. Ablation Results

| Primary | Ablation | Δtrades | Δnet(C) | Δexp | ΔPF |
|---------|----------|---------|---------|------|-----|
| 001 (0) | no-sweep (64) | +64 | −29.14 | −0.46 | 0.36 |
| 002 (0) | no-sweep (78) | +78 | −57.12 | — | — |
| 002 (0) | no-displacement (0) | 0 | 0 | — | — |
| 003 (0) | no-sweep/displacement/fvg | 0 | 0 | — | — |
| 004 (2,−2.13) | no-bos (8) | +6 | −0.93 | — | — |
| 005 (2,−1.54) | no-breaker (16) | +14 | −4.96 | — | — |
| 006/007 (0) | no-volume | 0 | 0 | — | — |
| 008 (0) | no-htf | 0 | 0 | — | — |

Removing gates adds trades but only losses (reference-touch and
unfiltered displacement fire often, negatively). Ablations answer
their question — every component carries the (absent) signal — and
select nothing. (007 has no no-fvg variant; its preregistered
ablation is no-volume: 0 trades.)

## Q. Cost Sensitivity

004 ladder A −0.54 → D −3.72; 005 ladder A +0.05 (lone zero-cost
win, 1W/1L) → D −3.13. Everything inverts by Cost B. Costs
headlined at C throughout; zero-cost never presented as edge.

## R. Walk-Forward Results

Expanding trains verified in artifacts ([0,2000)→[0,5000)); tests
chronological/disjoint; purge/embargo respected; cold-start engines
(state/account/registry/mitigation/HTF reset per fold — fresh
candidate + fresh Backtester objects per run). 004 fills in F0
(BTC+ETH); 005 fills in BTC F2/F3. No fold skipped.

## S. Regime Results

Train-fit ATR terciles + SMA50 per fold; all 004/005 trades assigned;
cells below 3 trades flagged INSUFFICIENT (all of them — no pooled
significance manufactured). Rule applied, not bent.

## T. Random Baseline

500 draws/fold, seeds 1108000+, train-median stop/hold, $500 cap,
cost C, fold-confined, MTM-boundary. Folds without train fits or
fills → INSUFFICIENT (honest, incl. all four 004 folds). 005 BTC
F2/F3 ran: percentiles 0.982 / 0.032 on single trades — noise in
opposite directions, reported exactly, claims nothing.

## U. Monte Carlo

All hypotheses INSUFFICIENT (no pooled sample); protocol (5000/5000,
seeds 1107001/1107002) executed trivially with empty inputs. No
distribution fabricated from n=2.

## V. Execution Robustness

Overlays computed on pooled C (zeros for six hypotheses; −2.13/−1.54
bases for 004/005, variations stay negative). No favorable scenarios
invented.

## W. Reproducibility

Independent second process, all 256: `reproducibility_results.json`
256/256 folds + metrics identical. Artifact hashes pinned in
`results_manifest.json`.

## X. Causality

11G-A suites green post-execution; execution-level truncation proofs
(all 8 candidates, full + sequential) green; NBO mechanics proven
(fill at N+1 open); decision≤entry≤exit on all 4 real trades;
hostile future-sweep/BOS/FVG/OB/breaker/Wyckoff/volume/HTF mutations
change nothing (11G-A battery).

## Y. Mutation Tests

Entry/stop/target/cost/dataset/ID/model mutations all detected
(hash/contract mismatch); restoration verified (on-disk hashes match
manifest). No mutation remains in the tree.

## Z. D3 Integrity

READ 0 / HASH 0 / LOAD 0 (in-process counters + source scan + zero
D3 strings in all 10 artifacts + D1/D2-only lineage). Seal holds.

## AA. Production Integrity

`core/ config/ data/ execution/ risk/ backtesting/ main.py`:
zero modifications. Research contained in `research/phase11g/`.
ALLOW_LIVE/LIVE_EXECUTE false; exchange-write scan clean.

## AB. Gate A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs. Production behavior
unchanged by 135 new 11G tests + executor.

## AC. Test Suite

Main `tests/`: 2188 passed, 0 failed, 0 collection errors.
11G suite: 135 passed (88 A + 31 B + 16 C), 0 failed. `compileall`:
clean. `git diff --check`: clean.

## AD. Multiple Testing

N=8, Bonferroni 0.00625, BH-FDR q=0.10. Passes: 0. All eight reported;
no ranking; no winner.

## AE. Limitations

Two-symbol 1m only; 826-bar tail unused; cold-start warmup; oos_fresh
unused; funding 0; RB neutral exits + train-fit minimums (most folds
INSUFFICIENT); MC vacuous at n≤2; six zero-setup hyps unjudgeable
economically; NBO resize follows production behavior.

## AF. Final Classification

PASS: 0 / FAIL: 0 / INSUFFICIENT_EVIDENCE: 8 / METHODOLOGY_INVALID: 0.
METHODOLOGY: GREEN. ECONOMIC EDGE: INSUFFICIENT_EVIDENCE. No winner.
No candidate for validation (nothing passed). D3 stays sealed.

## AG. Recommendation

Do NOT promote anything. The setup-rate finding (sweep-gated families
starve at frozen tolerance; OB/breaker retests fill ~1/1000 bars) is
itself the scientific result: these precise institutional patterns, as
frozen, do not occur frequently enough on 1m BTC/ETH to evaluate —
and the rare fills lose to costs. Any follow-up (alternative liquidity
references, different holding structure) is a NEW preregistered family,
never an edit of this one.
