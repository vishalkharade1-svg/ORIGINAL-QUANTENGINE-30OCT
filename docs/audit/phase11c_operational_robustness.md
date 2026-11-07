# Phase 11C — Operational Robustness Evidence

Paper/fake-transport/deterministic-replay only. `ALLOW_LIVE=false`,
`LIVE_EXECUTE=false`. Zero real exchange orders. No strategy changes.

Commits: implementation `a92d53f`, tests `6287ea8`, evidence (this doc).

Machine-readable measured results:
`docs/audit/phase11c_operational_robustness.json`.

## 11C-A — Failure-path audit (traced code, not described)

MARKET DATA → NORMALIZATION → MARKET STATE → SYMBOL PIPELINE →
STRATEGY → SIGNAL → RISK → POSITION SIZING → ORDER INTENT →
PAPER EXECUTION → POSITION → TRADE → RECONCILIATION → MONITORING,
plus universe discovery → eligibility → subscription → WS frame →
candle builder → closed candle → pipeline.

| Boundary | Input → Output | Failure modes found (11C) | Behavior after fix |
|---|---|---|---|
| WS frame → `_emit_ticker` | raw JSON → ticker tick | unvalidated `raw["d"][0]`, `float()` raised into pump; ONE bad frame killed ALL symbols | per-message isolation + `frames_received/malformed_frames/unknown_frames/closed_candles/disconnects/pump_restarts` counters; `stats()` |
| tick → `CandleBuilder.update` | (ts, price, vol) → finished candle | no price validation; stale bucket tick moved time BACKWARDS and emitted dup events | finite positive price + finite non-negative volume required; stale ticks ignored + `rejected_ticks/stale_ticks`; `stats()` |
| bulk history → `load_history` | raw bars → series | bare `KeyError` mid-load, partial window, impossible OHLC accepted | indexed typed `ValueError`; impossible OHLC rejected |
| transport → `SubscriptionWorker._on_candle` | candle → router → callback | downstream exception propagated into transport chain | isolated, `callback_errors` + `last_callback_error`, worker stays LIVE |
| worker → `RealTimeEngine._on_closed_candle` | candle → runtime | one symbol's exception starved all runtimes | isolated per symbol, `route_errors` + `last_route_error`; `poll`/`reconcile` also guarded (`reconcile_errors`) |
| contract → `DeltaOrderExecutor._contract` | intent+contract → payload | only product_id + precisions validated; bad tick/step/min-qty reached payload math | tick_size>0, quantity_step>0, min_quantity>=0, finite numbers; `InvalidContractError` before transport |
| transport → `DeltaContractLoader.load` | `/v2/products` → registry | untyped `KeyError`; empty result → silent empty registry; malformed product → untyped crash | `ContractLoadError` for transport/missing/wrong-type/empty/non-dict/missing-symbol failures |
| exchange records → `BrokerEngine._find_position/_sync_equity/_book_live_close` | tolerant `_field` reads | `int(pid)` / `float(size/equity/pnl)` raised out of the live loop; silent fallback substitution | malformed REQUIRED fields degrade safely (no position / no match / modeled P&L / last equity kept) AND count drift |
| provider → `UniverseManager/RefreshScheduler` | discovery+providers → universe | provider raise inside `build_universe` (no local try) | `RefreshScheduler` records + returns None; `AsyncRefreshScheduler` preserves cached universe; ONE worker, coalesced, no lock across I/O |
| legacy `websocket_client.start` | WS frame → market/candle | malformed frame crashed the feed (generic `except: raise`) | per-frame skip + local counters; reconnect policy unchanged |
| registry → `OrderRegistry` | order events → lifecycle | transitions already strict; proven by negative tests | unchanged (mutation-proven) |

## 11C-B — Contract metadata hardening

`InvalidContractError` (before ANY transport call, counting fake
records 0 calls): missing contract; product_id None/non-numeric/zero/
negative; tick_size 0/negative/None/NaN/Inf/bool/string; quantity_step
same; min_quantity negative/None/NaN/string; precisions negative/float/
string/None/bool. Valid contract + armed gate → 1 payload. Valid
contract + no safety → `LiveBlockedError`, 0 calls.

## 11C-C — Contract loader failures

`ContractLoadError` for: timeout, connection failure, HTTP failure,
malformed envelope, missing `result`, `None` envelope, wrong result
type (dict/str/int), EMPTY result (refuses empty registry), non-dict
product, missing symbol, non-string contract_type. Valid products load.

## 11C-D — Schema-drift decision (REQUIRED vs OPTIONAL)

REQUIRED (detectable, degrade loudly + count): position size,
product_id match key, exit price, realized P&L, equity. OPTIONAL
(tolerant fallback correct, but OBSERVED): `{"result":…}` envelope
shape, candidate spellings (`size|quantity`, `product_id|productId`,
`exit_price|close_price|average_exit_price`, `realized_pnl|realised_pnl`,
`total_equity|equity|total_balance`). `get_schema_drift_stats()`,
`drain_schema_drift_stats()`, `schema_health()` → HEALTHY/DEGRADED.

## 11C-E — Exception-swallow audit (108 sites, 41 files, prod code)

- SAFE RECOVERY (isolated + logged/counted): subscription manager (5),
  workers (4), schedulers (3), broker live paths (3), engine routes (3),
  providers, journal observer.
- EXPECTED INPUT/USER (typed fallback): gateway body-parse, safety
  bool coerce, normalizers/mappers, discovery.
- RETRYABLE INFRA (logged + retry/degrade): client poller, lifecycle,
  monitoring/api_server, REST 429/5xx retry.
- FATAL (propagates intentionally): reconnect-budget exhaustion,
  LiveBlockedError, ConfigurationError.
- FIXED IN 11C (were silent/dangerous): pump frame kill-all, worker
  propagation, engine cross-symbol starvation, live-loop numeric
  crashes, builder time-backwards, legacy feed crash, loader untyped
  errors + silent empty registry.
- Accepted LOW: `research/*` offline paths; legacy feed local counters;
  `test_contract_loader.py` module-level network import (flagged).

## 11C-F/G/H/J/K/L/M/N/O/P/V — measured

See JSON artifact for every measured value. Headline figures:

- Chain (11C-I): 5000/5000 routed, 9 intents → 9 fills, balance
  2000 → 2029.491386, reconciliation diff 0, 0 HTTP calls (tripwire).
- Soaks: 10→1200 candles 4/4 fills; 25→3000 9/9; 50→6000 17/17;
  0 route/reconcile errors; dispatch p95 ≤ 0.05ms.
- Event loop: provider 500ms vs poll p95 0.0026ms (n=50), separate.
- Resources: threads 1→1, repeated-soak gc growth 0, peak 13.5MB.
- Restart: clean rebuild verified; persistent trading-state recovery
  NOT IMPLEMENTED (no save/load on runtimes); catalog JSON round-trip 2/2.
- Mutations M1–M6: every guard removal detected by tests; tree restored.
- Gate A: 27/11/6/5/net 3.80889 identical in 2 processes. PASS.
- Suite: 1918 passed, 0 failed/skipped/errors (241s). Bare `pytest`
  collects 1918 deterministically via `pytest.ini`.
- LIVE: disabled, 0 real orders, Phase 11A suite green.
