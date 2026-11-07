# Muse Suggestions 1 — Full-Workspace Audit (post-11D, HEAD `1bfa190`)

Date (UTC): 2026-09-07 | Method: 3 parallel audit passes + independent
verification by execution (`python -c` probes) and code reads.
Scope: entire workspace — errors, code quality, mathematics, knowledge/docs,
upgrade/optimization/correction opportunities. No code changed, nothing committed.

## 1. Headline verdict

The prior audit (`muse suggetions.md`, vs commit `3609864`) is now
**substantially resolved**: of its 14 action items, 11 are RESOLVED,
1 PARTIAL, 1 MOSTLY-RESOLVED with 1 remainder each, 1 UPHELD (§2).
Phases 11A–11D implemented nearly everything it asked for.

This pass finds **no live-safety violation and no P&L-magnitude math error
in the certified paths**, but it does find one CRITICAL and three HIGH
defects, all in the same family the previous phases never covered:
**non-finite (NaN/Inf) inputs bypass every risk guard** and flow through
sizing → audit → simulator → ledger, where they are booked as phantom
BREAKEVEN trades. Plus one HIGH sizing-truthfulness defect (the same
`MAX_ALLOCATION_PER_TRADE=500` constant means *margin* in the sizer and
*notional* in the manager — true risk understated up to 10× on the
intent). Details in §3; every CRITICAL/HIGH below was re-verified by
execution in this audit (probe outputs quoted).

Honesty notes (where I disagree with the audit passes):
- Slippage `2.0×` (risk_engine.py:300-304) is **not a bug**: settings
  document round-trip costs, and 2 legs × entry notional is the coherent
  reading. It needs a one-line comment, not a fix (§6, N5).
- Async cold-start "does nothing" is **self-healing on the next poll**,
  and production (`paper_main.py`, `main.py`) doesn't wire the async
  scheduler at all. The real finding is the unwired scheduler (§4, M5).
- `logs/engine.log` is still tracked (11D missed it); `.env`/`.venv`/`*.pyc`
  removal verified effective (§5, H1).

## 2. Prior-audit (`muse suggetions.md` §8) resolution status

| # | Item | Status | Evidence |
|---|---|---|---|
| P0-1 | Reframe `3609864` | SUPERSEDED (Option B taken) | `6f5e608` built the real gate |
| P0-2 | Real `ALLOW_LIVE` invariant | RESOLVED | `live_safety_gate.py`, enforced in executor + `main.py` |
| P0-3 | Honest tests | RESOLVED | `test_live_block_11.py` rewritten (659 lines, counting transport) |
| P1-4 | PAPER+LIVE conflict | RESOLVED (raises `ConfigurationError`) | gate `:167-171`, tests |
| P1-5 | Contract validation | RESOLVED | `InvalidContractError`, 11C-B |
| P1-6 | Drift observability | RESOLVED | `_SCHEMA_DRIFT` ledger, 11C-D |
| P1-7 | Typed loader errors | RESOLVED | `ContractLoadError`, 11C-C |
| P1-8 | `balance<=0` guard | RESOLVED for finite; **NaN still passes (§3, C1)** | `position_sizer.py:59` |
| P1-9 | `pytest.ini` | RESOLVED; `examples/test_market_structure.py:14` still broken but excluded | `pytest.ini`, 1921 collected |
| P1-10 | Untrack junk | RESOLVED except **`logs/engine.log` still tracked (§5, H1)** | `131660f` |
| P1-11 | Deps | RESOLVED except **loguru contradiction (§5, H2)** | `requirements.txt` |
| P2-12 | Gate A + cost sensitivity | RESOLVED | 11B |
| P2-13 | Math recertification | RESOLVED | 67 tests, 11B |
| P2-14 | Boundary discipline | UPHELD | "Phase 12 NOT STARTED" |

## 3. CRITICAL / HIGH — verified by execution

### C1 — CRITICAL — NaN bypasses every risk guard, books phantom BREAKEVEN trades
- `position_sizer.py:59` `if balance <= 0` is `False` for NaN → probe:
  `calculate(balance=nan,…) → valid=True, qty=nan` (verified).
- `position_sizer.py:91+` entry/stop checks catch `<=0`, not NaN/Inf →
  `stop=nan → valid=True, qty=nan`; `entry=inf → valid=True` (verified).
