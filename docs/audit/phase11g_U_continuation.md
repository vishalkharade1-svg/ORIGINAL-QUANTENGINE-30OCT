# Phase 11G-U — Continuation Monitor & Machine-Verified Counts

FAST-PATH MONITOR PHASE. The availability probe shows zero new
post-cutoff provider files, so per the efficiency rule NO historical
re-validation was performed — only the deterministic availability
record + gate arithmetic. NO economic experiment was executed. No
hypothesis run, created, modified, or evaluated. No economics of any
kind (proven by scan). No optimization. No D3 contact (counters
0/0/0 before, during, after). Frozen 11G-K hashes re-verified;
H004/H007 stay failed; nothing resurrected, nothing promoted.

## 1. Starting HEAD / Final HEAD / Branch / Tree

Start: `e88c3a0b39997de440cc56543141c096ee4ed4f7` (T commit),
branch `main`, tree clean except the two pre-existing untracked
notes files. Final HEAD = the U commit (see git log). No history
rewritten.

## 2. Derived Fresh Cutoff (Re-Derived, Not Copied)

Latest exposed minute re-derived from the S readiness artifact
(contiguity lasts), the N feasibility spans, and the oos window
end: 2026-09-08T23:59Z (1788911940). FRESH_START_U 1788912000
(09-09T00:00Z), unit-tested as an exact tuple. Rule: qualifying
events require timestamp >= FRESH_START_U.

## 3. Provider Availability (Execution/Observation Timestamp 2026-09-09)

Execution date (system UTC at run time): 2026-09-09. This is the
observation timestamp — it must not be confused with the probe
target dates. Binance Vision daily aggTrades CHECKSUM probes
covered targets 09-09→09-21, both BTCUSDT and ETHUSDT (13
dates/symbol, 26 probes): HTTP 404 throughout. Calendar semantics
are explicit: the 09-09 target cannot exist yet (day in progress —
daily file publishes after day close), and 09-10→09-21 are future
dates (404 calendar-trivial, not lag evidence). The substantive
finding is only that 09-08 remains the newest acquirable day,
consistent with ~1-day publication lag. A 404 is recorded as
DATA_NOT_YET_AVAILABLE (archive-lag semantics), never as zero-bars.
Recorded as provenance observation metadata, excluded from
deterministic hashes. New files acquired: 0. New fresh bars: 0.

## 4. Gate (Per Symbol, No Pooling)

Required: 6,175 (derived from the certified builder signature
in-code, asserted in-test — never a copied constant). BTC fresh 0
(shortfall 6,175); ETH fresh 0 (shortfall 6,175); gate_met
false/false. Folds executed: 0. Expanding origin pinned by
positive control (7,000-bar build, exact F0 boundaries). No
shrinkage, no rolling, no stitching, no pooling.

## 5. Inventory / Quality / REAL Matrix / Regimes / Symbols

No new store (nothing newer exists). Reference spans stand as
certified (BTC 2,676 / ETH 2,880 clean bars, REUSED, ZERO overlap
vs checkable priors, D3 UNKNOWN_BY_SEAL). Fast path performs no
bulk re-parsing; reference quality stands (zeros across every
gate). REAL/DERIVED event model preserved; PROXY: none;
UNAVAILABLE: bulk L2/quotes/resting/queue/book/spread/
liquidations. Regime/symbol descriptives: referenced, never pooled,
no thresholds fit.

## 6. Trigger / Hypotheses / Economics (All Negative)

Trigger met: false. Decision: DATA_NOT_YET_AVAILABLE (readiness in
effect: DATA_STILL_INSUFFICIENT). Hypotheses executed: 0.
Economics executed: false (`refuse_economics()` raises; no economic
entry point by member scan). Methodology constants re-pinned
read-only (cost ladder, tiers 30/3/2/3, Bonferroni 0.00625, seeds,
declared negative controls). H004/H007 re-pinned FAIL.

## 7. Lookahead / Determinism / Mutations (22) / D3 / Isolation

Lookahead: future-appended trades leave earlier bars/volumes/
quality identical. Determinism: monitor rerun byte-identical vs
committed `readiness_u.json`. Mutations: duplicate ID/minute,
reorder, timestamp corruption, negative quantity, invalid
aggressor, checksum/normalized/transformation tampering, symbol/
venue/freshness/overlap tampering, gap stitching, synthetic
insertion, pooled qualification, WF shrink, rolling, future
insertion, hypothesis/economic execution refusal, D3 access
(refused, counters 0) — all detected/refused. D3: READ 0 / HASH 0
/ LOAD 0 throughout. Production isolation: AST import scan clean
(stdlib + research.* only), no runtime tokens, report object
permanently non-production (frozen + enforced), production tree
clean, LIVE unset. Resume trigger: next unchecked date 2026-09-22
both symbols (deterministic from the observation).

## 8. Machine-Verified Test Counts (§35)

`research/phase11g_u/counts.py` walks unittest's own loader (the
same machinery `discover` uses) and returns per-family counts plus
the total; the reconciliation equation is asserted in-test. Machine
output pre-commit:

```
baseline = 2181
families = N42 O49 P47 Q58 R50 S57 T50 (sum 353)
main_total = 2534
research_total = 422
reconciled = true
```

Post-commit expectation: 2,534 + 54 U = 2,588 (verified below from
actual runner output; composition: 2,181 + 42 + 49 + 47 + 58 + 50
+ 57 + 50 + 54). No hand arithmetic in the gate path; every number
above is command output.

## 9. Full Suite / Compileall / Gate A (Post-Commit Actuals)

Phase U file: 54/54. Research suites: 422/422. Main suite: 2,588
collected, 0 failed/errors/skipped (actual output). Zero
prior-test modifications in this phase (N/O/P/Q/R/S files
untouched — U scope is strictly additive). No test weakened; no
production file touched. Compileall clean. `git diff --check`
clean. Gate A ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 10. Documentation Convention

No STATUS.md / import_manifest / project_manifest updates: git log
proves 11G-K/L/M/N/O/P/Q/R/S/T (all research-only) made none —
those manifests track production files, and U adds none. PHASE
11G-U recorded here.

## 11. Final Decision: DATA_NOT_YET_AVAILABLE

```
required = 6175
BTC fresh = 0
BTC shortfall = 6175
ETH fresh = 0
ETH shortfall = 6175
```

Readiness in effect: DATA_STILL_INSUFFICIENT. STOP — WAIT FOR
ADDITIONAL PROVIDER DATA. DO NOT WEAKEN THE 6,175-BAR GATE.
