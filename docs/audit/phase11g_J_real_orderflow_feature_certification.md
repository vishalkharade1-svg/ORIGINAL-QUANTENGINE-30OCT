# Phase 11G-J — REAL Order-Flow Replay & Feature Certification

DATA / REPLAY / FEATURE-CERTIFICATION ONLY. No strategies, no economics,
no winners. D3 sealed. LIVE disabled. Production untouched.

## 1. Starting HEAD

`bbd1046a26eecff2fbaa2da93e82ade9befe3e65` (11G-I acquisition),
branch `main`, tree clean (muse notes pre-existing). Chain verified.

## 2. Input Dataset

`binance_um_aggtrades_BTCUSDT_2026-09-05`: 410,535 aggTrades,
2026-09-05 00:00:00.003 → 23:59:59.413 UTC, raw sha `6e7c50c4…`
(provider CHECKSUM match), normalized sha `440c9191…` (deterministic
repeat verified). Quality: 410,535 accepted / 0 rejected, no dups,
no disorder; kline cross-check 1440/1440 min (2 sub-tick rounding
residuals, vol rel diff 0.034%).

## 3. Provider Semantics

Binance UM aggTrade = one or MORE executions at one price/side/moment
(40% of rows aggregate multiple fills via first/last_trade_id) —
documented limitation: NOT individual-fill resolution. `is_buyer_maker`
mapping (True→sell aggressor, False→buy) frozen with dedicated test;
changing it requires documentary evidence + test (none presented).

## 4. aggTrade Semantic Interpretation

Aggregate event with (price, quantity, side, ms timestamp, ID range).
Fine for volume/delta/footprint aggregates; unsuitable for
per-fill microstructure claims. Stated, not hidden.

## 5. Timestamp Handling

CORRECTED during development (audited, not assumed): transact_time is
MILLISECOND precision throughout (13 digits; an early µs assumption
was refuted by digit-length census). 219,213 distinct ms; 191,322
same-ms collisions (46.6%); max 141/ms; mean 1.87/ms. Ordering key =
(event_ms, source_index) — intra-ms order from source rows only, never
synthesized. Canonical ms retained for 11G compatibility.

## 6. Ordering

Deterministic total order (ms, source_index); replay ingests sorted;
prefix operations preserve it. Out-of-order input is re-sorted, never
rejected (documented normalization choice); malformed time fails loud.

## 7. Canonical Event Mapping

`RealTrade` superset (ms, raw, index, symbol, venue, price, quantity,
side, IDs, provenance REAL, feature v1) converting losslessly to 11G
`TradeEvent`. No invented sequences/IDs; µs-scale precision correctly
absent (not faked).

## 8. Feature Inventory

`TradeReplay`: delta (prefix/1s/5s/15s/30s/1m/5m), CVD (+ one-pass
twin, proven equal), footprint ($0.01 buckets, REAL traded levels),
trade imbalance (never "book imbalance"), trade-based absorption
(frozen high-volume + limited-progress form, labeled indicator not
proof), trade-aggression events (per-side trailing-med, never
"liquidity sweep"). Versions pinned (`real-trade-features-v1`).

## 9. REAL/DERIVED/PROXY/UNAVAILABLE

REAL: price/quantity/timestamp/side. DERIVED_FROM_REAL: delta, CVD,
volumes, footprint, imbalance, absorption/aggression indicators.
PROXY: none introduced. UNAVAILABLE: spread, depth, queue, resting
liquidity, L2 depletion, quote changes (order-flow truth model
unchanged; book work stays synthetic-tested).

## 10. Delta

Prefix + 6 fixed windows; buy/sell/total/delta/delta-pct reported.
Golden hand-computed values match (3.5/4.5/−1.0/8.0).

## 11. CVD

Causal prefix accumulation; 410,535 points, final +1066.87 BTC (net
buy-aggressor day). One-pass twin identical.

## 12. Footprint

Deterministic $0.01 levels from REAL trades only; golden levels match;
empty buckets return empty (never fabricated).

## 13. Trade Imbalance

(buy−sell)/total on aggressor volumes; name-guarded against
"book imbalance" by test.

## 14. Trade-Based Absorption

Frozen form; labeled indicator-with-evidence, explicitly not
resting-order proof. Last-1m sample: not present (reported, not tuned).

## 15. Trade-Aggression Event Detection

Per-side trailing-median bursts; directional without liquidity claims;
"liquidity sweep" string banned by test.

## 16. Causality Evidence

Prefix-append/forecast-mutation/deletion invariance green;
historical-mutation sensitivity proven (test actually detects);
footprint window isolation green.

## 17. Mutation Evidence

MUT-1…10 all detected (future-state divergence, quantity/side
sensitivity, dup/order/quantity validation, tamper→hash change,
PROXY≠REAL guard, window sensitivity, implementation twin +
hash stability). Tree clean of mutants.

## 18. Deterministic Replay

Load → 410,535 events; CVD identical across runs; state hash stable;
normalization twice → `440c9191…`. No uncontrolled randomness
(scanned), no network in tests (scanned).

## 19. Quality Results

11G-I quality re-verified through the J pipeline (0 rejections);
golden fixtures clean; malformed/duplicates/gaps all detected with
reasons; gap semantics (absence ≠ gap) tested.

## 20. Performance

Load 410,535 events 26.4s (~15.5k/s); CVD 1.4s; feature set 4.0s;
peak 348 MB. Correctness-first; no optimization applied.

## 21. D3

READ 0 / HASH 0 / LOAD 0. No D3 paths in new modules (scan); seal
suites green; registry refuses D3.

## 22. Production Diff

NONE. Scope: `research/phase11g_j/` (replay/, tests/, research_log)
+ this report. `core/ config/ data/ execution/ risk/ backtesting/
main.py` untouched. 11F/11G-A–I artifacts untouched. ALLOW_LIVE/
LIVE_EXECUTE false; write-scan clean; 0 exchange writes.

## 23. Production Diff (tests)

Main `tests/`: 2188 passed, 0 failed. Research suites: 324 passed
(11G 205 + 11G-F 40 + 11G-G 19 + 11G-I 17 + 11G-J 43), 0 failed.
New 43 green. `compileall`: clean. `git diff --check`: clean.

## 24. Gate A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 25. Limitations

One day/one venue (Binance ≠ Delta basis caveat for future
economics); no historical book/quotes (book validated synthetic-only);
aggregate (not fill) resolution; ms precision; no funding/OI history
paths verified; 348 MB replay footprint.

## 26. Final Verdict

**REAL_ORDERFLOW_FEATURES_CERTIFIED** — all §32 gates pass (canonical
REAL events, aggressor semantics, deterministic ordering +
normalization, causal features, validated delta/CVD/footprint,
accurate classification, mutation protection, reproducible replay,
provenance intact, D3 sealed, production untouched, Gate A unchanged,
tests pass). TRADING EDGE: NOT EVALUATED (no strategies run).
