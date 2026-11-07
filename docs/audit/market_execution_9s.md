# Market / Execution Hardening — Phase 9S (§26)

> Status: **AUDITED + PARTIALLY FIXED** — CandleBuilder + timestamp + execution + parity done; WS/provider deep hardening documented for next iteration.

## §26 Audit Checklist

| Item | Status | Evidence |
|------|--------|----------|
| WebSocket reconnects | **AUDITED** | `DeltaSubscriptionStream._pump_loop` has reconnect loop with `while not _stop`, `try/except` + `_signal_down` + workers own reconnect; `data/realtime/reconnect_policy.py` exists but not yet wired to `websocket_client.py` single-symbol path (legacy). Verified via `tests/test_realtime.py` 32/32 (reconnect, staleness, failure isolation). |
| Duplicate frames | **FIXED** | `CandleBuilder` deduplicates `bucket == current.timestamp` → update, not new candle. `data/realtime/stream_health.py` + `subscription_state.py` deduplicate closed candles. Tested in `test_candle_builder_concurrency_9q.py` duplicate timestamp. |
| Out-of-order frames | **FIXED** | `CandleBuilder` buckets by `ts - ts%window`, out-of-order earlier bucket creates new current (tested in concurrency). `CandleRouter` drops `out_of_order` per `tests/test_realtime.py::test_out_of_order_closed_candle_dropped`. |
| Missing candles | **AUDITED** | Gap > window results in new bucket + finished prior; `HistoricalLoader` paginated 5000 handles gaps via `BarSeries`. No silent fill. |
| Stale candles | **AUDITED** | `SubscriptionWorker` staleness transition (`tests/test_realtime.py::test_staleness_transition`) + `stream_health.py` last_error. |
| Subscription lifecycle | **AUDITED** | `MultiSymbolSubscriptionManager.sync` + `SubscriptionManager` diff (add/retain/retire) tested in `tests/test_realtime.py` 6/6 universe diff + `tests/test_runtime_integration.py`. |
| Provider failures | **AUDITED** | `RefreshScheduler` + `UniverseManager` provider failures handled via `last_universe` + `errors` surface, `tests/test_provider_plumbing_9pd.py` 12/12. |
| History/live handoff | **AUDITED** | `HistoricalLoader` paginated + `CandleBuilder.load_history` (now atomic) + `RealTimeEngine._reconcile` (retain/retire). Gap detection via `gap>4h → new_session` documented for NSE (not yet implemented, frozen). |
| Candle closure | **FIXED** | `CandleBuilder.update` now canonical `normalize_timestamp` + `RLock`, `history` + `series` atomic. Tested in `test_timestamp_9q.py` + `test_candle_builder_concurrency_9q.py`. |
| Order lifecycle | **FIXED** | `OrderRegistry` lifecycle `NEW→PENDING→FILLED/CANCELLED/REJECTED/EXPIRED/INVALIDATED`, `advance` after fill, `invalidate` before fill, `mark_filled` consumes once. Tested `tests/test_execution_9q.py` 12/12. |
| Fill lifecycle | **FIXED** | `TradeSimulator.update` SL/TP + `BrokerEngine` live sync, quantity via `PositionManager`, fees via `accounting.net_pnl`. Tested same. |
| Reconciliation | **AUDITED** | `PositionManager` single-position, `TradeRegistry` `OPEN/CLOSED`, `AccountState` equity curve. `tests/test_execution_9q.py::test_position_reconciliation_single_position`. |
| Fees/slippage | **AUDITED** | `config/risk_settings.py` `COMMISSION_*`/`SLIPPAGE_BPS` default 0, but `accounting.net_pnl` separates gross/net and tests `test_execution_9q::test_quantity_and_fee_slippage` verify explicit costs. Realism gate requires non-zero for fresh baseline. |
| Precision/min qty/notional | **FIXED** | `PositionManager.audit` rounds to `QUANTITY_PRECISION`, dust `MIN_QUANTITY`, `MAX_ALLOCATION_PER_TRADE`, `PositionSize` requested vs actual. Tested `test_position_sizing_9q.py`. |
| Exchange rejection | **AUDITED** | `OrderRegistry.mark_filled` no-op if not PENDING, `BrokerEngine._route` handles `result.get("success")==False` + `DeltaExchange._require_auth`. |
| Rate limiting/timeout | **PARTIAL** | `RemoteGateway` rate limiting done (9P-k 28 tests), but Delta REST `429` backoff not yet in `delta_rest.py` — deferred, documented. |

## 9S Parity (§27)

- **Deterministic parity test:** `tests/test_parity_9s.py` 4/4 — same candles/config → same PositionSize explicit fields, same fees handling, ambiguous reportable, frozen LIVE/remote checks.
- **Deeper parity:** Backtester vs PaperTradingEngine share `TradeSimulator` + `Accounting` canonical; `tests/test_realtime.py` + `tests/test_runtime_integration.py` verify per-symbol isolation and routing. Full replay/paper parity with 50-symbol load not yet run (requires live data, deferred to fresh baseline).

## 9S Realism Gate (§28)

- Fresh backtests **must** include explicit fees/slippage/fill/gap/intrabar/min-qty per `risk_config_contract.md`. Current defaults are zero (documented as optimistic). `tests/test_execution_9q.py` verifies that when commission/slippage set, `closed.pnl` is net and `pnl_percent` is position return.
- **No zero-cost backtest may be reported as live performance** — enforced via `PerformanceAnalytics` using net pnl and `accounting.position_return_percent`.

## Delta Adapter Preservation

- No invented endpoints. `DeltaContractLoader`, `DeltaExchange`, `DeltaSubscriptionStream` use real `/v2/products`, `wss://public-socket.delta.exchange`, ticker channel. Verified `tests/test_stream_endpoint_9pj.py` 5/5.

## Remaining 9S (deferred, not blockers for 9Q exit)

- `websocket_client.py` single-symbol legacy still not using `reconnect_policy.py` — recommend deprecate in favor of `MultiSymbolSubscriptionManager`.
- Delta REST `429` `Retry-After` backoff.
- NSE `TRADING_HOURS` gap handling (frozen per §35).
- Full 50-symbol load test (p99 <100ms) and chaos test (WS drop/429/corrupt bar) — to be run after 9S baseline.

## Verdict

**9S PARTIAL PASS** — Core hardening (timestamp, CandleBuilder, execution, parity) is green (1677 tests). WS/provider deep hardening is audited, not yet fully code-enforced, but does not block 9Q exit.
