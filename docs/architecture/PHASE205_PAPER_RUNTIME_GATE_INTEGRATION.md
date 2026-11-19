# Phase 205 — Paper Runtime Market-Data Gate Integration

## Scope

Phase 205 wires the Phase 204 data-quality decision helper into `PaperRuntime.process_closed_candle` as an **opt-in, fail-closed intake gate**. This remains paper-only and makes no exchange API calls.

## Behavior

- Gate is disabled by default (`market_data_max_age_seconds=None`) to preserve the existing runtime path unless an operator explicitly enables it.
- When enabled, the runtime checks the incoming candle before calling `BrokerEngine.run_candle`.
- The gate requires a non-empty candle symbol matching the runtime instrument symbol, a valid Unix-seconds timestamp, a fresh timestamp within the configured maximum age, a closed candle, and valid finite/positive OHLC values with a consistent OHLC range and non-negative volume.
- Rejected candles do not reach the strategy engine. Decisions are retained in `market_data_gate_decisions`; a counter is exposed in `state()`.
- Clock-provider exceptions fail closed with `MARKET_DATA_GATE_ERROR`. Payloads and exception text are not logged.
- The `market_data_now_provider` can be injected for deterministic tests.

## Explicit limits

This is not feed-authenticity verification, exchange-session validation, complete symbol-universe validation, latency measurement, or profitability evidence. The gate is not enabled by default in every deployment; callers must supply `market_data_max_age_seconds` to activate it. It does not change live-execution authorization and does not place, cancel, or modify orders.

## Tests

Phase 205 tests cover fresh acceptance, stale rejection before engine intake, symbol mismatch rejection, forming-candle rejection, inconsistent OHLC rejection, and disabled-mode compatibility. Focused paper runtime boundary, execution lifecycle, order-script safety, and testnet credential-isolation tests were also run.
