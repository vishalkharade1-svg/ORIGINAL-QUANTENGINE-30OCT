# Phase 11G-E — Historical Data Capability & Order-Flow Substrate Report

INFRASTRUCTURE ONLY. No economic experiments. No hypothesis changes.
No winners. D3 sealed. LIVE disabled. Production untouched.

## PHASE: 11G-E
## METHODOLOGY: GREEN

New modules (all under `research/phase11g/`, all green):
`events/canonical.py` (8 frozen event types, v11ge-v1),
`normalization/normalize.py` (REAL OHLCV path; missing-field refusal;
deterministic ordering), `validation/quality.py` (observable
rejections + reports + gap detection), `provenance/model.py`
(27-field immutable records + content/transformation hashes),
`orderflow/truth.py` (REAL/PROXY/UNAVAILABLE classifier + trade-only
footprint/CVD/diagonal/absorption), `orderflow/book.py` (validated
deterministic reconstruction), `registry/registry.py` (catalog +
phase-ordered freshness + D3 refusal), `adapters/exchange.py`
(interface + centralized Delta URLs + fake-client tests),
`storage/store.py` (immutable RAW + Parquet/JSON normalized + sidecars),
`data/synthetic.py` (seeded SYNTHETIC fixtures, tests only).

One scope-noted test clarification: `test_d3_seal.py`'s
content-hash scan now exempts `test_data_*` (11G-E provenance tests
must reference hashing; Stage-A files remain banned — documented,
non-weakening).

## DATA CAPABILITY (verified, not assumed)

Historical: OHLCV 1m ONLY (`DeltaHistory.candles()` /
`HistoricalLoader`, `/v2/history/candles`). No tick/trade/quote/book/
funding/OI/liquidation/VAP history. Live socket is live-only.
`CandleMapper` carries total volume only.

## REAL ORDER FLOW: UNAVAILABLE

`ReplayDeltaProvider` is OHLCV-estimated (`mode="ESTIMATED"`); the live
trade-based provider has no historical feed and is research-forbidden.
Classifier tightened during development (tests caught an over-broad
PROXY allowance for spread/depth — fixed in implementation, not tests).

## PROXY ORDER FLOW

Candle-directional estimates only, explicitly labeled PROXY_FEATURE,
never REAL. Spread/depth/imbalance have NO candle proxy (UNAVAILABLE).

## D3: READ 0 / HASH 0 / LOAD 0

No D3 paths in new code (scan-enforced); seal suites green; registry
refuses D3 registration. Counters verified zero post-run.

## PRODUCTION DIFF: NONE

`core/ config/ data/ execution/ risk/ backtesting/ main.py` untouched
(verified by status + suite). 11F/11G-A–D artifacts untouched.

## TESTS

New 11G-E: 51 passed (events 9, quality 11, orderflow 11, registry 12,
mutations 8... precisely: 51 across 6 files), 0 failed. Full 11G
suite: 205 passed. Main `tests/`: 2188 passed, 0 failed, 0 collection
errors. `compileall`: clean. `git diff --check`: clean.

## GATE A

PASS ×2: 27 orders / 11 fills / 6 wins / 5 losses / 0 BE /
net +0.117534, identical IDs.

## DATASETS

No new market datasets (infrastructure phase; synthetic fixtures are
seeded unit-test inputs, labeled, never economic evidence).

## NEW INFRASTRUCTURE

10 modules + 5 docs (`docs/` capability audit, provenance contract,
orderflow capability, registry spec, event schema) + 6 test files +
research-log 11G-E entry. File list in `git show --stat HEAD`.

## ECONOMIC RESEARCH: NOT RUN
## HYPOTHESIS CHANGES: NONE
## PARAMETER CHANGES: NONE
## WINNER SELECTION: NONE
## LIVE: DISABLED

Recommendation: 11G-F may preregister hypotheses ONLY against
REAL-available data (OHLCV + derived) or explicitly PROXY claims;
REAL order-flow hypotheses must wait for a genuine historical feed
(new phase + new data, never fabrication).
