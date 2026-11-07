# Phase 11E — Strategy Edge & Out-of-Sample Certification
# (CLOSED with methodology corrections — see §21 and
# `docs/audit/phase11e_closure_amendment.md`)

Research/certification phase. Production strategy, risk, execution,
safety, and configuration are unchanged (zero production diff since
the pre-registered spec commit `0ede560`, re-verified at closure).
No exchange orders. LIVE remains disabled.

Conventions used below: FACT (verifiable), MEASURED RESULT (executed
output), INFERENCE (conclusion from results), LIMITATION (what this
does not show).

## 1. Executive verdict

**---

## 21. Closure corrections vs v1 evidence (11E-Closure)

| Metric | v1 (superseded) | Corrected | Difference / explanation |
|---|---|---|---|
| Pooled net(C) | −$9.78 | −$9.78 | none (economics identical) |
| Pooled gross | mislabeled (= net) | explicit gross/fees/slip split | reporting fix; net unchanged |
| Regime cells | pooled IS cutoffs (D1+D2) | per-fold strictly-prior calibration | composition shifted; all cells still 0 wins, negative |
| Random baseline | pooled, boundary-crossing | per-fold, MTM-at-boundary | F1 50.8th, F2 44.0th, F3 INSUFFICIENT, F4 56.6th (was pooled 48.6th) |
| Walk-forward label | E4 PASS + WALK-FORWARD FAIL | E4-M PASS / E4-E FAIL | terminology split, same rule |
| Verdict | RED / NO EDGE | RED / NO EDGE | corrections change nothing economically |

Corrected analysis remains strongly negative (Outcome A). Methodology
notes: `docs/audit/phase11e_closure_amendment.md`.

---

PHASE 11E: RED — NO EDGE / NO-GO.**

MEASURED RESULT: pooled qualifying OOS (21 trades, D2+D3) is negative
even at zero modeled cost (net −$0.33, PF 0.72) and deeply negative at
moderate costs (net −$9.78, 0/21 wins, expectancy −$0.47/trade).
Break-even cost is −$0.016/trade (the strategy needs a per-trade
subsidy; modeled cost is +$0.45/trade — 29× underwater). The strategy
sits at the 48.6th percentile of a random-timing control. Every regime
cell is negative. All sensitivity perturbations stay negative. This is
not a software failure: the engine is certified (11A–11D); the frozen
strategy should not trade real money.

## 2. Frozen baseline fingerprint

FACT: strategy BREAKOUT_CONTINUATION
(`core/pipeline/institutional_pipeline.py` + entry models under
`core/execution/entry_model.py`, NEXT_BAR_OPEN fills, SL/TP exits via
`TradeSimulator` with SL-first ambiguity); BTCUSDT 1m via Delta
`/v2/history/candles`; balance 2000, risk/trade 0.01, notional cap 500,
leverage 10, wait 30, delay 1, zero fees/slippage; git HEAD `1e2d3cf`
(production identical to spec registration — verified empty diff).
MEASURED RESULT: Gate A fingerprint reproduced through the research
harness: 27 orders, 11 fills, 6W/5L/0BE, net +0.117534 — matches spec.

## 3. Dataset inventory

- D1 Gate A (`docs/audit/baseline_9s_delta_5000_raw.json`): 5000 bars,
  2026-09-01T22:25Z→2026-09-05T09:44Z, complete, sha recorded in
  `research/phase11e/data/step1_integrity.json`. Role: fingerprint +
  IS statistics only. CONTAMINATED (certification dataset).
- D2 Phase-7 file (`data/history/BTCUSDT_1m_oos.json`): 10000 bars,
  2026-08-24T12:45Z→2026-08-31T11:24Z, complete. CONTAMINATED
  (used by Phase 7 breakout research — referenced in
  `tests/test_breakout_asymmetry_7e.py`).
- D3 fresh (`research/phase11e/data/oos_fresh.json`): 2499 bars,
  2026-09-05T09:45Z→2026-09-07T03:23Z, complete, fetched post-freeze,
  sha256 `9f25e6…7440`. Primary clean OOS. Meets the ≥2000-bar minimum.

## 4. Data-integrity results (E1: PASS)

