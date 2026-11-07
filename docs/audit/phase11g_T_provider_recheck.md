# Phase 11G-T — Provider Recheck & 6,175-Bar Readiness Monitor

FAST-PATH MONITOR PHASE. The availability probe shows zero new
post-cutoff provider files, so per the phase's efficiency rule NO
historical re-validation was performed — only the deterministic
availability record + gate arithmetic. NO economic experiment was
executed. No hypothesis run, created, modified, or evaluated. No
economics of any kind (proven by scan). No optimization. No D3
contact (counters 0/0/0 before, during, after). Frozen 11G-K hashes
re-verified; H004/H007 stay failed; nothing resurrected, nothing
promoted.

## 1. Starting HEAD / Final HEAD / Branch / Tree

Start: `2942b57f85957e7a48546f9baea935d6437f39bd` (S commit),
branch `main`, tree clean except the two pre-existing untracked
notes files. Final HEAD = the T commit (see git log). No history
rewritten.

## 2. Derived Fresh Cutoff (Re-Derived, Not Copied)

Latest exposed minute re-derived from the S readiness artifact
(contiguity lasts), the N feasibility spans, and the oos window
end: 2026-09-08T23:59Z (1788911940). FRESH_START_T 1788912000
(09-09T00:00Z). Rule: qualifying events require timestamp >=
FRESH_START_T. Cutoff derivation is unit-tested (exact tuple).

## 3. Provider Availability (Observed 2026-09-09)

Binance Vision daily aggTrades CHECKSUM probes: HTTP 404 for
09-09→09-20, both BTCUSDT and ETHUSDT (12 dates/symbol, 24 probes).
09-08 remains the newest acquirable day. A 404 is recorded as
DATA_NOT_YET_AVAILABLE (archive-lag semantics), never as zero-bars.
Recorded as provenance observation metadata, excluded from
deterministic hashes. New files acquired: 0. New fresh bars: 0.

## 4. Dataset Inventory (Reference Spans, REUSED)

No new store (nothing newer exists). Reference: BTC 2,676 clean
bars (09-07T03:24→09-08T23:59); ETH 2,880 (09-07T00:00→09-08T23:59).
Freshness REUSED (descriptive exposure, no fits, no economics);
overlap ZERO vs all checkable priors (re-verified logic; no new
minutes to compare); D3 UNKNOWN_BY_SEAL. Per-symbol gate records:
fresh 0/0, shortfalls 6,175/6,175, gate_met false/false. No
pooling (gate keys BTC/ETH only).

## 5. Quality / REAL Matrix / Regime / Symbols

Fast path performs no bulk re-parsing (nothing new to validate);
reference quality stands as certified in N/O/P/Q/R (zeros across
every gate; kline cross-checks 0.0). REAL: price/quantity/
ms-timestamp/agg-IDs/provider aggressor side; event model
aggregate. PROXY: none. UNAVAILABLE: L2/quotes/resting/queue/book/
spread/liquidations. No thresholds fit; no economics.

## 6. Registered WF Geometry (Derived, Not Hardcoded)

`required_bars()` reads the certified builder signature
(train 2000 + 3×step 1000 + purge 150 + embargo 25 + test 1000) and
returns 6,175 — asserted in-test. Positive control: 7,000-bar
build yields nested expanding trains with exact F0 boundaries.
Builder raises on both reference spans. Folds executed: 0. No
shrinkage, no rolling, no stitching, no pooling.

## 7. Trigger / Hypotheses / Economics (All Negative)

Trigger met: false. Decision: DATA_NOT_YET_AVAILABLE (provider
reason; readiness remains DATA_STILL_INSUFFICIENT in effect).
Hypotheses executed: 0. Economics executed: false (tested).
Methodology constants re-pinned read-only (cost ladder, tiers
30/3/2/3, Bonferroni 0.00625, seeds, declared negative controls).
H004/H007 re-pinned FAIL. The monitor exposes `refuse_economics()`
(raises) and no economic entry point (member scan).

## 8. Lookahead / Determinism / Mutations (22) / D3 / Isolation

Lookahead: future-appended trades leave earlier bars/volumes/
quality identical. Determinism: monitor rerun byte-identical vs
committed `readiness_t.json` (seconds — no bulk work). Mutations:
duplicate ID/minute, reorder, timestamp corruption, negative
quantity, invalid aggressor, checksum/normalized/transformation
tampering, symbol/venue/freshness/overlap tampering, gap
stitching, synthetic insertion, pooled qualification, WF shrink,
rolling, future insertion, hypothesis/economic execution refusal,
D3 access (refused, counters 0) — all detected/refused. D3: READ 0
/ HASH 0 / LOAD 0 throughout. Production isolation: AST import
scan clean (stdlib + research.* only), no runtime tokens, report
object permanently non-production (frozen + enforced), production
tree clean, LIVE unset.

## 9. Test Counts (Actual Command Output, §23)

Phase T file: 50/50 (actual `Ran 50 tests ... OK`, ~0.4 s — the
fast path performs no bulk parsing by design). Research suites:
422/422. Main suite: 2,534 collected = 2,484 + 50 T (prior "2,484"
was pre-T; composition: 2,181 baseline + 42 N + 49 O + 47 P + 58 Q
+ 50 R + 57 S + 50 T = 2,534): 0 failed/errors/skipped. Zero prior-test modifications in this phase
(the N/O/P/Q/R allowlist cascades were left untouched; T needs
none — its scope is strictly additive). No test weakened; no
production file touched. Compileall clean. `git diff --check`
clean. Gate A ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 10. Documentation Convention

No STATUS.md / import_manifest / project_manifest updates: git log
proves 11G-K/L/M/N/O/P/Q/R/S (all research-only) made none — those
manifests track production files, and T adds none. PHASE 11G-T
recorded here.

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
