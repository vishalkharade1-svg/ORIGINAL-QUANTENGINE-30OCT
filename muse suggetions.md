# Muse Suggestions — Independent Final Audit: Phase 11 claims vs commit 3609864

Date (UTC): 2026-09-06 | HEAD: `3609864` | Branch: `main` (79 commits ahead of `origin/main`)
Scope: entire workspace — architecture, logic, mathematics, code, errors, refinements.
Method: static reads + executed checks (`git show`, `pytest tests/test_live_block_11.py`, `git ls-files`, collection census).
Verdict location: §1. Details: §2–§7. Action list: §8.

---

## 1. Headline verdict — the central discrepancy

**Commit `3609864` (`feat(phase11): hard safety invariant — LIVE blocking (7 tests)`) changes exactly ONE file and ZERO production lines:**

```
tests/test_live_block_11.py | 142 ++++ (new file, tests only)
git show --stat 3609864  →  1 file changed, 142 insertions(+), 0 deletions
```

There is **no Phase 11 report file anywhere in the workspace** (glob of all `**/*.md` + grep for
`Phase 11|phase 11|LIVE blocking|3609864` finds only: the test docstring itself,
`docs/phase10/known_limitations.md:33`, and `docs/audit/phase10_final_evidence.md:165-169`).
The nearest thing to a "Phase 11 report" is the **Phase 10 final-evidence §Phase 11 Decision**,
which states the opposite of what the commit message implies:

> `docs/audit/phase10_final_evidence.md:165-169`: "**PHASE 10 GREEN — PHASE 11 MAY BE CONSIDERED.**
> Per hard boundary, **Phase 11 is NOT implemented in this task**… not Tests pass → live trading."
> `docs/phase10/known_limitations.md:31-33`: "then **Phase 11** (separate architectural decision, not auto-started)."

So the audited claim-vs-reality matrix is:

| Claimed (commit message + `test_live_block_11.py:1-6` docstring) | Actually implemented in `3609864` | Audit result |
|---|---|---|
| "hard safety invariant" | No source change; no guard, kill-switch, mode validator, or executor change | **FAIL — no invariant exists; only assertions about pre-existing defaults** |
| "LIVE blocking" / "LIVE = rejected/disabled" | LIVE path untouched (`main.py:112-135`, `BrokerEngine`, `DeltaExchange._require_auth` all pre-date the commit) | **FAIL — LIVE is default-off, NOT blocked. `LIVE_MODE=true + LIVE_EXECUTE=1 + creds` still places real orders by design** |
| "unknown = rejected" | No unknown-mode code or test (see §3, test 5) | **FAIL — nothing rejects an unknown mode; the test never exercises one** |
| "No live order submission endpoint may be called" | No instrumentation/interceptor added; test 7 patches `DeltaOrderExecutor.execute` then runs a `Backtester` that never calls it | **FAIL — vacuously true (see §3)** |
| "7 tests" | 7 tests exist, 7/7 pass (verified by execution this audit) | **PASS on count only — 4–5 of 7 pass vacuously (see §3)** |

**Bottom line:** `3609864` is a **tests-only snapshot of current defaults**, not a safety feature.
It does not make the system any safer than its parent commit. The commit message prefix
`feat(phase11)` overstates this and directly contradicts the Phase 10 boundary
("Phase 11 NOT implemented… separate architectural decision, not auto-started").
Recommendation: either (a) revert the `feat(phase11)` framing (rename to `test:` + document
that no invariant was added), or (b) implement the invariant for real (§8, items P0-1…P0-4)
and replace the vacuous tests with ones that can actually fail.

---

## 2. What `3609864` actually contains (verified)

- One new file: `tests/test_live_block_11.py` (142 lines, class `TestLiveBlocking`, 7 methods).
- Re-ran here: `python -m pytest tests/test_live_block_11.py -v` → **7 passed** (7.66 s).
- Passing ≠ proving. Test-by-test analysis in §3.
- No changes to `config/settings.py`, `main.py`, `core/live/broker_engine.py`,
  `core/execution/order_executor.py`, `core/exchanges/delta/delta_exchange.py`,
  `core/runtime/*`, or any risk/pipeline file.

---

## 3. The 7 tests — individual verdicts (all imports resolve; most assert nothing)