MEASURED RESULT: all three datasets — chronological, unique timestamps,
0 gaps, 0 duplicates, 0 out-of-order, 0 invalid OHLC, 0 non-finite
values across 17,499 bars (validator: `research/phase11e/common.py`,
evidence `step1_integrity.json`). Train/test separation is by
construction (contiguous folds, fresh engine per fold, no shared
state). INFERENCE: integrity proven. LIMITATION: exchange-source truth
is assumed (no independent vendor cross-check).

## 5. OOS definitions (E3: PASS with disclosure)

F1 D2[0:3333], F2 D2[3333:6666], F3 D2[6666:10000], F4 D3-all; pooled
OOS = F1–F4 concat (21 fills). D1 never counts as OOS. Contamination of
D1/D2 is disclosed (§3, §16); with a frozen zero-degree-of-freedom
config, walk-forward here measures stability, not selection — no
tuning occurs at any point, so contamination cannot inflate these
numbers. D3 (2499 bars) qualifies as unseen clean OOS.

## 6. Walk-forward results (E4-M: PASS methodological; E4-E: FAIL economic)

MEASURED RESULT (fills / W-L / netA / netC):

- F1: 34 orders, 14 fills, 9-5, −0.1606 / −6.4606
- F2: 13 orders, 6 fills, 4-2, −0.1684 / −2.8684
- F3: 0 orders, 0 fills (dead fold — no setups), 0 / 0
- F4 (clean): 2 orders, 1 fill, 1-0, +0.0024 / −0.4476

Full per-fold table (expectancy, PF, drawdown, Sharpe, Sortino, avg/med
R, largest W/L, fees/slippage) is in `step3_folds.json`. Fills proven
cost-independent (identical trade IDs across A/B/C/D reruns).
INFERENCE: execution clean, no leakage; economics negative in every
active fold at every cost level. LIMITATION: F3 contributes nothing;
F4 is a single trade.

## 7. Cost analysis (E5: FAIL)

MEASURED RESULT, pooled OOS (production-path reruns, 11B scenarios):
A −$0.33 (PF 0.72) / B −$4.53 (2/19) / C −$9.78 (0/21) / D −$17.02
(0/21). Consistent with 11B's ladder on Gate A data. INFERENCE: costs
do not merely reduce an edge — there is no gross edge for them to
reduce (pooled zero-cost net is already negative).

Separately-reported production finding (§21): production books
commission/slippage on pre-resize sizer notional (up to $500), while
`_resize_for_actual_entry` can shrink final notional far below it
(Gate A finals ≈ $22) — realized cost rates are therefore higher than
final-notional math suggests. Research used production reruns, so all
reported economics reflect actual booking. No production change made.

## 8. Cost break-even

MEASURED RESULT: gross edge/trade −$0.0156; modeled cost/trade (C)
+$0.45; break-even cost −$0.0156/trade; safety margin −$0.47.
INFERENCE: break-even is unrealistically low in the precise sense —
it is negative. No non-negative transaction cost clears zero.

## 9. Sample-size analysis (E6: INSUFFICIENT)

MEASURED RESULT: 21 pooled trades (14/6/0/1 per fold); win rate 66.7%
at zero cost collapsing to 0% at C; bootstrap 95% CI for expectancy
(−$0.53, −$0.41) — entirely negative but n=21 < pre-registered 30.
INFERENCE: adequate to show costs dominate (total C-cost $9.45 ≈ 29×
|gross|), inadequate to certify any positive edge claim. Per spec, E6
gates EDGE claims only, not the cost-driven RED.

## 10. Monte Carlo analysis (E9: FAIL)

MEASURED RESULT (5000 shuffles + 5000 bootstraps, seeds 1107001/2, pooled
C nets): P(loss) = 1.0; final p5/p50/p95 all −$9.78 (degenerate — every
trade negative, so order cannot change the sum); maxDD $9.78;
P(DD > observed) = 0.0; p95 losing streak 21. INFERENCE: risk profile is
certain loss at realistic costs; no sequence luck is available.

## 11. Regime analysis (E7: FAIL)

MEASURED RESULT (causal per-fold calibration; each fold's tercile
cutoffs from strictly-prior bars only — `step5_regimes.json` records
calibration window, OOS window, and threshold source per fold):

