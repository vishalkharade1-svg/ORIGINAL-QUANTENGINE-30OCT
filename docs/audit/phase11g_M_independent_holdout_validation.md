# Phase 11G-M — Independent Holdout Validation Report

ABSOLUTE HOLDOUT PHASE. Outcome: NO ELIGIBLE HYPOTHESIS FOR HOLDOUT.
No D3 dataset was acquired, opened, or evaluated. The sealed holdouts
remain sealed (counters 0/0/0 throughout, verified before, during,
and after). This is a valid research outcome, executed exactly per
the phase specification.

## 1. Starting HEAD

`eb35cc4c20ba1e852d63a8b9776b099490bedded`
(`research(phase11g): execute real orderflow economic research`),
branch `main`, tree clean except two pre-existing untracked notes
files (present since before 11G-K, never touched).

## 2. Final HEAD

The M commit carrying `research/phase11g_m/` + this report (see
`git log`; message `research(phase11g): validate real orderflow on
independent holdout`).

## 3. Chain Verification

Starting HEAD + 11G-K freeze (8 hashes + `f803fe7d…`) + 11G-L report
and `fold_results.json` verified read-only before any M step. All
hashes reproduced. No frozen file modified (git scope check clean).

## 4. D3 Authorization

NONE GRANTED. The mechanical eligibility determination (§9) returned
an empty eligible set (see §9), so no validation purpose existed and
no D3 opening was authorized. D3_OPEN_TIMESTAMP: N/A (never opened).

## 5. D3 Lineage

No D3 dataset was created, acquired, or contacted by this phase. The
pre-existing sealed holdouts (11F/11G-D lineage) were never read,
hashed, or loaded by M code (proven by counters, §27 of spec /
§28 here). Lineage test pins: M tree contains code + the
eligibility record only — zero data blobs.

## 6. D3 Dataset Hashes

N/A — no D3 dataset exists for this phase. Reference (untouched):
development dataset `binance_um_aggtrades_BTCUSDT_2026-09-05`,
hash `440c9191…`, pinned read-only.

## 7. Overlap Analysis

Vacuous: with no M dataset, there is nothing whose overlap must be
tested. Non-contact is proven cryptographically by the seal counters
(0/0/0 across both guarded modules, recorded inside the eligibility
artifact before and after determination).

## 8. D3 Scale

N/A — no D3 execution. No folds were manufactured to fit unavailable
data (§6/§12: STOP-that-analysis semantics honored by not starting).

## 9. Hypothesis Eligibility (Mechanical §9 Rule)

Rule applied to 11G-L outcomes + frozen `promotion_policy` (all 8 =
`"NONE"` — no explicit holdout permission exists anywhere frozen):
FAIL → resurrection barred; zero pooled events → not promoted
(promotion would be discovery); INSUFFICIENT → proceeds only with
explicit permission → permission absent → excluded.

| Hypothesis | Dev Verdict | Dev n | Promotion | Branch | Eligible |
|------------|-------------|-------|-----------|--------|----------|
| H11GK-001 | INSUFFICIENT_EVIDENCE | 6 | NONE | SUB_ELIGIBLE_PERMISSION_ABSENT | NO |
| H11GK-002 | INSUFFICIENT_EVIDENCE | 2 | NONE | SUB_ELIGIBLE_PERMISSION_ABSENT | NO |
| H11GK-003 | INSUFFICIENT_EVIDENCE | 1 | NONE | SUB_ELIGIBLE_PERMISSION_ABSENT | NO |
| H11GK-004 | FAIL | 43 | NONE | RESURRECTION_BARRED | NO |
| H11GK-005 | INSUFFICIENT (n=0) | 0 | NONE | ZERO_EVENTS_NOT_PROMOTED | NO |
| H11GK-006 | INSUFFICIENT (n=0) | 0 | NONE | ZERO_EVENTS_NOT_PROMOTED | NO |
| H11GK-007 | FAIL | 43 | NONE | RESURRECTION_BARRED | NO |
| H11GK-008 | INSUFFICIENT (n=0) | 0 | NONE | ZERO_EVENTS_NOT_PROMOTED | NO |