Pre-check: the imports the tests rely on **do exist**, so failures are logic-vacuity, not import errors:
`core/runtime/paper_main.py:273` (`build_paper_engine`), `core/runtime/execution_port.py:69`
(`PaperExecutionAdapter`), `BrokerEngine(pipeline, event_bus, executor, dry_run)`
(`core/live/broker_engine.py:150-160`), `DeltaExchange(api_key="", api_secret="")`
(`core/exchanges/delta/delta_exchange.py:26-32`; `""` correctly trips `_require_auth:75-83`
because only `None` falls back to settings and `authenticated` is `bool(key and secret)`).

| # | Test (`tests/test_live_block_11.py`) | What it really does | Verdict |
|---|---|---|---|
| 1 | `test_paper_mode_allowed:14-19` — asserts `settings.PAPER_MODE is True`, `LIVE_MODE is False` | Reads env-derived defaults (`config/settings.py:45-46`). Correct today; brittle under any operator env override. Proves nothing about blocking. | WEAK (default-snapshot) |
| 2 | `test_live_mode_rejected_without_credentials:21-41` — `_require_auth` raises (good, lines 26-27 SOUND), then `executor.execute(Mock(...))` expecting fail-closed | Second half never reaches auth logic: `registry=Mock()` → `.get()` returns a `Mock` contract → `build_payload` (`order_executor.py:121,140-143`) does `round(value, Mock)` → `TypeError`, swallowed by `except Exception: pass` (`:40-41`). Also `Mock.valid`/`order_id` are truthy Mocks, not real `OrderIntent` fields. Passes regardless of auth behavior. Real result shape `{"success": bool, ...}` (`:69-90`) never asserted. | VACUOUS second half — rewrite with a real `OrderIntent(valid=False)` + real registry stub |
| 3 | `test_paper_execution_does_not_call_live_endpoint:43-79` — builds `BrokerEngine(..., dry_run=True)`, asserts `mock.execute.assert_not_called()` | Never calls `run_candle`/`on_candle`; the mock is never driven, so the assertion is trivially true. Uses a `Mock` executor, not the real `PaperExecutionAdapter` (whose `balance/positions/fetch/cancel` raise `PaperOnlyError`, `execution_port.py:99-123`). Proves no paper boundary. | VACUOUS — drive at least one candle that yields an intent, then assert |
| 4 | `test_live_execute_requires_explicit_opt_in:81-84` — asserts `not settings.LIVE_EXECUTE` | Snapshot of `config/settings.py:47` (`""` → `False`). Correct, brittle, proves no enforcement. | WEAK (default-snapshot) |
| 5 | `test_unknown_execution_mode_rejected:86-93` — imports `build_paper_engine` but never calls it; re-asserts `PAPER_MODE/LIVE_MODE` | Duplicate of test 1. **No unknown mode is constructed, dispatched, or asserted.** The claim "unknown = rejected" is entirely untested. | FAILS ITS TITLE — vacuous |
| 6 | `test_paper_runtime_does_not_instantiate_live_executor:95-103` — `build_paper_engine()`, loops `engine.runtimes.values()` asserting `PaperExecutionAdapter` + `dry_run` | `build_paper_engine()` returns a `RealTimeEngine` with `runtimes={}` (`core/runtime/realtime_engine.py:161`); population happens only in `_reconcile:270-310` via `poll/refresh/start`, none of which the test calls. Loop iterates **0×, asserts nothing**. Attribute names exist (`paper_runtime.py:69-80`) but are never exercised. | VACUOUS (0-iteration loop) — call `_reconcile`/drive one symbol first |
| 7 | `test_no_live_order_submission_in_paper_tests:105-142` — patches `DeltaOrderExecutor.execute`, runs `Backtester`, asserts 0 calls | `Backtester` fills via `TradeSimulator.open_trade` (`backtesting/backtester.py:928-934`), **never** via `DeltaOrderExecutor`. `len(calls)==0` is structurally guaranteed. | VACUOUS — patch the surface actually used, or run the broker path with a counting fake |

Net: tests 1+4 are true-but-brittle default snapshots; tests 3+5+6+7 cannot fail as written;
test 2 is half-sound (auth guard) + half-dead (executor half). A genuine "hard invariant" suite
needs at least: (i) LIVE-mode construction refused or armed-explicitly with a typed error,
(ii) unknown-mode dispatch raising (not default-asserting), (iii) an end-to-end dry-run candle
that produces an intent and proves zero exchange writes via a counting transport fake,
(iv) a negative control with `dry_run=False` + no creds proving fail-closed at `place_order`.

---

