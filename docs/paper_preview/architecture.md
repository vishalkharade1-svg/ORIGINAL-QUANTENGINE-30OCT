# Paper Preview — Architecture

PAPER ONLY. LIVE EXECUTION IS DISABLED. PRODUCTION_READY = FALSE.

## Authority map (all reused except where noted)

| Component | Authoritative module | Reuse |
|---|---|---|
| Public REST candles | `core/exchanges/delta/delta_history.py` + `core/history/candle_mapper.py` | REUSE |
| Polling transport | `data/delta/rest_candle_transport.py` (same subscribe contract) | CREATE minimal |
| Dedupe/reconnect/stale | `data/realtime/*` worker, router, health, policy | REUSE |
| Universe | `core/runtime/paper_main.py` explicit manager | REUSE |
| Engine | `core/runtime/real_time_engine.py` + `paper_runtime.py` + `BrokerEngine` dry-run | REUSE |
| Strategy/risk/sizing | `InstitutionalPipeline` / `RiskEngine` / `PositionSizer` + gates | REUSE |
| Portfolio/accounting | `Account` / `TradeRegistry` / `PerformanceAnalytics` | REUSE |
| API | `core/monitoring/api_server.py` (+4 read routes) | EXTEND |
| Dashboard | `core/monitoring/dashboard.html` (static, polling) | CREATE minimal |
| Evidence | existing registries/journals aggregated read-only | EXTEND (no new system) |

## Data flow

```text
Delta public REST /v2/history/candles (no auth)
  -> RestPollingCandleTransport (CLOSED bars only, ordered, watermarked)
  -> SubscriptionWorker -> CandleRouter (dedupe/order/finality)
  -> RealTimeEngine._on_closed_candle (identity-keyed routing)
  -> PaperRuntime.process_closed_candle -> BrokerEngine dry-run
  -> pipeline (strategy) -> RiskEngine -> sizing -> paper fill
  -> TradeRegistry/Account -> ControlApiServer GET routes
  -> browser dashboard (visualization only)
```

## Why REST polling, not the WS ticker feed

The default WS transport derives candles from ticker marks
(reference prices, not traded OHLCV) and is fail-closed for
strategy use by repository policy. REST history returns
exchange-reported traded candles with timestamps; the transport
emits a bar only after its interval fully elapsed, preserving
the same causal contract (closed-only, ordered, deduplicated).

## Provenance labels

- Market data / candles: OBSERVED (venue REST).
- Fills, P&L, account: PAPER-MODELLED (explicit simulator).
- Evidence rollups: LOCAL (never exchange/live).
- Missing values render UNAVAILABLE, never invented.