Eligible set: []. Determination artifact
`research/phase11g_m/eligibility/eligibility.json`, sha256
`afd8cae539b1ede83d03b0852f36062ead10c8e9eac8817901c30615656ab8b8`
(determiner code hash `ce1519be…3456`). Result:
NO_ELIGIBLE_HYPOTHESIS_FOR_HOLDOUT.

## 10. Frozen Hypothesis Hashes

All 8 canonical hashes reproduce against the freeze manifest; freeze
`f803fe7d8aae896e`; family count 8; feature version
`real-trade-features-v1`. Hypotheses immutable (never edited, no v2).

## 11. Fold Geometry

No M folds created. L geometry re-validated read-only from the L
artifact (F0 [0,300)/[475,775), F1 [0,600)/[775,1075), F2
[0,900)/[1075,1375); purge 150, embargo 25): validators empty;
rolling mutant trips expanding check; gap-shrink detected. M created
no fold artifacts.

## 12. Causality

Feature-level adversarial attacks on synthetic fixtures (no
economics, no datasets): appending a trade strictly after a decision
boundary leaves earlier `window_vol`/CVD/CVD-slope identical
(MUT-M1/M2 green); aggressor-flip moves delta sign (positive control).
No D3 boundary exists to attack; L bundle prefix-stability stands
referenced, not re-executed.

## 13. Execution

No M execution occurred. Frozen NBO contract re-pinned read-only
from L artifacts: every recorded fill `NEXT_BAR_OPEN`,
entry_time − decision_time = 60, entry = next-bar open,
gross − commission − slippage = net for all recorded trades.

## 14. Cost Model

Frozen ladder re-pinned (A zeros; B 0.05%+2bp; C 0.059%+5bp; D 2×C);
mutant inequality green. Every recorded Cost-C trade carries
positive commission+slippage on positive notional (MUT-M6/M7: no
omission). No M costs applied.

## 15. Sample-Size Gate

Tiers pinned (<10 NO EVIDENCE; 10–29 INSUFFICIENT; ≥30 eligible;
≥100 stronger; 30/3/2/3 minima). L counts against tiers: 43/43
(sufficient, then falsified), 6/2/1 (insufficient), 0/0/0 (no
evidence). Thresholds never lowered.

## 16. Complete D3 Results

N/A — no hypothesis tested (see §9). No result fabricated.

## 17. Development-vs-D3 Comparison

| Hypothesis | Development | D3 | Survived? |
|------------|-------------|----|-----------|
| H11GK-001 | INSUFFICIENT (6, netC −5.96) | N/A (not tested) | NO (untested; nothing to survive) |
| H11GK-002 | INSUFFICIENT (2, netC −2.41) | N/A | NO |
| H11GK-003 | INSUFFICIENT (1, netC −1.10) | N/A | NO |
| H11GK-004 | FAIL (43, netC −33.05) | N/A (barred) | NO (falsified; stays failed) |
| H11GK-005 | NO EVIDENCE (0) | N/A | NO |
| H11GK-006 | NO EVIDENCE (0) | N/A | NO |
| H11GK-007 | FAIL (43, netC −35.51) | N/A (barred) | NO (falsified; stays failed) |
| H11GK-008 | NO EVIDENCE (0) | N/A | NO |

Development results are quoted, never hidden (§34). No development
winner exists to compare; the two falsified hypotheses stay failed.

## 18. Cost Sensitivity

N/A on D3 (no runs). Reference: dev ladder strictly monotone for
every hypothesis (A ≥ B ≥ C ≥ D); 004 gross ≈ zero turns negative
under any cost; 007 negative at all costs.

## 19. Ablations

Not executed on D3: no eligible primaries exist, and §22 forbids
ablation-driven rescue (a failed primary is never replaced by an
ablation). Dev ablation reference stands (17 coherent + 1
degenerate-skip + 1 blocked; all pooled Cost-C ≤ 0).