## 4. Architecture audit — sound pipeline, default-off (not hard-blocked) LIVE

What is good (keep):

- **Single-pipeline rule holds.** `InstitutionalPipeline.__init__` is the sole `register(ExecutionEngine())`
  (`core/pipeline/institutional_pipeline.py:124`); `register()` dedupes by name (`:149-161`) with an
  `IndicatorEngine` guard (`:134-147`). `main.py:44` constructs once with a do-not-re-register comment
  (`:29-42`). The STATUS-99 double-registration defect is fixed everywhere checked:
  only intentional dedupe test `tests/test_execution_lifecycle.py:593` still references it;
  `examples/test_live_broker.py:66`, `examples/test_paper_trading.py:61` construct without re-registering.
- **One intent contract across modes.** Backtest/Paper/Live all consume `OrderIntent`
  (`core/risk/order_intent.py:33-81`) through `TradeSimulator` (sim) or `DeltaOrderExecutor` (live)
  — the documented `Signal → Risk → Order Intent → Execution Adapter` flow (`order_executor.py:1-22`).
- **Entry-touch + consume-once enforced in backtest.** Legacy branch `order_id` guard
  (`backtesting/backtester.py:535-539`), touch gate (`:541-543`), pending-pass touch gate (`:867`),
  `mark_filled` (`:940`), single-position gate (`:920-922`), `filled_bar/terminal_bar` (`:944-951`),
  inclusive touch `low<=entry<=high` (`_candle_touches_entry:1038-1057`), loud `!=1` close guard
  (`_book_closed_trades:1200-1204`). `BrokerEngine._route:351` mirrors with a `current_trade` guard.
- **Fail-closed auth primitive exists** (`delta_exchange.py:75-83` + `delta_auth.py:115-120`).
  Empty-string creds raise `RuntimeError`. Good — but it is a *guard*, not an *invariant*.

What is overstated / missing (the "LIVE blocking" gap):

1. **LIVE is reachable by configuration, by design.** `main.py:69/112` branches on
   `settings.PAPER_MODE` then `settings.LIVE_MODE`; live placement requires
   `LIVE_MODE=true + LIVE_EXECUTE=1 + DELTA_API_KEY/SECRET` (`main.py:123-133`,
   `dry_run=not settings.LIVE_EXECUTE`, `config/settings.py:45-47`). That is a sane
   default-off posture — it is **not** "LIVE rejected/disabled". Nothing in `3609864`
   changes this, and the docstring's "unknown = rejected" has no corresponding dispatcher:
   there is no mode enum/validator; an unknown combination simply falls into `else: pipeline.subscribe`
   (analyze-only, `main.py:137-139`).
2. **Both-true ambiguity undocumented.** `PAPER_MODE=true + LIVE_MODE=true` → PAPER wins
   (first branch). Harmless precedence, but no warning/conflict error; an operator typo is silent.
3. **No kill-switch / typed refusal.** There is no `LiveBlockedError`, no `ALLOW_LIVE` master flag,
   no startup refusal banner, no audit log line proving "live refused because X". The suite therefore
   cannot distinguish "blocked by invariant" from "not configured".
4. **Dry-run is a constructor argument, not a property of the mode.**
   `BrokerEngine(..., dry_run=True)` defaults safe (docstring `:37-42`), but any caller can pass
   `dry_run=False`; the tests never construct the `main.py:128-133` live wiring, so the actual
   arming expression `dry_run=not settings.LIVE_EXECUTE` is untested.

---

## 5. Logic + mathematics audit

### 5.1 Position sizing (`core/risk/position_sizer.py:229-364`, `config/risk_settings.py`) — CORRECT with two edge notes

- Formula chain is right: `risk_amount = balance * risk_percent` (`:229`);
  `stop_distance = |entry − stop|` (`:239`); fail-closed on `stop_distance <= 0`
  (returns `valid=False, quantity=0`, `:245-275`); `quantity = risk_amount / stop_distance` (`:281`);
  `position_value = quantity * entry` (`:283`); `margin = notional / leverage` (`:285`);
  allocation cap scales quantity+notional (`:299-309`) with an explicit `cap_reason` (`:309`);
  `expected_loss = quantity * stop_distance` (`:311`) and `risk_amount` re-aligned to it when capped (`:318-329`).