- `position_manager.py` `audit()` keeps `quantity=nan` (reason wrongly says
  "rounded to 8 decimals") (verified); `trade_simulator.py open_trade`
  `if quantity <= 0: return None` is `False` for NaN → `Trade(qty=NaN)`
  created (verified); `classify_pnl(NaN) → BREAKEVEN` (probed) → ledger
  `sum(pnl)` goes NaN while account books nothing — silent split.
- Same hole in `candle_builder.py load_history` (my 11C code): `high=inf`
  and `open=nan` both ACCEPTED (verified) — `update()` rejects them, so
  bulk and streaming paths disagree.
- FIX (one place each, fail-closed): `math.isfinite` guards at sizer entry
  (`balance`, `entry_price`, `stop_price`), `audit()` (`quantity → 0` when
  non-finite), `open_trade` (`if not (quantity > 0): return None`),
  `load_history` (mirror `update()`), `classify_pnl` (raise on non-finite
  instead of BREAKEVEN). Add 6 negative tests; mutation-check them.

### H1 — HIGH — one constant, two units: true risk understated up to 10×
- Sizer (`position_sizer.py:299-309`) caps **margin** at
  `MAX_ALLOCATION_PER_TRADE=500` → position value up to `500×leverage`
  (5000 at lev 10). Manager (`position_manager.py audit` →
  `max_quantity = 500/entry`) caps **notional** at 500. Verified chain on
  BTC 77600/77500, balance 2000: sizer `qty=0.0644, PV=5000,
  risk_amount=6.44` → manager clamps to `qty=0.00644, PV=500`, true risk
  0.64 — while the intent still carries `risk_percent=0.01` (implies 20.0)
  and stale `risk_amount=6.44` (`risk_engine.py:318` copies pre-cap
  `position.risk_percent`; `actual_risk_percent` never propagated).
- FIX: single unit for the constant (recommend notional everywhere),
  recompute `risk_amount = qty×stop_distance` after the manager cap, and
  propagate `actual_risk_percent` onto the intent.

### H2 — HIGH — production never uses the non-blocking refresh
- `AsyncRefreshScheduler` (the Phase-10 p99 fix, 11C-K evidence) is
  referenced only by `realtime_engine.py` duck-typing + tests. `paper_main.py`
  and `main.py` wire the synchronous `RefreshScheduler` (verified by grep),
  so the production poll loop still blocks on provider I/O every 60 s —
  the exact stall 11C-K measured the *wrapper* as fixing.
- FIX: wire `AsyncRefreshScheduler` in `build_paper_engine()` (first refresh
  synchronous to avoid cold-start emptiness), or document why blocking is
  acceptable. Related: async cold `start()` reconciles nothing until the
  next `poll` (self-healing one-tick delay — document it; do not "fix" by
  blocking startup without a timeout).

### H3 — HIGH — live equity frozen while in position (live-only scope)
- `broker_engine.py _sync_live`: `_sync_equity()` is called only on the
  flat path; while a position is open the account sits on last-synced
  equity with no unrealized tracking (verified by read). Paper path
  unaffected. Portfolio-level decisions made mid-position use stale equity.
- FIX: call `_sync_equity` unconditionally + track unrealized (or document
  "flat-synced equity" as the design).

## 4. MEDIUM — verified or code-read, worth fixing

- **M1 — RSI reports 100 in a dead-flat market** (`rsi.py`: `avg_loss==0 →
  100` with no `avg_gain==0` check; verified by read). Convention is 50
  (0/0 undefined). One-line fix + test.
- **M2 — Sortino ≠ textbook** (`performance.py`: `std(min(0,r) incl. zeros,
  ddof=1, mean-centered)` vs `sqrt(mean(min(0,r)²))`; ~+17% on probe
  `[.02,-.01,.03,-.02]` → 1.044 vs 0.894). 11B docs disclose "incl zeros"
  but not mean-centering/ddof. Either switch to textbook or quote the
  exact formula in `phase11b_quant_math.md`. (Sharpe/PF/expectancy/win-rate/
  drawdown/accounting signs all re-verified CORRECT; Sharpe is honestly
  labeled trade-based, not annualized.)
