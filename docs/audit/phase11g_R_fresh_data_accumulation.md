# Phase 11G-R — Fresh Data Accumulation & 6,175-Bar Qualification

DATA-ONLY PHASE. The readiness gate (≥6,175 contiguous clean FRESH
bars on one symbol) is NOT satisfied: zero post-cutoff minutes are
acquirable, so per the phase rules NO economic experiment was
executed. This report certifies DATA_STILL_INSUFFICIENT with exact
arithmetic. No hypothesis run, created, modified, or evaluated. No
economics of any kind (proven by scan). No optimization. No D3
contact (counters 0/0/0 before, during, after). Frozen 11G-K hashes
re-verified; H004/H007 stay failed; nothing resurrected, nothing
promoted.

## 1. Starting HEAD / Final HEAD / Branch / Tree

Start: `29959c536610be610653bf34ac7fd331270d96fa` (Q commit),
branch `main`, tree clean except the two pre-existing untracked
notes files. Final HEAD = the R commit (see git log). No history
rewritten.

## 2. Provider / Fresh Cutoff / Availability / New Files / New Fresh Bars

Provider: Binance Vision (official archive, per-zip CHECKSUMs).
Cutoffs re-derived, not copied: PRE_CUTOFF 1788751380 (oos end),
FRESH_START_R 1788912000 (09-09T00:00Z, strictly after the latest
exposed minute 09-08T23:59Z). Availability observation (provenance
metadata): Vision CHECKSUM probes return HTTP 404 for 09-09→09-18
daily aggTrades, both BTCUSDT and ETHUSDT — 09-08 remains newest;
DATA_NOT_YET_AVAILABLE. New files acquired: 0. New fresh bars: 0.

## 3. Per-Symbol Gate Arithmetic (§36)

Required: 6,175 (derived from the certified builder signature:
2000 + 3×1000 + 150 + 25 + 1000 — not a copied constant).

BTC: fresh bars 0, contiguous bars n/a (reference REUSED span
2,676/2,676, 0 gaps), shortfall = 6,175 − 0 = 6,175.
ETH: fresh bars 0, reference 2,880/2,880, shortfall = 6,175.

No pooling (gate evaluated per symbol; pooled entry absent by
construction). No rounding (exact integers).

## 4. Dataset Inventory (Reference + Empty R Store)

N store re-verified immutable (4/4 zips re-hash to acquisition
manifests). R store: absent/empty (nothing newer exists to
acquire). Reference spans: BTC 09-07T03:24→09-08T23:59 (2,676),
ETH 09-07T00:00→09-08T23:59 (2,880); freshness REUSED (N/O/P/Q
descriptive exposure, no fits, no economics); overlap ZERO vs all
checkable priors; D3 UNKNOWN_BY_SEAL.

## 5. Data-Quality Results / REAL Matrix / Regime / Symbol Coverage

Re-parsed 3,572,238 rows: 0 rejected, 0 duplicate IDs, 0
out-of-order, 0 bad-precision. Spans minute-aligned, contiguous.
REAL: price/quantity/ms-timestamp/agg-IDs/provider aggressor side;
DERIVED: OHLCV/delta/CVD/footprint/imbalance/aggression; event
model aggregate. PROXY: none. UNAVAILABLE: L2/quotes/resting/queue/
book/spread/liquidations. Regime/symbol descriptives recomputed per
symbol, never pooled, no thresholds fit.

## 6. Registered WF Geometry / Folds Executed = 0

Authoritative 2000/1000/150/25/1000/4 pinned (signature-derived).
Certified builder probed: raises on both reference spans (2,676 /
2,880 < 6,175). Folds executed: 0 (none manufactured). Expanding
origin pinned by positive control (7,000-bar build: nested
[0,2000)→[0,5000), exact F0 purge [2000,2150)/embargo [2150,2175)/
test [2175,3175)). No shrinkage, no rolling, no stitching.

## 7. Hypotheses / Economics Executed = NO

Hypotheses executed: 0. Trades/PnL/expectancy/Sharpe/Sortino/PF/win
rate/drawdown/baseline/Monte Carlo: all NOT_EXECUTED (tested as
literal field values). Methodology constants re-pinned read-only
(cost ladder values, sample tiers 30/3/2/3, Bonferroni 0.00625,
seeds 1108000+/1107001/1107002, declared negative controls
present). H004/H007 verdicts re-pinned FAIL from the L artifact.

## 8. Lookahead / Determinism / Mutations / D3 / Isolation

Lookahead: future-appended trades leave earlier bars/volumes/
quality identical. Determinism: gate rerun byte-identical vs
committed `readiness_r.json`. Mutations: duplicate ID/minute,
ordering, timestamp corruption, negative quantity, invalid
aggressor, checksum/normalized/transformation tampering, symbol/
venue/freshness/overlap tampering, gap stitching, synthetic
insertion, WF shrink, rolling, future contamination, D3 access
(refused, counters 0), hypothesis/cost/metric modification,
economics-attempt scan — all detected/refused. D3: READ 0 / HASH 0
/ LOAD 0 throughout. Production isolation: AST import scan clean
(stdlib + research.* only), no runtime tokens, report object
permanently non-production (frozen + enforced), production tree
clean, LIVE unset.

## 9. Test Counts / Full Suite / Compileall / Gate A

Phase R file: 50/50. Research suites: 422/422. Main suite:
2,427 collected = 2,377 + 50 R (prior "2,377" was pre-R; delta fully
explained): 0 failed/errors/skipped. Four additive tree-allowlist
edits disclosed (N/O/P/Q tree tests gained the R paths;
post-commit behavior identical). No test weakened; no production
file touched. Compileall clean. `git diff --check` clean. Gate A
×2: 27/11/6/5/0/+0.117534, identical IDs.

## 10. Limitations

Two symbols/two reference days; REUSED minutes; D3 era unknowable;
Vision lag + retrospective updates; no bulk quotes/L2/funding/OI;
thin trend variety; pre-cutoff drops excluded; any future
preregistration must re-derive minute admissibility.

## 11. Final Decision: DATA_STILL_INSUFFICIENT

```
required = 6175
BTC fresh = 0
BTC shortfall = 6175
ETH fresh = 0
ETH shortfall = 6175
```

Provider reason: DATA_NOT_YET_AVAILABLE (nothing past 09-08
published). STOP. No OOS economics, no D3 opening, no new
hypotheses, no promotion, no paper/live. Wait for additional
provider data, then re-audit — never weaken the gate.