- Allocation base `min(balance, MAX_ALLOCATION_PER_TRADE=500)` (`:231-237`) matches the
  "₹2000 capital / ₹500 default position" posture. `MAX_TOTAL_EXPOSURE_PCT = 25.0` (`risk_settings.py:90`)
  is documented as a runaway-pending backstop sized for 8 slots — coherent, though generous by construction.
- Edge notes (minor, suggest fixes in §8):
  - Negative/zero `balance`: `actual_risk_percent` guards `balance > 0` (`:323-327`), but initial
    `risk_amount = balance * risk_percent` can go negative if `balance < 0`; downstream quantity would
    be negative. Add an explicit `balance <= 0 → invalid` early return.
  - `ENTRY_DELAY_BARS = 1` + `MAX_WAIT_BARS = 30` → `bars_pending = 31` eligible-window accounting is
    consistent with the bar-anchored comments (`risk_settings.py:40-52`); no off-by-one found in the
    constants themselves (lifecycle ordering `update → invalidation → fill → advance-after` was verified
    in a prior phase per STATUS; not re-executed here).

### 5.2 Costs — honest but live-misleading by default

- `COMMISSION_PER_TRADE = 0.0`, `COMMISSION_RATE = 0.0`, `SLIPPAGE_BPS = 0.0`
  (`risk_settings.py:345-353`) — explicit zero-cost, matching the Phase 10 evidence disclosure
  (`phase10_final_evidence.md:19`). Code-correct; strategy PnL (≈+3.81 on the 5000-bar baseline) is
  therefore a **gross-idealized** figure. Any live-readiness claim must re-run with real taker fees
  (~0.02% noted in `known_limitations.md:24`). The `BrokerEngine` comment that exchange-reported PnL
  is already net of fees (drop modeled costs to avoid double counting) is the right policy — flagging
  here so a future live path doesn't regress it.

### 5.3 Performance analytics (`core/analytics/performance.py`) — CORRECT definitions, one interpretation caveat

- Win/loss/breakeven triad (`:30-49`), `profit_factor = gross_profit / gross_loss`
  (`inf` when only wins, `0.0` when no profit, `:40-42`), expectancy = mean over completed incl.
  breakevens (`:43-45`), open-trade exclusion — all sound and contract-tested per STATUS.
- Sharpe/Sortino (`:373-415`): computed on the **per-trade position-return series**
  (`pnl / (entry*quantity)`, `:382-392`), mean/std with `sqrt(N)` scaling (`:398-402`),
  Sortino on the downside-clipped series (`:404-414`). The code **documents** this as
  "trade-based Sharpe, not annualized" (`:377-378`) — acceptable as a comparative diagnostic,
  but it is **not** a standard time-based Sharpe and must never be compared against one.
  Minor: downside series keeps zeros (`min(0, r)`), which dampens `downside_std` (common variant;
  stricter Sortino uses only negative observations). Suggest documenting the choice.
- Equity curve from exit-time-sorted closed trades with peak/drawdown — sound construction.

### 5.4 Not re-executed this pass (honesty note)

- `core/validation/` (walk-forward fold carving/overlap, Monte Carlo `Random(seed+index)` determinism,
  optimizer `max_combos`), incremental indicator/swing/displacement caches, and the
  economic-dedup `ECONOMIC_TICK_SIZE` fingerprint math were **not** re-read line-by-line in this pass;
  STATUS 97–102 records byte-identical proofs for each. No contrary evidence was found, but this audit
  does not re-certify them. Recommend a dedicated math pass before any live-readiness review (§8).

---

## 6. Code errors + robustness findings (pre-existing, NOT introduced by `3609864`)

All verified by read/execution this audit; none are caused by the audited commit (which adds no source):

1. **`ContractRegistry.get` → `None` crash path.** `registry.get` is a bare `dict.get`
   (`core/exchanges/contract_registry.py:23-25`); `_contract()` raises cleanly on miss
   (`order_executor.py:94-106`), but `build_payload` then does `int(contract.product_id)` /
   `round(qty, quantity_precision)` (`:121,134-142`) with no `None`/non-numeric guard.
   `BrokerEngine._route:467-470` can store `None product_id`; `_find_position:601-612` guards
   `pid is not None` yet `int(pid)` still raises on non-numeric strings. Fix: validate
   `product_id` + precisions at `_contract()` time with a typed error.
2. **Tolerant readers mask schema drift.** `_field/_fields_list` (`broker_engine.py:74-113`,
   20 call sites) unwrap `{"result": …}` and take the first non-`None` candidate
   (e.g. equity `total_equity/equity/total_balance :748-753`, exit price fallbacks `:669-674`).
   `_sync_equity:755-756` silently returns on `None`; `_book_live_close:679-680` falls back to
   `entry` price. Resilient, but silent — add degraded-health emission when fallbacks trigger.