- **M3 — `_live_trade` has no identity** (`broker_engine.py:506-518`:
  `Trade(…)` without `symbol/setup_id/order_id/canonical_id`; `Trade`
  defaults `symbol=""`). Breaks ledger slicing and the realtime release
  path (`_reservation_by_symbol` keyed by symbol). Pass the order's identity
  through (verified by 11C-era read of the constructor call).
- **M4 — Reservation lifecycle leaks** (`realtime_engine.py _reconcile`
  retires runtimes without releasing `portfolio_state` reservations;
  single-slot `_reservation_by_symbol` never cancelled on dust-drop).
  Release-on-retire + key by `order_id`, cancel on failed open.
- **M5 — `entry<=0` auto-fills** (`backtester.py _candle_touches_entry`:
  `if entry <= 0: return True`, verified) chained with
  `_next_bar_open_price` returning `0.0` when a candle carries neither
  open nor close (verified): malformed/synthetic feeds fill at price 0.
  Real feeds always carry OHLC (EDGE), but fail-closed (`return False`)
  costs nothing. Same for dry-run dust path (`broker_engine.py:525-539`:
  `placed.append` before `open_trade` returns `None`; dangling `_live_trade`).
- **M6 — Cost inputs frozen pre-cap** (`risk_engine.py:294-304` uses
  pre-`audit` `position_value`; capped notionals overstate modeled costs).
  Recompute after `audit`, or compute inside the simulator from the final
  quantity.
- **M7 — Import-time network still gates collection**: 6 files execute I/O
  at import (`test_delta_products.py`, `test_delta_mapper.py`,
  `test_delta_history.py`, `test_history_storage.py`,
  `test_history_database.py`, `test_replay_feed.py` — verified by read;
  one live import printed `Products : 303`). The 1921 count is not
  reproducible offline. Apply the 11D pattern (stub at import, live demo
  under `__main__ + QE_LIVE_SMOKE=1`) to all six.
- **M8 — 41 `tests/test_*.py` files collect 0 tests** (verified by scan;
  full list in probe output — print-driven demos shadowing real suites,
  e.g. `test_position_sizer.py` vs `test_position_sizing_9q.py`).
  Move demos to `scripts/`/`examples/` or convert; enforce "≥1 test per
  `tests/test_*.py`" in CI.
- **M9 — Thread-safety debt** (static reads, no race demonstrated):
  `DeltaSubscriptionStream` dict/close races, `RefreshScheduler` fields
  mutated on worker thread, worker `state.*` vs control-thread reads,
  `event_bus.dispatch` iterating a live callback list,
  `TradeRegistry.all()` returns the live list (verified identity —
  external `.clear()` wipes the ledger), lock-free `Account`.
  Cheapest high-value fixes: `return list(…)` in `all()`, iterate
  `list(callbacks)` in `dispatch`, `RLock` on stream/scheduler/worker.
- **M10 — RUNBOOK omits the 11A safety model** (verified: no `ALLOW_LIVE`,
  `EXECUTION_MODE`, banner, conflict/unknown-mode errors; "no live trading
  path" over-reassures vs the gated-but-real `main.py` LIVE branch; control
  verbs 4 vs code allowlist 6). Add §2.5 + cost-model warning (zero-cost
  defaults flatter every PAPER PnL; 11B proved −18…−84 at modeled costs).
- **M11 — Stale decision docs**: `phase10/known_limitations.md` (Gate A
  5W→6W/5L, dummy-universe, "NOT YET RUN" soaks, "Phase 11 not started"),
  `phase10/baseline.md`/`architecture.md` (HEAD 22326a9/4515c96, 9 pins,
  388 products vs ~402 live), `project_status.md` ("Phase 11A", ₹12000/₹1500
  vs code 2000/500), one-line `README.md`, `STATUS.md` ending at 9R/9S,
  `import_manifest.md` missing `live_safety_gate.py`. Banner them as
  point-in-time or refresh the deltas; minimum viable: README quickstart +
  docs map.
- **M12 — `.env.example` ships 4 inert variables** (`RISK_PER_TRADE`,
  `MAX_OPEN_TRADES`, `HISTORICAL_CANDLES`, `LOG_LEVEL` — verified zero code
  readers; `RISK_PER_TRADE=1.0` is 100× the real 0.01). Delete or wire via
  `settings.py` helpers.

