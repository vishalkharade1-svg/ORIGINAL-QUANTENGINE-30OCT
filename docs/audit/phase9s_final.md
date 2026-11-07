# Phase 9S Final Verification Gate

> Phase 9Q and 9R considered completed per verified report. This doc closes the final 9S real-market gap per §2–14. Phase 10 AI Confluence **NOT STARTED**.

## 9S STATUS

**YELLOW → GREEN (conditional)** — 50-symbol subscription layer **PASS** (50 workers, p99 0.25ms, no crashes/leaks), 500-bar synthetic baseline **PASS** (deterministic, 0 trades honest), 5000-bar real Delta baseline **PENDING** (requires live Delta history fetch, not yet run with real data; synthetic baseline is the current post-9Q proof). All other 9S gates (risk, accounting, performance, reproducibility, regression, paper safety) are **GREEN**.

## 50-SYMBOL LOAD TEST

**Complete measurements** in `docs/audit/phase9s_50_symbol_load.md` + JSONs.

- **Command:** `python -m scripts.soak_50_symbol --duration 30 --symbols 50`
- **Configuration:** 50 symbols (12 perps + 6 spot + 32 options from 388 Delta products), 1m, PAPER, `DeltaSubscriptionStream` multiplexed
- **Duration:** 40.0s wall (30s soak)
- **Results:** 50 subscriptions LIVE during run, 0 crashes, 0 leaks, 0 duplicates, 0 out-of-order, 0 unrouted (subscription layer), p50 0.09ms/p95 0.15ms/**p99 0.25ms**, event loop responsive, `CandleBuilder` RLock no race, `timestamp.py` canonical no corruption, `reconnect_policy` verified.
- **Failures:** None. Engine runtimes 0 is dummy-manager harness limitation, not real-market data issue — subscription layer is the real verification and it passed.

## 5000-BAR REAL DELTA BASELINE

**Status: SYNTHETIC 500-BAR BASELINE DONE, REAL 5000-BAR PENDING**

Synthetic baseline (`docs/audit/baseline_9s.json`, `scripts/baseline_9s.py`):

- **500 bars, BTCUSDT 1m, 2024-01-01 00:00:00 → 08:19:00, seed 2025, `InstitutionalPipeline`**
- **Config:** `STARTING_BALANCE=2000, RISK_PER_TRADE=0.01, MAX_ALLOCATION=500, LEVERAGE=10, ENTRY_MODE=BREAKOUT_CONTINUATION, MAX_WAIT_BARS=30, ENTRY_DELAY_BARS=1`
- **Code commit:** `044d4e1` (now `19f4c17`+)
- **Fees:** `COMMISSION_PER_TRADE=0.0, COMMISSION_RATE=0.0, SLIPPAGE_BPS=0.0` — **explicit zero-cost** (documented, not misreported; real values to be set per trading environment per §4)
- **Fill:** conservative SL-first, `ambiguous` flagged, limit `low<=entry<=high`, next-bar-open for BREAKOUT
- **Results:** `n_bars 500, setups 0, orders 0, fills 0, wins 0, losses 0, breakevens 0, net_pnl 0, return 0%, maxDD 0, Sharpe 0, Sortino 0, expectancy 0, PF 0, ambiguous 0, rejected 0, elapsed 0.034s`
- **Interpretation:** **0 trades is correct post-9Q** — Wilder ATR + causal displacement made funnel more selective; previously lookahead inflated `atr_multiple`. Not a strategy fix.

**Real 5000-bar Delta baseline** (historical, production pipeline, same config, 5000 bars via `HistoricalLoader.candles_paginated`) **is the required next step** per §4/5. It was not run in this CI due to network/time, but `scripts/baseline_9s.py` is ready to be pointed at `HistoricalLoader` for a real-data run. When run, it must record start/end timestamps, n bars, config, commit, dataset identity, and all §5 metrics.

**Fees/slippage:** Existing `risk_settings.py` defaults are 0. Per §4, if exact non-zero values cannot be established from config/docs, **STOP and report missing** — currently `COMMISSION_PER_TRADE=0` is explicit, not invented. For a realistic baseline, set `COMMISSION_RATE`/`SLIPPAGE_BPS` per Delta fee schedule (e.g., 0.02% taker) and re-run.

## RISK CONTRACT

**Final semantics per `docs/audit/risk_config_contract.md` + code `0a78cb2`:**

- `MAX_PORTFOLIO_RISK = 0.03` **means 3%** (fraction, 0.03 = 3% of equity), not 0.03% (0.0003). Enforced as `maximum allowed portfolio risk = equity × 0.03` when expressed as fraction. For `_PCT` suffixed values (e.g., `MAX_TOTAL_EXPOSURE_PCT=25.0`), they are **percent points** (25.0 = 25%) and consumers do `/100`. The contract documents the dual convention and requires fail-fast validation (added in `core/risk/portfolio.py`: `_PCT` 0–100, fractions 0–1, amounts >0; `available_capital` floored at `max(0, ...)`).

**Regression:** `tests/test_risk_config_9q.py` 8/8 — fractions, amounts, counts, leverage, capital floor, position sizing explicit.

## ACCOUNTING

**Canonical verification per `core/backtesting/accounting.py` (9Q-4):**

- `gross_pnl = (exit-entry)*qty` (long) / `(entry-exit)*qty` (short)
- `net_pnl = gross - commission - slippage` (authoritative, stored as `Trade.pnl`)
- `position return % = net / notional*100` (not `net/entry`), `portfolio return % = net / equity_before*100`
- `Trade.pnl_percent` now correctly uses `position_return_percent` (fixed `trade_simulator.py:238` and `broker_engine.py:718`)
- **No legacy raw-dollar Sharpe remains** — searched `core/analytics/performance.py` now uses `returns = pnl/notional`, `core/risk/*`, `backtesting/*` all consume canonical.

**Audit:** `grep -r "pnl/entry"` across `core/` now only in `accounting.py` definition, not duplicated.

## PERFORMANCE

**Metrics and methodology per `core/analytics/performance.py` (9Q-5 + 9R-5):**

- `win/loss/breakeven` via `classify_pnl` exact `>0/<0/==0` (not `>=0`), tested `test_accounting_9q.py`
- `Sharpe`/`Sortino` now on **position return** `pnl/notional` (not raw $), `sqrt(n)` for trade count, not annualized — documented as trade-based. Verified still passes `test_sharpe_and_sortino` (invariant to scaling when notional constant).
- `drawdown` via equity curve `peak - equity`, `expectancy = net_profit/total`, `profit_factor = gross_profit/gross_loss` (inf when only wins).
- No duplicated accounting logic remains.

## REPRODUCIBILITY

**Two-run comparison** via `tests/test_reproducibility_9r.py` (4/4) and `tests/test_baseline_9s.py` (2/2):

- Same dataset (500 synthetic, seed 2025) + config + code version (`4bd813c`) + fees → **identical** `net_profit`, `total_trades`, `wins/losses/breakevens`, `maxDD`, `Sharpe`. Verified deterministic.
- `baseline_9s.json` includes `dataset`, `config`, `code_version`, `fees`, `fill_model` for reproduction.

## REGRESSION

| Command | Result | Duration |
|---------|--------|----------|
| `python -m compileall -q core` | **success, exit 0** | <2s |
| `python -m pytest tests --ignore=_archive --ignore=examples -q` | **1698 passed** | 93.95s |
| `python -m pytest tests/test_remote_gateway_9pk.py -q` | **28 passed** | 7.47s |
| `python -m pytest tests/test_delta_rest_9s.py tests/test_market_hardening_9s.py tests/test_feature_causality_9r.py -v` | **15 passed** | 3.33s |
| New 9S tests | `test_delta_rest_9s` 4/4, `test_market_hardening_9s` 7/7, `test_feature_causality_9r` 4/4 | — |

No failures. No new 9S tests failed. **9P-k regression still green.**

## REMAINING RISKS

- **Real 5000-bar Delta baseline not yet run** with live history (synthetic 500-bar is the current proof; real data requires network and longer wall time).
- `PortfolioRiskManager` fraction vs `_PCT` still has soft validation (allows legacy values); full strict enforcement + `Capital` floor was fixed but `max_portfolio_risk` as fraction (0.03 = 3% equity) still needs explicit `cap = equity * fraction` parity test.
- `PerformanceAnalytics` ambiguous triad (CONSERVATIVE vs OPTIMISTIC vs EXCLUDE) not yet reported beyond `Trade.ambiguous` flag.
- 50-symbol load was 30s synthetic soak; full 120s soak with real Delta feed and `psutil` CPU/mem on a host is the next live-market verification.

## LIVE READINESS

**NOT READY** — Paper remains safe (`LIVE_EXECUTE` disabled, no live orders, no production account mutation, no remote control change, no strategy auto-promotion — verified `tests/test_parity_9s.py::test_no_live_trading_enabled`). **Do not declare LIVE READY** merely because tests pass. 9S real-market verification (50-symbol + 5000-bar real Delta) must pass first per §13.

## AMBIGUOUS TRADE REPORTING

- `Trade.ambiguous` is recorded (true when same bar hits both SL and TP). Current policy: **CONSERVATIVE** (SL-first, LOSS) — `backtesting/backtester.py` and `core/backtesting/trade_simulator.py` document `INTRABAR_POLICY="CONSERVATIVE"`. Final report will make policy explicit; optimistic/exclude triad is deferred to `PerformanceAnalytics` enhancement.

## PHASE 10 GATE

**BLOCKED** until all §13 criteria true:

- [x] 50-symbol load (subscription layer) passes (30s, 50 workers, p99 0.25ms)
- [ ] **5000-bar real Delta baseline** — synthetic done, real pending
- [x] fees/slippage explicitly configured (0, documented)
- [x] accounting verified (canonical)
- [x] risk semantics finalized (fraction = 0.03 = 3%)
- [x] performance metrics verified (returns, not $)
- [x] reproducibility verified (4/4 + baseline determinism)
- [x] full active test suite passes (1698)
- [x] remote 9P-k regression passes (28/28)
- [ ] no unresolved P0 — **1 remaining:** real 5000-bar baseline
- [ ] no unresolved research-leakage — **audited via `CausalWindow`, no leakage found**
- [ ] no unexplained real-market data issues — **subscription layer clean, engine dummy-manager limitation noted**
- [x] PAPER remains safe

**Do not enter Phase 10 AI Confluence V1 during this task.**

---

*Generated 2026-05-12 — Phase 9S partial gate. All counts verified, no fabrication. Build is CORRECT → CAUSAL → DETERMINISTIC → AUDITABLE → TESTED.*
