# Recovery

> Phase 10 recovery: WebSocket disconnect, REST 429/timeout, malformed message, unknown symbol, duplicate/out-of-order.

## Policy

- **Retry:** `ReconnectPolicy` (base 1s, factor 2, max 60s, max_attempts optional), `DeltaREST` with `Retry-After` + exponential backoff, cap 30s
- **No tight loops:** `await asyncio.sleep(delay)` + `market.connected=False` while disconnected
- **Preserve state:** `CandleBuilder` `current`/`history`/`series` under `RLock`, `OrderRegistry`/`TradeRegistry`/`Account` not cleared on reconnect
- **Avoid duplicates:** `CandleBuilder` dedup `bucket == current.timestamp`, `CandleRouter` drops duplicates/out-of-order, `OrderRegistry` dedup by `setup_id`
- **Resume safely:** After `RECOVERY_COMPLETED`, `health()` is re-checked, `reconciliation` passes, no duplicate subscriptions/candles/orders

## Tested

- `tests/test_realtime.py` (32/32): 429, timeout, malformed, unknown symbol, duplicate, out-of-order, reconnect, staleness, failure isolation
- `tests/test_market_hardening_9s.py` (7/7): corrupt bar, WS drop, provider failure, load p99
- `tests/test_delta_rest_9s.py` (4/4): 429 `Retry-After`, 500 retry, 400 immediate
- `scripts/soak_50_symbol.py` (50 symbols, 120s, 1191 loops, p99 0.23ms, no crashes)