F1 (calib Aug 21–24, 4001 bars): high/above 3 (−$1.12), high/below
10 (−$4.90), mid/above 1 (−$0.44) — 0 wins everywhere.
F2 (calib +F1, 7334 bars): high/above 2 (−$1.10), high/below 2
(−$0.88), mid/below 2 (−$0.89) — 0 wins everywhere.
F3: no fills.
F4 (calib +F1–F3+D1, 19001 bars): mid/below 1 (−$0.45).
Gross/net are now reported separately per cell (e.g. F1 high/above:
gross +$0.23, net −$1.12 — costs dominate). INFERENCE: failure is
not a one-regime accident; no regime rescues the strategy.
LIMITATION: small cells (several below the 3-trade minimum).

## 12. Parameter sensitivity (no optimization)

MEASURED RESULT (pooled continuous D2+D3, netC): baseline −13.05 (28
fills, 0 wins); wait25 −13.05 (identical — expiry window irrelevant);
wait35 −13.05; delay2 −11.64 (25 fills); width008 −13.48; width012
−12.60. Zero-cost nets all ≈ −$0.39…−$0.45, 0 wins everywhere.
INFERENCE: not fragile — uniformly negative under every perturbation;
no perturbation rescues the economics, none was selected. (Pooled-
continuous fills, 28, differ from fold-concat, 21, via warmup/
continuity effects — documented; fold table remains the certified
per-fold evidence.)

## 13. Execution robustness (E8: FAIL)

MEASURED RESULT (overlays on C baseline −$9.78): V1 entry +0.5bp
adverse → −$9.84; V2 10% missed fills (seed 1107, dropped idx 4,13) →
−$8.64; V3 exits 1bp worse → −$9.91. First-order arithmetic on final
notionals; V2 occupancy feedback noted as approximation. INFERENCE:
already-failed economics stay failed; variations move ±$1 on a −$9.78
base — execution is not the deciding factor, costs and gross edge are.

## 14. Baseline comparison (E10: FAIL)

MEASURED RESULT: buy-and-hold $2000 BTC: D2 −$6.70 net (one round
trip), D3 +$0.42; combined ≈ −$6.28 vs strategy pooled C −$9.78.
Per-fold random-timing controls (500 draws each, fold-confined
entries/exits with MTM-at-boundary rule, frozen k=15.53, $500
notional, C costs): F1 strategy −$6.46 vs random median −$6.72
(50.8th percentile); F2 −$2.87 vs −$1.88 (44.0th); F3 INSUFFICIENT
(no fills); F4 −$0.45 vs −$0.45 (56.6th, single trade). No-trade = 0
beats the strategy by $9.78. INFERENCE: no evidence of value
beyond trivial alternatives; strategy timing is coin-flip grade.

## 15. Edge decomposition

MEASURED RESULT (gross pooled): payoff ratio 0.36 (avg win << avg
loss); top-1 trade = 32% of gross profit; leave-one-out nets range
−$0.60…+$0.21 — removing the best trade worsens, removing the worst
still leaves negative. INFERENCE: failure is broad-based (0/21 wins at
C), not one-trade-driven; the gross shape itself (PF 0.72) carries no
edge for costs to spare.

## 16. Data-mining / selection-bias assessment (E12: PASS by disclosure)

FACT: 16 research submodules under `core/research/` (analyzer,
breakout_asymmetry, conditional_ml, counterfactual, dataset,
discovery, features, intelligence, journal, lab, ml, oos, readback,
recommendation, regime, researcher); Phase 9 discovery/ML/regime
history; Phase 7 breakout work on the D2 lineage; 11B cost scenarios;
Gate A certifications. The frozen strategy is the survivor of extensive
prior experimentation on overlapping data — its apparent IS performance
cannot be read as independent evidence. No correction factor is
fabricated. This phase performed zero additional selection (single
frozen config throughout), so its OOS measurements are unbiased
conditional on that history.

## 17. Reproducibility (E11: PASS)