3. **Silent swallows.** 87× `except Exception` in core/backtesting/config/data (0 bare `except` —
   good); loudest: `backtester.py:1180-1181` (breakout-resize audit), `paper_runtime.py:123-125`
   (journal, by design), `broker_engine.py:544,631,739` (live sync/watch/balance log-and-return).
   Safe but outage-hiding; suggest error counters.
4. **Network-error `KeyError`.** `DeltaContractLoader.load:39` does `download()["result"]` —
   raises `KeyError` (not a typed connection error) on transport failure. Wrap it.
5. **Zero-size handling is correct** (`_find_position(include_zero=False)` `:556,586-599`; `True`
   only for flat-record exit lookup `:664`). No change needed — noted to prevent "fixing" it.

---

## 7. Repo hygiene + test-suite health (executed checks)

- **Suite counts.** `tests/test_*.py`: **148 files** here. `pytest tests/ --collect-only` → **1735
  collected, 0 errors** (per executed sub-check, ~54 s). Bare `pytest --collect-only` (no ignores) →
  1735 + **24 collection errors**: 22× `_archive/examples/test_*.py`, 1×
  `examples/test_market_structure.py:14` (`MarketStructureEngine has no attribute registry`),
  1× `examples/test_portfolio_backtester.py` (live `httpx.ReadTimeout`), 1× `tests_list.txt`
  (`UnicodeDecodeError`). There is **no `pytest.ini`/`pyproject.toml`/`setup.cfg`/`conftest.py`**,
  so the `_archive` exclusion is conventional, not configured (`git check-ignore` empty) — the
  Phase 10 evidence table's "24 legacy collection errors intentionally excluded" (`phase10_final_evidence.md:107-112`)
  depends on the caller remembering `--ignore=_archive --ignore=examples`. Add a `pytest.ini`/`pyproject`
  `norecursedirs` + `collect_ignore` so the default invocation is the honest one.
- **Tracked secrets/venv/log noise (pre-existing, still true).**
  `git ls-files` shows `.env` tracked (despite `.gitignore:6-7`), `logs/engine.log` tracked
  (despite `.gitignore:30`), and **`.venv/` tracked (~7215 files)**; `_archive/` 75 files tracked
  (172 on disk). Tracked files bypass ignore rules (`git check-ignore` returns empty for both).
  Also `git status --short` shows modified `__pycache__/*.pyc` (pycache committed — should never be)
  plus the untracked `muse suggetions.md` (this file). Recommend: stop tracking `.venv/`,
  `__pycache__/`, `logs/`, `.pytest_cache/`; decide `.env` policy explicitly (if it holds real
  `DELTA_API_*`, rotate after untracking — history retains it).
- **Dependencies.** `requirements.txt` 9 pins vs usage: `aiohttp==3.10.5` **0 first-party hits**
  (unused), `orjson==3.10.7` **0 hits** (unused), `loguru==0.7.2` effectively dead (only
  `core/logger.py:2`; `logging_config.py:20-24` says loguru is not a dep and nothing imports it),
  `pyarrow` only transitive via `df.to_parquet` (`history_storage.py:120`); live users are
  `httpx` (15 hits), `websockets`, `dotenv`, `pandas` (single user), `numpy` (guarded imports +
  pandas transitive). `pytest` itself is **not pinned** and the committed `.venv` has no pytest
  (`No module named pytest`) while system Python has 8.4.2 — pin the test runner or document it.

---

## 8. Suggested actions (prioritized)

### P0 — fix the Phase 11 misrepresentation (pick one)
1. **Option A (honest, cheap):** reframe `3609864` as tests-only — e.g.
   `git commit --allow-empty -m "docs(phase11): scope note — 3609864 adds default-snapshot tests only; no LIVE invariant implemented"` 
   and amend the Phase 10 boundary doc to list `3609864` explicitly as *not* a Phase 11 implementation.
   Do not leave `feat(phase11): hard safety invariant` standing: it will mislead every future audit.
