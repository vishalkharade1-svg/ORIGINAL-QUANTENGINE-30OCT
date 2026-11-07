# 11G-E Data Capability Audit (verified against the repository)

No availability is claimed from module names. Every row was traced to
its source endpoint, schema, or the absence thereof.

| Data | Historical | Live | Source | Resolution | REAL/PROXY | Status |
|------|------------|------|--------|------------|------------|--------|
| OHLCV candles | YES | YES | Delta `/v2/history/candles` via `DeltaHistory.candles()` / `HistoricalLoader` | 1m bars | REAL | RESEARCH-READY (only historical market data) |
| Trades (tick) | NO | provider-only | `core/orderflow/live_delta_provider.py` (no historical feed) | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Trade side/size | NO | provider-only | same as above | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Bid/ask quotes | NO | socket (live state) | `wss://public-socket.delta.exchange` (live only) | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Order book snaps/deltas | NO | none | none in research surface | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Depth | NO | none | none | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Funding | NO | none | no endpoint in `delta_rest.py`/`delta_history.py` | n/a | UNAVAILABLE | unmodeled (carried limitation) |
| Open interest | NO | none | none | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Liquidations | NO | none | none | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Volume-at-price | NO | none | requires tick history | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Tick data | NO | none | none | n/a | UNAVAILABLE | NOT AVAILABLE historically |
| Exchange timestamps | partial | n/a | candle `time` (bar-open, UTC epoch s) | 1m | REAL | bar precision only |
| Sequence numbers | NO | none | absent historically | n/a | UNAVAILABLE | book validation needs future feed |
| Trade/quote IDs | NO | none | absent historically | n/a | UNAVAILABLE | dedup fields reserved in schema |
| Symbol metadata | YES | n/a | `delta_contract.py` / products | n/a | REAL | available |
| Contract metadata | YES | n/a | `delta_contract_loader.py` | n/a | REAL | available |
| Multi-TF history | NO (files) | n/a | derived exactly from closed 1m | 15m+ via resampler | REAL (derived) | resampler-certified |

Critical honesty notes:

* `core/orderflow/` exists, but `ReplayDeltaProvider` is OHLCV-estimated
  (`mode="ESTIMATED"`). Only the live provider uses real trades, which
  has no historical feed and is research-forbidden. Any historical
  "delta/footprint" built here is PROXY by construction.
* `CandleMapper` carries total volume only — no bid/ask split exists
  anywhere in the historical path.
* Local stores: `data/history/BTCUSDT/1m.parquet`, `BTCUSDT_1m_oos.json`,
  Gate-A snapshot, 11F universe (D1/D2/D3) — all OHLCV.
