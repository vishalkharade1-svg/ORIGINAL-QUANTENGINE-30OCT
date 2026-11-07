# Phase 10 Baseline — 2026-09-05 15:32 UTC

> Verified before any Phase 10 code changes. All counts verified, no fabrication.

## Git

- Commit: `22326a9` (HEAD, 63 commits ahead of origin/main)
- Status: clean except `claude suggetions.md` (untracked, prior audit artifact) and `docs/audit/phase9s_50_symbol_load_real_test2.json` (untracked, soak harness artifact)
- Branch: `main`

## Python / Dependencies

- Python: 3.12.10
- httpx 0.27.2, pandas 2.2.2, websockets 12.0
- requirements.txt: 9 pins (aiohttp, httpx, websockets, orjson, python-dotenv, loguru, pandas, numpy, pyarrow) — unchanged

## Tests

- `python -m compileall -q core` → success, exit 0
- `python -m pytest tests --ignore=_archive --ignore=examples -q` → **1709 passed** (was 1705, now 1709 with `test_portfolio_risk_semantics_9s` + `test_performance_ambiguous_9s`)
- `python -m pytest tests/test_remote_gateway_9pk.py -q` → 28 passed
- `python -m pytest --collect-only -q` → 1568 collected, 24 errors (all `_archive/examples` legacy)

## Existing PAPER Startup Behavior (verified)

- `config/settings.py` defaults: `PAPER_MODE=True`, `LIVE_MODE=False`, `LIVE_EXECUTE=False`, `SYMBOLS=BTCUSDT,ETHUSDT`, `TIMEFRAME=1m`, `UNIVERSE=explicit`
- `main.py` PAPER path: `build_paper_engine()` → `RealTimeEngine` (Phase 6E, multi-symbol, `InstrumentRegistry` + `UniverseManager` + `MarketUniverse` + `LiquidityProvider` + `HistoryProvider` + `PipelineRegistry` + `PaperRuntime` + `BrokerEngine dry_run`) → `run_paper_with_monitoring(engine)` (EngineLifecycle + optional Control API)
- `main.py` prints: `Symbols`, `Mode: PAPER TRADING`, `Runtime: Phase 6E RealTimeEngine`, `Paper-only: dry_run=True`, `Control API: disabled (default)` — verified via `python -m scripts.baseline_9s` (synthetic) and `scripts/baseline_9s_delta_5000.py` (real Delta history)
- `LIVE_EXECUTE` remains disabled, no live orders, fail-closed if `LIVE_MODE` without `DELTA_API_KEY/SECRET` (verified `core/exchanges/delta/delta_rest.py` + `DeltaExchange._require_auth`)

## Existing Monitoring Behavior (verified)

- **Control API** `core/monitoring/api_server.py` + `service.py`: localhost `127.0.0.1:8787` (default), bearer token, allowlist `start/stop/restart/emergency_stop`, PAPER-only (`_assert_paper_capable`), fail-closed without token, read-only otherwise
- **Remote Gateway** `core/remote/gateway.py` + `service.py`: `127.0.0.1:9443` (default), TLS, `VIEW/CONTROL/EMERGENCY` roles, audit logging, rate limiting, `RemoteGateway` + `TrustedDevice` + `DeviceRegistry`
- **Desktop/Remote Monitoring:** `core/monitoring/service.py` + `core/remote/service.py` + `core/client` + PWA — thin, no direct order execution, role/auth/audit enforced

## Existing Real Data Baseline (verified)

- **Synthetic 500-bar:** `docs/audit/baseline_9s.json` — 500 synthetic, 0 trades (post-9Q selective, honest), deterministic
- **Real 5000-bar Delta:** `docs/audit/baseline_9s_delta_5000.json` — BTCUSDT 1m, 2026-09-01 21:31:00 → 2026-09-05 08:50:00, 5000 requested → 5000 received → 5000 usable, 0 duplicates, 0 missing, 0 gaps, 27 orders, 11 fills, 6 wins, 5 losses, 0 breakevens, net 3.80889, Sharpe 0.5969, `verify_gate_a.py` **PASS** (determinism 1e-6)
- **50-symbol soak:** `docs/audit/phase9s_50_symbol_load*.json` — 50 symbols (12 perps + 6 spot + 32 options from 388 Delta products), `DeltaSubscriptionStream` multiplexed, p99 0.23ms, 120s, 1191 loops, no crashes/leaks (subscription layer GREEN)

## Architecture (current, verified)

```
REAL DELTA MARKET DATA (REST / WS wss://public-socket.delta.exchange)
  ↓ timestamp normalization (core/common/timestamp.py, canonical seconds)
  ↓ CandleBuilder (thread-safe RLock, 1m buckets)
  ↓ CandleRouter
  ↓ UniverseManager / MarketUniverse / InstrumentRegistry (eligibility cascade)
  ↓ SymbolPipeline (per-symbol, 20+ engines, MarketState, indicators, structure, liquidity, FVG, order blocks, regime, setup, decision)
  ↓ PortfolioRiskManager / SharedCapital (max_portfolio_risk 0.03 = 3% fraction)
  ↓ PositionSizer / PositionManager
  ↓ PAPER EXECUTION (TradeSimulator dry_run, OrderRegistry, TradeRegistry)
  ↓ Accounting (core/backtesting/accounting.py, canonical)
  ↓ Analytics (PerformanceAnalytics, ambiguous, Sharpe on returns)
  ↓ Monitoring (Control API + Remote Gateway + desktop/PWA)
```

All stages observable and testable per `docs/audit/research_integrity_9r.md` and `market_execution_9s.md`.

## Next

Baseline verified, no code changed. Proceed to Phase 10 hardening: PAPER runtime lifecycle, real UniverseManager integration, multi-symbol isolation, candle integrity, reconciliation invariants, health, recovery, resource management, and real Delta soaks (5/10/25/50 symbols).
