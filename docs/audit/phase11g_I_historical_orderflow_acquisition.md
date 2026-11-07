# Phase 11G-I — Historical REAL Order-Flow Acquisition & Certification

DATA/INFRASTRUCTURE ONLY. No strategies, no winners, no economics.
D3 sealed. LIVE disabled. Production untouched.

## 1. Starting HEAD

`3d72434750dd9b414665f16e7664052ac29aecc7` (11G-H readiness),
branch `main`, tree clean (muse notes pre-existing). Chain verified.

## 2. Provider Research

Delta: candles-only history (probed 11G-H); recent-trades count-capped
(50, window params ignored — proven); L2 live snapshot only; order/
fills history is user-authenticated own-data (rejected: auth + not
market-wide). Coinbase: candles-only public; tick data paid (rejected:
no paid commitments). Bybit: no official bulk path (third-party
scrapers rejected). OKX: download pages login-ambiguous (rejected as
primary; fallback). Tardis/cryptostruct: paid (rejected).
**Binance Vision: FREE public UM aggTrades with `is_buyer_maker`
aggressor side + CHECKSUM per zip + klines + funding/mark histories
— SELECTED.** Matrix: `research/phase11g_i/provider_matrix.md`.

## 3. Provider Capability Matrix

See provider_matrix.md (9 rows: Delta×4, Binance×2, OKX/Bybit/
Coinbase/Tardis rejections with reasons). Venue note recorded:
Binance UM ≠ Delta matching engine; feature mechanics venue-agnostic,
future economics must account for basis.

## 4. Sources Investigated / 5. Rejected

§2 table. Rejected: Delta trades/book history (recent/live only),
Coinbase tick (paid), Bybit bulk (no official path), OKX bulk
(access unclear), Tardis (paid), Delta user fills (auth + own-data).

## 6. Dataset Acquired

`binance_um_aggtrades_BTCUSDT_2026-09-05` + same-day 1m klines.
410,536 agg rows (buy 210,247 / sell 200,288 per `is_buyer_maker`
mapping True→sell); 1440 kline minutes. Acquisition: committed
`fetch_binance.py` (read-only GET, CHECKSUM-verified before store).

## 7. Exact Source

`https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/`
(+ `klines/BTCUSDT/1m/`), retrieved 2026-09-08T17:58Z, 5,133,394 +
56,850 bytes, 2.1s fetch.

## 8. Retrieval Timestamp

2026-09-08T17:58:29Z (in `acquisition_manifest.json`).

## 9. Time Range

2026-09-05 00:00:00.003 → 23:59:59.413 UTC (event-ms).

## 10. Instrument

BTCUSDT USD-M perpetual (Binance venue).

## 11. Record Count

410,535 accepted / 0 rejected (1 header row excluded from 410,536 lines).

## 12. Hashes

Raw zip sha256 `6e7c50c4…` (== provider CHECKSUM), klines `af5938c8…`;
normalized content sha `440c9191…` (deterministic repeat verified);
transformation hash recorded; manifest in `certified/`.

## 13. Provenance

27-field record (`certified/provenance.json`): source/provider/
exchange/UTC/event-ms/tick/microsecond-origin/duplicate-reject/
gap-enumerate/schema 11ge-v1/content+raw+transformation hashes/
REAL/fresh-acquired/unused/no-restrictions/FRESH.

## 14. Validation Results

Quality engine: 410,535 total, 410,535 accepted, 0 rejected, 0
duplicates, 0 out-of-order, full-day span. Kline cross-check:
1440/1440 minutes, high/low match except 2 sub-tick ($0.10 on ~$80k)
kline-rounding residuals; volume rel diff 0.034% (late prints).
Quality report + registry snapshot committed.

## 15. REAL/PROXY/UNAVAILABLE

Trades+aggressor: REAL. Footprint/delta/CVD from them: REAL.
Candle estimates: PROXY (unchanged). Spread/depth/book history:
UNAVAILABLE (classifier tightened after tests caught laxity).

## 16. Causality Evidence

Footprint windows exclude out-of-window trades (in-window moves,
post-close excluded — tested both directions); prefix/bisect
invariance; book future-update isolation; ATR prefix-stability.

## 17. Mutation Evidence

MUT-1 (in-window moves/out-window excluded), MUT-4 (dup ID),
MUT-5 (crossed book refused + unapplied), MUT-6 (negative qty),
MUT-7 (tamper→hash change), MUT-9 (PROXY≠REAL); cost/dataset/rolling
mutations detected; tree clean.

## 18. Reproducibility

Normalize-twice → identical hash (`440c9191…`); acquisition
re-download → identical bytes/shas. Provider files immutable (Binance
static archive; limitation recorded if they ever mutate).

## 19. D3 Status

READ 0 / HASH 0 / LOAD 0. Seal suites green; registry refuses D3;
no D3 markers in new artifacts (scan-enforced).

## 20. Production Diff

NONE. Scope: `research/phase11g_i/` + this report (+ 11G log entry).
`core/ config/ data/ execution/ risk/ backtesting/ main.py` untouched.
ALLOW_LIVE/LIVE_EXECUTE false; write-scan clean; 0 exchange writes
(one new outbound surface: public read-only GET for the documented
fetch; no auth, no keys, secret-scan clean).

## 21. Test Results

New 17 passed (no-network enforced by scanner test). Full 11G
research suites: 281 passed (205+40+19+17). Main `tests/`: 2188
passed, 0 failed, 0 collection errors. `compileall`: clean.
`git diff --check`: clean.

## 22. Gate A Results

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 23. Limitations

One day / one symbol (INSUFFICIENT_FOR_RESEARCH_SCALE — authenticity
≠ sufficiency); Binance≠Delta venue (basis caveat for future
economics); no historical book/quotes (book validated on synthetic
only); mark/OI/funding history REST paths unverified; provider files
assumed immutable; µs→ms truncation documented.

## 24. Final Verdict

**REAL_ORDERFLOW_DATA_CERTIFIED** — all 12 §25 gates pass:
legitimate-day REAL trades acquired; provenance defensible; raw
hash-protected (provider CHECKSUM match); normalization deterministic;
validation passes; causality passes; lineage defensible (fresh-
acquired, unused); registry classifies correctly; D3 sealed;
production untouched; Gate A unchanged; tests pass.
TRADING EDGE: NOT EVALUATED (no strategies run — next phase territory).