## 5. LOW / nits (static reads; batch when touching the files)

- **H1 (11D remainder): `logs/engine.log` still tracked** (verified
  `git ls-files`). `git rm --cached logs/engine.log`, keep working copy.
- **H2 (loguru contradiction)**: `requirements.txt` justifies loguru as
  "logging" while `logging_config.py:20-24` says it isn't a dependency;
  verified sole importer is the unimported `core/logger.py`. Drop loguru +
  quarantine `core/logger.py`, or unify logging and fix the docstring.
- Expiry off-by-one smell: bar-anchored `bar >= expires_at` vs legacy
  `wait_bars > max` (`order_registry.py:299/319`) — eligible window is
  `max+1` bars. Pick one semantic, document, test both.
- `CandleBuilder` gaps collapse silently (t→t+300 emits 1 candle, verified),
  `load_history` unsorted/unbucketed/un-normalized, `normalize_timestamp(True)==1`
  + float-ns precision loss (`timestamp.py`), `historical_loader.py:187`
  `remaining -= batch_size` under-fetches sparse history, `settings.py:97-100`
  raw `int()/float()` vs `_env_*` helpers, `SYMBOLS[0]` `IndexError` on empty
  config (`warmup.py:34`, `websocket_client.py:73`), router `<` vs `<=`
  post-eviction redelivery, manager heal double-listing, `risk_multiplier<0`
  silent clamp (verified: −5 → 0.001 valid), `leverage<=0→1.0` silent,
  `position_size.py:91` `risk_reward = PV/EL` (~776× on BTC — wrong formula,
  verified zero consumers: dormant trap, fix or delete before anyone wires
  `MIN_RISK_REWARD` to it), dead helpers (`all_trades`, `schema_health`,
  `print_last`, `manage_into/unrealized` — verified zero callers),
  `scripts/soak_50_symbol.py:287` lone TODO.
- 11C report wart: `phase11c_operational_robustness` known-wart section
  predates the 11D fixes it flags (contract-loader import I/O, tracked
  `.env`/`.venv`) — annotate resolved-by-11D; 11D report file count 742→744
  (its own commit).

## 6. Optimizations (measured or reasoned; no behavior change)

1. **`SMA.update()` is full recompute** — add rolling-sum incremental like
   EMA/RSI/ATR/ADX already have (verified pattern exists in siblings).
2. **Wire the async scheduler into production** (§3 H2) — the measured
   11C-K numbers (poll p95 0.0026 ms vs 500 ms provider) only apply where
   it is wired; today that is nowhere in prod.
3. **Cheapest concurrency wins**: `list()` copies in `TradeRegistry.all()`
   + `event_bus.dispatch`, one `RLock` each on stream/scheduler/worker —
   removes 80% of the M9 surface with ~10 lines.
4. **Collection speed**: M7+M8 fixes remove network waits and 41 dead
   imports from every bare run (37 s → materially lower, plus offline-safe).
5. **Soak cost**: 50-symbol soak is 0.22 s — cheap enough to run the
   *real-pipeline* (not scripted-world) soak at 10 symbols as a nightly
   fidelity check alongside the fast one.

## 7. Suggested actions (prioritized)

- **P0 (before any strategy/live work):** C1 NaN guards (sizer, audit,
  open_trade, load_history, classify) + negative tests; H1 single-unit cap
  + intent risk truthfulness; re-run Gate A + full suite after.
- **P1 (correctness/hygiene):** H2 wire async scheduler (or document
  blocking); H3 flat-vs-open equity policy; M1 RSI-50; M2 Sortino formula
  doc-or-fix; M3/M4 identity + reservation lifecycle; M5 fail-closed fills;
  M6 post-cap costs; M7 import-time I/O ×6; M8 dead-test triage; M9 lock
  micro-fixes; `logs/engine.log` untrack; loguru decision; M10–M12 doc fixes.
- **P2 (knowledge):** §5 batch; README quickstart + docs map; annotate
  superseded 11C/11D report lines; economic-dedup + validation re-check
  already covered by 11B — no action.

*End of audit. Strongest single sentence: add `math.isfinite` to the five
listed boundaries and the phantom-BREAKEVEN family disappears; unify the
allocation-cap unit and the intent tells the truth about risk.*