Deterministic components (folds, metrics, regimes, sensitivity,
baselines given seeds, evidence JSONs) reproduce exactly; research
metric definitions verified equal to production `PerformanceAnalytics`
(31 research tests: spec conformance, hand-computed metrics, parity,
determinism, break-even, R1-R5, RB1-RB6, M1-M6);
complete suite 1984 passed; compile clean; Gate A deterministic across
processes (27/11/6/5/0/0.117534); MC uses recorded seeds (1107001/2,
1107, 1108000–1108499) and re-runs identically (tested). Dataset hashes
recorded (`step1_integrity.json`, D3 fetch record). Environment: pinned
`requirements.txt` versions verified in a clean venv during prior
phases; this phase added no dependencies.

## 18. Certification gate table

| Gate | Result | Reason |
|---|---|---|
| E1 data integrity | PASS | 17,499 bars validated, 0 defects |
| E2 no lookahead | PASS | frozen pipeline, chronological folds, prior-data-only cutoffs |
| E3 independent OOS | PASS | D3 clean (2499 bars); D1/D2 contamination disclosed |
| E4-M walk-forward methodology | PASS | folds causal, no leakage |
| E4-E walk-forward economics | FAIL | pooled net(C) −$9.78 (same rule as E5) |
| E5 cost robustness | FAIL | pooled net(C) −$9.78; even gross −$0.33 |
| E6 sample adequacy | INSUFFICIENT | n=21 < 30 (gates edge claims, not cost RED) |
| E7 regime | FAIL | all cells negative; no rescue regime |
| E8 execution | FAIL | variations stay ≈ −$9…−$10 |
| E9 Monte Carlo | FAIL | P(loss)=1.0 at C |
| E10 baselines | FAIL | 48.6th percentile of random; worse than B&H and no-trade |
| E11 reproducibility | PASS | deterministic + tested |
| E12 data-mining | PASS | fully disclosed |

## 19. Limitations

Small OOS sample (21 trades; F3 empty; F4 single trade); OOS window
covers two Aug/Sep-2026 weeks only (no crisis/alt-season coverage);
single instrument (BTCUSDT) and timeframe (1m); funding rates unmodeled
(mild for minute-scale holds, noted); random-entry control uses fixed
2:1 exits (neutral conventional choice, documented); V2 occupancy
feedback approximated; prior-selection bias uncorrectable by design;
exchange-source truth assumed.

## 20. Final recommendation

NO-GO for any real-money use of BREAKOUT_CONTINUATION. Recommended
next steps (research, not LIVE): any future strategy work starts from
this evidence baseline with pre-registered designs; address funding-
rate modeling and the §7 pre-resize cost-basis finding through the
normal defect process (separately reported, untouched here); credential
rotation + history purge remain required before any live-readiness
discussion.

---

---

## 21. Closure corrections vs v1 evidence (11E-Closure)

| Metric | v1 (superseded) | Corrected | Difference / explanation |
|---|---|---|---|
| Pooled net(C) | −$9.78 | −$9.78 | none (economics identical) |
| Pooled gross | mislabeled (= net) | explicit gross/fees/slip split | reporting fix; net unchanged |
| Regime cells | pooled IS cutoffs (D1+D2) | per-fold strictly-prior calibration | composition shifted; all cells still 0 wins, negative |
| Random baseline | pooled, boundary-crossing | per-fold, MTM-at-boundary | F1 50.8th, F2 44.0th, F3 INSUFFICIENT, F4 56.6th (was pooled 48.6th) |
| Walk-forward label | E4 PASS + WALK-FORWARD FAIL | E4-M PASS / E4-E FAIL | terminology split, same rule |
| Verdict | RED / NO EDGE | RED / NO EDGE | corrections change nothing economically |

Corrected analysis remains strongly negative (Outcome A). Methodology
notes: `docs/audit/phase11e_closure_amendment.md`.

---

PHASE 11E: RED

EDGE STATUS:
NO EDGE

OOS STATUS:
FAIL

COST ROBUSTNESS:
FAIL

WALK-FORWARD:
FAIL

MONTE CARLO:
FAIL

REGIME ROBUSTNESS:
FAIL

EXECUTION ROBUSTNESS:
FAIL

REPRODUCIBILITY:
PASS

LIVE:
DISABLED

PRODUCTION STRATEGY MODIFIED:
NO

PHASE 12:
NOT STARTED

Limitations preventing a stronger verdict: none could — the verdict is
already maximally negative on economics; the evidence is insufficient
only in the sense that a larger sample would narrow the already-
negative confidence interval (bootstrap 95% CI entirely below zero).
