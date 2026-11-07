# Runtime Health & Data Freshness

> Phase 10 health: `HEALTHY` / `DEGRADED` / `FAILED` / `STOPPED`

## Health State

- **HEALTHY:** `lifecycle_state == RUNNING`, `engine_started`, `control_thread_alive`, `polls` increasing, `last_error` None, subscriptions LIVE, last market event < threshold
- **DEGRADED:** stale data, high latency, reconnecting, risk kill, low subscriptions
- **FAILED:** `lifecycle_state == FAILED`, `last_error` set, or invariant failure
- **STOPPED:** `STOPPED` or `PAUSED` (paused is intentionally not healthy for new signals)

Considers: market-data freshness, subscription health, pipeline processing, event-loop responsiveness (p99), reconciliation, risk state, errors, resource pressure.

## Data Freshness (per active symbol)

```
last_market_event (tick timestamp, canonical seconds)
last_closed_candle (CandleBuilder last finished)
data_age = now - last_closed_candle
```

If `data_age > threshold` (e.g., 2× timeframe = 120s for 1m):
- mark symbol `DEGRADED`
- stop new signals for that symbol (do not fabricate candles, do not trade stale data)

## Monitoring

- `EngineLifecycle.health()` → `lifecycle_state`, `engine_started`, `uptime`, `polls`, `control_thread_alive`, `last_error`
- `CandleBuilder` `history`/`series` + `MarketState.timestamp` + `SubscriptionState`
- `PerformanceAnalytics` `ambiguous_trades` etc.
- Control API `GET /health`, `GET /runtimes` for desktop/remote

A dead feed must not appear healthy — verified via `test_realtime.py` staleness and `test_market_hardening_9s.py`.