## 20. Random Baseline

Methodology re-pinned (500 draws, seeds 1108000–1108499, Cost C,
frozen 2:1 train-median exits, V2 seed 1107). Not run in M (no
eligible hypotheses, no folds). Dev reference: strategies sat inside
the random band.

## 21. Monte Carlo

Seeds/counts re-pinned (5000 shuffles/1107001, 5000
bootstraps/1107002). Not run in M. Dev reference: p_loss = 1.000
for both FAILs.

## 22. Regime Analysis

Frozen methodology re-pinned per JSON (fit = training data only;
trend = close vs SMA50; volatility = ATR14/close terciles). M fit
nothing. Dev reference: every sufficient cell negative.

## 23. Symbol Analysis

| Hypothesis | BTC | ETH | Other Symbols | Direction |
|------------|-----|-----|---------------|-----------|
| all 8 | N/A (not tested) | N/A | N/A | N/A (no claims) |

Dev ran BTCUSDT only; no cross-symbol inference made anywhere.
Frozen direction rules pinned present (read-only).

## 24. Directional Analysis

No directional claims in M (eligible set empty; LONG/SHORT tokens
absent from the eligibility record by test). No LONG→SHORT or
symbol→symbol inference.

## 25. Multiple Testing

Family denominator 8 retained (FAILs included, never removed);
hypotheses tested on D3: 0; eligible: 0. Corrections pinned
(Bonferroni 0.00625, BH-FDR q = 0.10). Nothing survived because
nothing was tested — and the family frame is preserved for any
future preregistered work, not consumed here.

## 26. Mutation Tests (MUT-M1..M14)

M1 future-trade leak: GREEN (features invariant). M2 future-CVD
leak: GREEN. M3 D3 contamination: GREEN (sealed loaders/registry
refuse; counters still 0). M4 threshold change: GREEN. M5 cost
change: GREEN. M6 fee omission: GREEN. M7 slippage omission: GREEN.
M8 execution timing: GREEN (NBO + 60s pins). M9 regime lookahead:
GREEN (train-only pins; nothing fit). M10 fold leakage: GREEN.
M11 seed manipulation: GREEN (constants + draw sensitivity). M12
dataset substitution: GREEN. M13 hypothesis hash modification:
GREEN (all 8). M14 result tampering: GREEN (copy-tamper changes
canonical hash). All mutations restored (nothing was ever changed).

## 27. Deterministic Rerun

The only M artifact regenerates byte-identical (subprocess rerun,
bytes compared). L determinism referenced (96/96 identical, pinned
in its artifact). No stochastic M step exists.

## 28. Production Isolation

`core/ config/ data/ execution/ risk/ backtesting/ main.py` clean
(git scope check in-test, green). ALLOW_LIVE/LIVE_EXECUTE unset.
No order-submission/paper/shadow tokens in any M file (scanned).
No exchange writes (no exchange code paths touched at all).

## 29. Gate A ×2

PASS ×2: 27 orders, 11 fills, 6 wins, 5 losses, 0 BE, net
+0.117534, identical IDs (production path unaffected by M).

## 30. Limitations

Binance venue only (Binance ≠ Delta, moot — no data used);
aggregate-trade resolution; ms precision; no L2/quotes/resting
truth; no D3 duration/symbols to report (none acquired); L fold
adaptation stands as documented; L path limits (no time-stop, no
post-exit cooldown, boundary drops) stand undisputed.

## 31. Final Verdict

NO_ELIGIBLE_HYPOTHESIS_FOR_HOLDOUT — and therefore NO-GO: NO ROBUST
REAL ORDER-FLOW EDGE FOUND. 11G-L's FAILs stay failed (never
retested, never resurrected); its insufficient/silent hypotheses
stay unpromoted (no permission, no discovery on holdout). D3 was
never contacted and remains sealed. This no-go is a successful
research result. Nothing follows in this phase: no tuning, no new
hypotheses, no 11G-K reopen, no production change, no paper/shadow/
live activity.
