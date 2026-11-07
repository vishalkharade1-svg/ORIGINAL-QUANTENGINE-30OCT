# Phase 11G-N — Fresh-Data Scale + New Research Eligibility Audit

RESEARCH-ONLY PHASE. No hypothesis created, modified, or evaluated.
No economics. No optimization. No D3 contact (counters 0/0/0 before,
during, and after — recorded inside the feasibility artifact). The
eight frozen 11G-K hypotheses are untouched (hashes re-verified);
H004/H007 stay failed; nothing resurrected, nothing promoted.

## 1. Starting HEAD / Final HEAD / Branch / Tree

Start: `004b2bcbe5f3ea8ab0b4d2be246bbb25dde61db2`
(`research(phase11g): validate real orderflow on independent
holdout`), branch `main`, tree clean except two pre-existing
untracked notes files (present since before 11G-K, never touched).
Final HEAD = the N commit (see git log). No history rewritten.

## 2. Lineage Reconstruction (Verified, Not Assumed)

11F D1 08-26T14:44→08-29T09:24, D2 08-29T09:25→08-31T11:24 (BTC+ETH
OHLCV); D3 sealed, era unknowable without opening. 11G-G gaps
(Delta `/v2/history/candles`) 08-31T11:25→09-01T22:24. Gate-A
snapshot 09-01T22:25→09-05T09:44 (BTC). 11G-I dev day (Binance UM
aggTrades) 09-05 full day. oos_fresh (DeltaHistory, Delta venue)
09-05T09:45→09-07T03:23. 11G-K freeze `f803fe7d…` (8 hashes OK).
11G-L: 004/007 FAIL, 001/002/003 INSUFFICIENT, 005/006/008 silent,
NO EDGE. 11G-M: eligible set empty, D3 never opened, NO-GO.

## 3. Provider Matrix (Official Docs Only)

Binance Vision archive (`binance/binance-public-data`, MIT, free, no
auth, CHECKSUM per zip, daily next-day + monthly): UM-futures
aggTrades (agg_trade_id/price/quantity/first/last/transact_time/
is_buyer_maker, ms precision), klines (all intervals incl. 1m),
trades. Verified live: 08-30→09-08 present; 09-09+ absent (~1-day
lag). No quotes/L2/snapshots/deltas/funding/OI/liquidations/mark/
index in the bulk archive (fapi REST exposes funding history max
1000 rows, OI statistics, forceOrders — paginated, retention-limited,
not bulk-archived; unsuitable for multi-day 1m WF scale).
Delta Exchange docs (`docs.delta.exchange` + support articles):
`/v2/history/candles` (1m+, ≤2000/request, candles + funding/mark/
OI history, public); recent-trades endpoint only (no bulk historical
tick/trade archive documented); historical L2/deltas not documented
as bulk; aggressor-side semantics on historical trades UNKNOWN.
Delta BTCUSD is inverse, Binance BTCUSDT linear — never pooled.

## 4. Dataset Inventory (Acquired Minimum: 4 Day-Files, ~47 MB)

| Dataset | Venue | Span (UTC) | Bars | Events | Freshness | Overlap |
|---------|-------|-----------|------|--------|-----------|---------|
| BTCUSDT 2026-09-07 aggTrades+klines | Binance UM | 09-07T03:24→23:59 (204 oos minutes dropped) | 1236 clean | 739,584 | FRESH | ZERO (6/6 sets) |
| BTCUSDT 2026-09-08 aggTrades+klines | Binance UM | full day | 1440 | 1,028,583 | FRESH | ZERO |
| ETHUSDT 2026-09-07 aggTrades+klines | Binance UM | full day | 1440 | 829,122 | FRESH | ZERO (3/3 sets) |
| ETHUSDT 2026-09-08 aggTrades+klines | Binance UM | full day | 1440 | 974,949 | FRESH | ZERO |

Clean totals: BTC 2,676 bars / 1,768,167 events; ETH 2,880 /
1,804,071 (~884k/~902k events/day). All 8 zips CHECKSUM-verified
(provider == local sha256); source hashes re-verified at analysis.
No pre-08-31 span is acquirable without colliding Gate-A/11G-G/D2
eras — the forward span is the only zero-overlap direction.

## 5. Data-Quality Results

Parsed 3,572,238 rows, 0 rejected, 0 duplicate trade IDs, 0
out-of-order events, 0 bad-precision events. Klines 1,440/1,440 all
days, 0 rejected. Trade-built closes vs klines: max abs diff 0.0 on
all 5,556 matched minutes. Missing clean minutes: 0 both symbols.
Every reject class instrumented; nothing dropped silently (there was
nothing to drop).

## 6. REAL / PROXY / UNAVAILABLE Matrix (N Data)

Aggressor side REAL (provider `is_buyer_maker`, certified mapping);
price/quantity/ms-timestamp/trade-IDs REAL; OHLCV DERIVED_FROM_REAL;
event model aggregate (aggTrade != individual fill, explicit).
PROXY: none introduced. UNAVAILABLE: quotes, L2, snapshots, deltas,
funding, OI, liquidations, mark/index, resting-liquidity truth.
Side never inferred (CSV carries no symbol column either — symbol
binding is file-level: manifest == directory == dataset key, tested).

## 7. WF Feasibility