2. **Option B (real invariant):** implement an actual hard block behind an explicit flag, e.g.
   `ALLOW_LIVE=false` default; `DeltaOrderExecutor.execute` + `BrokerEngine(live)` refuse with a typed
   `LiveBlockedError` unless `ALLOW_LIVE=true AND LIVE_EXECUTE=1 AND creds present`; unknown mode enum
   raises instead of falling into analyze-only; startup logs the refusal reason; every refusal path
   covered by a test with a negative control (live wiring attempted → typed error, zero transport calls
   counted at the `rest.post` layer, not at an unused mock).

### P0 — make the 7 tests honest (whether or not P0-2 is taken)
3. Rewrite tests 2,3,5,6,7 per §3 table: real `OrderIntent` (not `Mock`), drive ≥1 candle through
   `BrokerEngine.run_candle` with a counting transport fake, call `_reconcile` (or equivalent) before
   asserting runtimes non-empty, construct + dispatch an actually-unknown mode, and count calls on the
   surface each path really uses (`TradeSimulator.open_trade` for backtest, `rest.post("/v2/orders")`
   for live). Every test must be shown to **fail** when its guard is removed (mutation check).

### P1 — safety hardening (small, high-value)
4. Document + warn on `PAPER_MODE && LIVE_MODE` (conflict warning, PAPER precedence logged).
5. Validate `product_id`/precisions in `DeltaOrderExecutor._contract()` with a typed error (fixes §6.1).
6. Emit degraded-health + counters whenever `_field` fallbacks or live sync/balance swallows trigger (§6.2–6.3).
7. Wrap `DeltaContractLoader.load` transport errors in a typed connection error (§6.4).
8. Guard `balance <= 0 → invalid` in `PositionSizer` (§5.1).

### P1 — repo hygiene
9. Add `pytest.ini` (or `pyproject`) with `norecursedirs = _archive .venv …` + `collect_ignore` so bare
   `pytest` == the honest 1735-test run; fix or quarantine `examples/test_market_structure.py:14`.
10. Untrack `.venv/`, `__pycache__/`, `logs/`, `.pytest_cache/` (`git rm -r --cached`, keep ignore rules);
    make an explicit, documented decision on `.env` (and rotate keys if it ever held real secrets).
11. Prune/pin deps: drop or justify `aiohttp`/`orjson`/`loguru`; pin `pytest`.

### P2 — before any live-readiness review
12. Re-run Gate A second-run reproducibility + a real-fee (`commission+slippage`) sensitivity pass;
    the zero-cost default (§5.2) flatters every PnL figure in the evidence docs.
13. Dedicated math re-certification of `core/validation/` + incremental caches + economic-dedup
    fingerprint/cluster tolerances (§5.4) with the formulas quoted in the report.
14. Keep the §Phase-10 boundary discipline: no `feat(phase11)` / `feat(live)` commits without the
    PAPER-soak prerequisites (`known_limitations.md:29-33`) evidenced first.

---

## Appendix — evidence pointers (all paths repo-relative)

- Audited commit: `git show --stat 3609864` → `tests/test_live_block_11.py | 142 +++`; `git show 3609864` (full diff in audit notes).
- Absent Phase 11 report: `glob **/*.md` (31 hits, none phase-11); `grep Phase 11|live_block|3609864` → 6 hits (§1).
- Boundary docs: `docs/audit/phase10_final_evidence.md:165-173`, `docs/phase10/known_limitations.md:27-33`.
- Mode wiring: `config/settings.py:45-47`, `main.py:69-139`, `core/live/broker_engine.py:37-42,150-160`,
  `core/exchanges/delta/delta_exchange.py:61-83,117-124`, `core/execution/order_executor.py:62-106`.
- Sizing/math: `core/risk/position_sizer.py:229-364`, `config/risk_settings.py:21-112,334-397`,
  `core/analytics/performance.py:30-49,373-415`.
- Robustness: `core/exchanges/contract_registry.py:23-25`, `core/live/broker_engine.py:74-113,544,631,739,748-756`,
  `backtesting/backtester.py:535-543,867,928-951,1038-1057,1180-1181,1200-1204`.
- Hygiene: `git ls-files` (.env / .venv / logs tracked), `git status --short` (pyc modified + this file untracked),
  `requirements.txt` (9 pins), no `pytest.ini|pyproject.toml|setup.cfg|conftest.py`.

*End of independent audit. The system as of `3609864` is best described as: Phase 10 PAPER pipeline
intact and default-safe, with a tests-only commit that documents — but does not enforce — that posture.
The word "blocking" in the commit message is the single most misleading artifact in the recent history;
everything in §8 flows from correcting it.*
