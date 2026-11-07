# Phase 11F-4 — Preregistered Hypothesis Research Results

First authorized execution of H11F-001…008. Controlled run, not
optimization. No winner selected. D3 sealed throughout (never opened,
hashed, or read). Production untouched. LIVE disabled.

Preregistered classification rule (fixed before results, 11E E5/E6):
SUFFICIENT (>=30 pooled trades, >=3 folds, >=2 active) + pooled
net(C) > 0 → PASS; SUFFICIENT + net(C) ≤ 0 → FAIL; else
INSUFFICIENT_EVIDENCE. No ranking.

## 1. Starting commit

```text
f782d9dcf2285a2c9bd16c3fff2e9980686a32d6
research(phase11f): freeze validation and walk-forward protocol
```

## 2. Frozen protocol verification

Pre-run: manifest hashes ALL-MATCH; log 8× REGISTERED/0/null; D3 seal
verified metadata-only. One documented scaffolding correction during
the phase (11F-4-A1, manifest amendment, prior hash preserved):
`candidates.py` `_Base.prepare()` rebuilt feature arrays on every bar
of the growing harness feed, wiping `pend`/`last_*` state, so
stateful LIMIT-retest hypotheses (002/005/006/007) could never trigger
in-harness (0 signals despite valid setups; proven by direct-vs-harness
divergence on identical bars). Fix preserves state across
same-dataset prefix-extension rebuilds (feature values prefix-stable
per 11F-2); economics, frozen params, features, costs untouched.
151/152 prior tests passed unchanged post-fix (only the manifest-hash
trip, then re-pinned). Equal-level rarity (pairwise swing distances
$4–$1000 vs tolerance $0.3–$4) verified genuine market structure, not
a bug — left untuned as frozen.

## 3. Dataset lineage

Per symbol: universe_D1 (4001 bars, IS lineage, disclosed) +
universe_D2 (3000 bars, validation lineage), contiguous
(D1.last+60 == D2.first), BTC/ETH time-aligned, 7001 bars each.
Frozen `build_folds` hosts 4 folds in [0,6175); 826-bar tail unused
(documented). oos_fresh reserved unused to keep geometry exact.
Cold-start engines per test fold (11E pattern); train regions supply
only fitted quantities (regime terciles, RB k). dataset_hash binds
full bar content per symbol (D1/D2 hashing permitted; D3 never hashed).

## 4. Hypothesis registry

Eight hypotheses executed exactly as frozen (default params, no
overrides except preregistered ablation switches): sweep reversal,
sweep+displacement/FVG, Wyckoff spring/upthrust, OB sweep, breaker,
trend FVG, range RSI fade. No definition changed for results.

## 5. Fold construction

Expanding-origin, train 2000 / test 1000 / purge 150 / embargo 25 /
step 1000 / 4 folds, `validate_folds` clean per series. 64 fold keys
(8 hyps × 2 symbols × 4 folds) × 4 costs = 256 runs, fills proven
cost-independent (no fold varies fill count across A/B/C/D).

## 6. H11F-001 results — INSUFFICIENT_EVIDENCE

0 pooled trades (0 fills, 8 folds). No equal-level sweep ever formed:
three 0.1×ATR-tolerance touches never co-occur on trending 1m data.
Costs: all zero. Nothing to infer; sample absence is the finding.

## 7. H11F-002 results — INSUFFICIENT_EVIDENCE

0 pooled trades. Sweep-gated (see §6); displacement (11 bars/1000)
and FVGs (177) never coincide with a sweep. Ablations no-sweep /
no-fvg (registry names; report §14 "no-FVG" uppercase): 0 trades each.

## 8. H11F-003 results — INSUFFICIENT_EVIDENCE

0 pooled trades. No Donchian-50 range (30-bar hold) ever produced a
spring-with-reclaim on either symbol in the test windows.

## 9. H11F-004 results — INSUFFICIENT_EVIDENCE

0 pooled trades. Mirror of §8 (upthrust side); no qualifying false
breakout with reclaim.

## 10. H11F-005 results — INSUFFICIENT_EVIDENCE

0 pooled trades (full). Sweep-gated. Ablation no-sweep: 6 trades,
net(C) −$2.93 — removing the gate lets OB+displacement fire, still
negative; reported, not selected.

## 11. H11F-006 results — INSUFFICIENT_EVIDENCE

0 pooled trades (2 orders, 0 fills: LIMIT levels never re-touched
within wait). Breaker crossings without retests are not evidence.

## 12. H11F-007 results — INSUFFICIENT_EVIDENCE

0 pooled trades (full). Ablation no-fvg: 28 trades, −$11.27;
no-trend: 0 trades. With-trend FVG continuation never set up at
frozen thresholds; variants negative or empty either way.

## 13. H11F-008 results — FAIL (sufficient evidence)

117 pooled trades, 4 folds, 8/8 active folds: SUFFICIENT.

```text
A: net +37.95, exp +0.32, PF 15.12, 28W/89L
B: net −14.70, exp −0.13, PF 0.66,  26W/91L
C: net −55.06, exp −0.47, PF 0.28,  17W/100L, Sharpe −5.79, Sortino −15.83, maxDD 57.51
D: net −148.08, exp −1.27, PF 0.07, 10W/107L
```