Registered geometry (2000/1000/150/25/1000/4) requires 6,175
chronological 1m bars. Available clean: BTC 2,676, ETH 2,880. The
certified builder raises on both → FULL_WF_INFEASIBLE. No geometry
shrinkage, no rolling substitution, no custom folds, no symbol
pooling — the shortfall (~3,500/~3,300 bars, ≈2.5 further clean
days) is reported, not engineered around.

## 8. Regime Coverage (Descriptive Only)

BTC: 0 up / 2 down days; 1m-return p10/p90 ±~4.5bp, extremes ±~21bp;
ATR14/close p10/p90 2.3bp/6.8bp. ETH: 0 up / 2 down; returns
±~6bp, extremes ±~30bp; ATR ratio 3.8bp/9.9bp. Variation exists
intraday, but trend coverage is thin (no up days) — recorded as a
limitation for any future design. No thresholds fit; deciles must
not be reused as such.

## 9. Symbol Coverage

BTCUSDT + ETHUSDT, per-symbol tables above; temporal spans
BTC [09-07T03:24, 09-08T23:59], ETH [09-07T00:00, 09-08T23:59];
densities ~613/~626 events/min; missingness 0. No economic
inference; reported separately, never pooled.

## 10. D3 Seal Counters

0/0/0 (READ/HASH/LOAD, both guarded modules) before and after —
asserted in code and recorded in `feasibility.json`. No D3 read,
hash, load, inspection, benchmark, or sample-size use. No exceptions.

## 11. Mutation Results (MUT-N1..N14)

N1 future-data contamination: GREEN. N2 timestamp shift: GREEN. N3
dataset substitution: GREEN. N4 hash tampering: GREEN. N5 duplicate
injection: GREEN. N6 event-order: GREEN (totals invariant, sequence
flags). N7 symbol substitution: GREEN (file-level binding pinned).
N8 venue substitution: GREEN. N9 freshness tampering: GREEN. N10 D3
access attempt: GREEN (refused, counters still 0). N11 WF shrink:
GREEN (full geometry raises; shrink detected as different plan).
N12 rolling substitution: GREEN. N13 threshold modification: GREEN.
N14 capability misclassification: GREEN.

## 12. Determinism Result

`analyze()` rerun byte-identical against the committed
`feasibility.json` (in-test, subprocess + direct). No clock, UUID,
random, or `hash()` in deterministic paths (scanned by construction;
acquisition timestamp lives only in manifests as labeled provenance
metadata, excluded from all hashes).

## 13. Production Isolation Result

AST import scan of `research/phase11g_n/`: stdlib + `research.*` +
`httpx` (fetcher) only — no `core.*`/`backtesting`/`data`/`execution`/
`risk`/`config`/`main` production imports; no order/paper/shadow/live
tokens. `NFeasibilityReport.is_production_ready` permanently False
(enforced, `ValueError` on True). Production tree clean; LIVE unset.

## 14. Test Counts

N file `tests/test_researcher_11g_n.py`: 42/42. Research suites:
422/422 (380 prior + 42 M — N adds none under `research/`, its tests
live in `tests/` per repo convention). Main suite: 2,223 OK
(2,181 + 42 N), 0 failures. `compileall -q .` clean.
`git diff --check` clean. Gate A ×2: 27/11/6/5/0/+0.117534,
identical IDs. Existing tests unmodified and unweakened.

## 15. Manifest Decision (§26)

No STATUS.md / import_manifest / project_manifest updates: verified
by git log that 11G-K/L/M (all research-only) made none — production
manifests track production files, and N adds none. Convention
followed, not broken.

## 16. Final Decision: PATH B — DATA EXISTS BUT INSUFFICIENT SCALE

Fresh, quality-clean, zero-overlap Binance UM data exists (2 symbols
× ~2 days, ~3.6M events), but cannot support the registered 4-fold
expanding-origin geometry (2,676/2,880 << 6,175 required).

```
RECOMMEND_NEXT_PHASE = DATA_EXPANSION_REQUIRED
```

Trigger for re-audit: ≥6,175 contiguous zero-overlap clean 1m bars
on one symbol (≈5 clean days; Vision lags ~1 day, so earliest
re-check after 09-13 data lands), plus up-day regime presence. Then
a NEW preregistration (frozen hypotheses only — 004/007 stay failed;
no resurrection; no tuning) may be justified. NO STRATEGY
PROMOTION, NO PAPER, NO SHADOW, NO LIVE, NO PRODUCTION CHANGE.

## 17. FUTURE_CANDIDATE_OBSERVATION

None recorded. No outcome inspection, signal counting, or
hypothesis-ideation was performed on the fresh data at any point.

## 18. Limitations

Binance venue only (Binance ≠ Delta); aggregate resolution; ms
precision; no quotes/L2/funding/OI/liquidations/mark/index in bulk;
Vision ~1-day lag; only 2 down-days regime coverage; D3 era
unknowable without opening (D3 overlap UNKNOWN — the one freshness
factor no sealed-phase audit can clear; a future preregistration
must address it by design, e.g. post-cutoff spans); K-line/ Vision
archive files can be retrospectively updated by provider (CHECKSUMs
re-verified at analysis; updates log monitored); ETH has no
post-08-31 exposure at all (cleaner lineage than BTC); sample counts
are descriptive, never evidence.
