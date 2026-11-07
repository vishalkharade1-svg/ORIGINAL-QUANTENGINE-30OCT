# Reconciliation Invariants (I1-I8) + Recovery

> Every invariant is checked periodically; failure → FAIL CLOSED, LOG, CORRELATION ID, SNAPSHOT, DO NOT CONTINUE.

## Invariants

- **I1** No duplicate order IDs — `OrderRegistry` keyed by `order_id` + `setup_id`, `create` returns existing, `test_execution_9q` duplicate
- **I2** No duplicate trade IDs — `TradeRegistry` + `OrderRegistry.mark_filled` mints `TRADE-1` once
- **I3** Filled order has valid execution — `mark_filled` consumes once, `status==FILLED` has `trade_id`
- **I4** Closed trade accounted exactly once — `Backtester._book_closed_trades` delta slice, `tests/test_backtester_hardening.py`
- **I5** Reservations reconcile — `SharedCapital` `available = max(0, deployment - reserved)`, `reserved = sum(reservations)`
- **I6** Portfolio equity reconciles — `PerformanceAnalytics` `final_equity = starting + net_profit`, `Account` `balance`
- **I7** Open positions reconcile — `PositionManager` single-position, `TradeSimulator.current_trade` vs `TradeRegistry` `OPEN`
- **I8** Risk limits satisfied — `PortfolioRiskManager` gates, `SharedCapital` `can_reserve`

## Recovery

- **WebSocket disconnect:** `ReconnectPolicy` exponential backoff (base 1s, factor 2, max 60s), `Retry-After` respected, `DeltaREST` 429 backoff, `SubscriptionWorker` reconnects, `MultiSymbolSubscriptionManager` `sync` idempotent
- **REST 429/timeout:** `DeltaREST` `max_retries=3`, `backoff_base=1s`, `Retry-After` header, cap 30s
- **Malformed/unknown symbol/duplicate/out-of-order:** `CandleBuilder` `normalize_timestamp` + `RLock`, `CandleRouter` drops duplicates/out-of-order, `tests/test_realtime.py`
- **After recovery:** validate state — `health()` is `HEALTHY`/`DEGRADED` correctly, `reconciliation` passes, no duplicate subscriptions/candles/orders