Zero-cost gross edge (+$0.32/trade) exists but realistic costs erase
it 29× over — the same signature as 11E. FAIL is economic, not
statistical: bootstrap mean 95% CI (−0.60, −0.33) entirely negative.

## 14. Cost sensitivity

H11F-008 ladder A→D strictly decreasing, wins collapsing 28→10;
every other hypothesis flat-zero at all costs. No cost assumption
was altered; scenario C remains the lens.

## 15. Regime analysis

Train-fit terciles per fold (causal). H11F-008: every sufficient
cell (≥3 trades) negative except two n=4 cells (+$1.99, +$2.46,
noise-scale); no rescue regime. Others: no trades, no cells.

## 16. Random baseline

Per-fold, 500 draws, train-median k, scenario C, MTM-at-boundary,
fold-confined (11E corrected method). H11F-008 strategy sits at the
99–100th percentile of random — but both are deeply negative
(strategy −$2…−$11 vs random medians −$5…−$18 per fold): losing less
than random is not an edge. Others: INSUFFICIENT (no fills → no draws).

## 17. Monte Carlo

H11F-008 pooled C (n=117): P(loss)=1.0; p5/p50/p95 all −$55.06
(degenerate — every-trade-negative ordering); maxDD obs $57.51 vs
p50 $55.36; P(DD>obs)=0.19; losing streak 15. Certain loss at
realistic costs; no sequence luck available. Others: INSUFFICIENT.

## 18. Ablations

Strict single removals, A+C costs, identical data/exec/risk/expiry:
002 no-sweep/no-fvg 0 trades; 005 no-sweep 6 trades −$2.93;
007 no-trend 0 trades, no-fvg 28 trades −$11.27. No ablation rescues
economics; none selected.

## 19. Execution robustness

First-order overlays on H11F-008 C baseline (−$55.06): V1 −$57.99,
V2 (seed 1107, 10% dropped) −$50.25, V3 −$60.91. Already-failed
economics stay failed; execution is not the deciding factor.

## 20. Multiple-testing interpretation

Bonferroni reference 0.00625, BH-FDR q=0.10 frozen; passes = 0;
verdicts {7× INSUFFICIENT_EVIDENCE, 1× FAIL}. No ranking, no winner
(the word appears nowhere in artifacts). A single future pass would
remain hypothesis-generating pending D3 replication.

## 21. Reproducibility

Full primary repeated (256 fold-cost runs): all trade lists,
setup IDs, metrics, and hashes identical (`reproducibility.json`:
256/256 folds + 256/256 metrics, identical=true).

## 22. Evidence minimums

Applied exactly as frozen: 7 hypotheses INSUFFICIENT (0 trades < 30);
H11F-008 SUFFICIENT (117 ≥ 30, 4 folds, 8 active). Zero-trade folds
recorded as EMPTY-equivalent (0-trade entries, never dropped).

## 23. D3 sealing

Seal verified pre-run (metadata-only), at runner startup, and
post-run: artifacts contain no "D3"/"oos_fresh" strings; fold lineage
is D1/D2 only; runner never opens/reads/hashes D3 (static scan +
metadata seal checks); no D3 timestamps/statistics computed anywhere.

## 24. Research safety

ALLOW_LIVE=false, LIVE_EXECUTE=false; runner static scan clean
(no execute/place_order/submit/cancel/credential paths); all runs
through the production Backtester paper path; `live_safety_gate.py`
untouched; Gate A pattern (frozen strategy) never invoked by research.

## 25. Limitations

Two-symbol 1m only; ~7.6k-bar universe per symbol with 826-bar unused
tail; cold-start warmup absorbs ~100 test bars per fold; oos_fresh
unused; funding unmodeled (0, explicit); RB exits use the documented
2:1 neutral convention; thin-regime cells; seven hypotheses untested
in the economic sense for lack of setups (a setup-rate finding, not
an edge finding).

## 26. Final evidence classification

```text
H11F-001: INSUFFICIENT_EVIDENCE (0 trades)
H11F-002: INSUFFICIENT_EVIDENCE (0 trades)
H11F-003: INSUFFICIENT_EVIDENCE (0 trades)
H11F-004: INSUFFICIENT_EVIDENCE (0 trades)
H11F-005: INSUFFICIENT_EVIDENCE (0 trades)
H11F-006: INSUFFICIENT_EVIDENCE (0 trades)
H11F-007: INSUFFICIENT_EVIDENCE (0 trades)
H11F-008: FAIL (117 trades, pooled net(C) −$55.06, exp −$0.47, PF 0.28)

PASS: 0 / FAIL: 1 / INSUFFICIENT_EVIDENCE: 7
NO EDGE IDENTIFIED. No winner selected.
```

Seven hypotheses cannot be judged economically for want of setups at
frozen thresholds; the one testable hypothesis fails costs decisively
despite a positive zero-cost gross. Phase 11E RED stands, extended:
no new edge identified.
