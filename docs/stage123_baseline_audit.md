# Stage 1–3 Production Hardening — Baseline Audit (forensic, pre-change)

HEAD `07def05`, branch `main` (+125 vs `origin/main`; remote
`github.com/vishalkharade1-svg/quantengine-spring-41.git`, fetch
only — no push performed). 153 commits on HEAD. Extra refs:
`refs/agents/be5197f0-*/checkpoints/*` (tooling checkpoints, not
reviewed branches) + local branch `agents/todo-list-analysis-fix`
(unrelated, untouched). Tree: only the two pre-existing untracked
notes files. All claims below verified against repository evidence
on 2026-09-09; reports not trusted.

## 1. Security forensics — SECURITY_BLOCKED (fail-closed)

- Tracked source: CLEAN. 17 pattern hits, all synthetic test
  fixtures (`SYNTHETIC-TEST-KEY`, `k`/`s`, and a deliberate
  `REAL-LOOKING-*` pair inside a no-leak test,
  `tests/test_live_block_11.py:639-655`). `.env.example` ships
  empty credentials by design.
- Git history: 5 `.env` blobs with live-format Delta credentials
  (`DELTA_API_KEY` 31 chars, `DELTA_API_SECRET` 62 chars, all
  non-placeholder-like), commits `63cd4f1` (`8e41290a…`),
  `e686ccd` (`3aa58533…`), `d5846fc`/`e49f61e` (`f9445598…` shared),
  `2f9bf0e` (`7275411a…`). All are ancestors of HEAD (verified both
  ends) — reachable forever without history rewrite. Untracked
  since `131660f`, never purged. No rotation evidence in repo.
- Working tree: ignored local `.env` (git-ignored, never committed)
  carries the same 31/62-char credential shapes. Validity
  deliberately UNTESTED (no exchange contact per safety rules).
- Verdict: fail-closed BLOCKED. Operator actions required (outside
  this milestone, no auto-rotation): confirm rotation/revocation of
  the exposed Delta pair, restrict the local `.env` host, and
  explicitly authorize-or-decline history purge (no rewrite
  performed here). `LiveSafetyGate`
  (`core/execution/live_safety_gate.py:272`, decide/require) gates
  mode+credentials and never leaks secrets (tested).

## 2. Cost architecture — zero-cost production defaults (P0 realism gap)

- Production math (`core/risk/risk_engine.py:294-304`): commission =
  `COMMISSION_PER_TRADE + notional*COMMISSION_RATE`, slippage =
  `2*notional*SLIPPAGE_BPS/10000`. Formula is sound and shared.
- Production defaults (`config/risk_settings.py:352-360`): 0.0 /
  0.0 / 0.0 — EXPLICIT zero-cost. Every production/paper/backtest
  path running on defaults books zero fees/slippage. Prior audits
  already flagged real Delta taker fees as unconfigured.
- Research ladder (`COST_SCENARIOS_11F` A/B/C/D: 0 | 0.05%+2bp |
  0.059%+5bp | 2xC) is separate, frozen, heavily pinned — 11F/11G
  economics do NOT read production globals (per-spec assembly).
  `COMMISSION_RATE=0` therefore does NOT affect frozen research
  results (verified: research cost paths take explicit specs).
- Legacy second ladder in `scripts/cost_sensitivity_11b.py` (11B
  scenarios; mutates global `risk_settings` — script-only).
- Finding: no single authoritative cost abstraction; production
  zero-cost default is the realism blocker for any live/paper
  claim. Defaults stay 0.0 (explicit; changing them would retune
  economics) — centralize formula, document models.

## 3. R:R policy — triple shadow thresholds, live gate 2.0

- `config/risk_settings.py:396` MIN_RISK_REWARD = 2.5 — DEAD for
  the decision path (nothing reads it there).
- `core/setup/decision_engine.py:41` MIN_RISK_REWARD = 2.0 class
  attr — the LIVE gate (`rr < gate` → terminal "Risk Reward"
  rejection, `:183-187`, acceptance requires zero reasons).
- `config/trading_profile.py` min_rr 3.0/2.5/2.0 — DEAD (read only
  by a print script `tests/test_trading_profile.py`).
- Formula (`trade_setup_builder.py:163-193`): rr =
  |target-entry|/|entry-stop|, side-checked, NO costs, NO tick
  rounding at calc. `PositionSize.risk_reward`
  (`core/risk/position_size.py:85-91`) is a different ratio
  (notional/expected_loss) with zero production consumers —
  confusing but inert. RiskEngine does NOT revalidate RR (logs it).
- Required: single 6.0 source; engine reads config; RiskEngine
  defense-in-depth revalidation; 6.0→5.99/6.01/tick mutations.

## 4. Config governance — shadows documented (RR fixed here, rest noted)

- Shadow pairs (engine class-attr vs config): RR 2.0 vs 2.5,
  confidence 70 vs 80, regime score 70 (no config twin found).
  Only RR is in mandate-scope; the rest are recorded YELLOW, not
  silently changed.
- Profiles (`trading_profile.py`) inert; `risk_settings.py` is the
  de-facto policy file (well-commented, phase-annotated).

## 5. Reconciliation — effectively absent (must build)

- Sole exchange comparison:
  `core/live/broker_engine.py:660-701` `_sync_live` detects
  flat-vs-open only (books close, no halt, no qty/side/entry
  compare, no order compare, exceptions only logged).
- `_watch_open_order` (`:766-788`) clears dead orders silently.
- No startup HALT (`__init__` does zero exchange reads). Paper
  never reconciles (`PaperOnlyError`). Equity sync keeps last on
  malformed input (no halt).

## 6. Restart — all trading state RAM-only (must build)

- Lost on restart: open position, pending orders + bar windows +
  cooldowns, closed-trade registry, account equity/PnL/drawdown,
  portfolio reservations, swing cache, router dedupe, workers.
  (`docs/phase10/paper_runtime.md:28` admits in-memory ledger.)
- Persisted (non-trading): instrument catalog, research JSON,
  parquet history, opt-in CSV exports, audit JSONL.

## 7. Order lifecycle — atomic fills, placeholder terminals

- States: NEW/PENDING/FILLED/CANCELLED/REJECTED/EXPIRED/
  INVALIDATED (`order_registry.py:44-50`). CANCELLED/REJECTED are
  placeholders (never written by registry); exchange-observed
  terminal states are never written back. No partial-fill
  representation anywhere; simulator is single all-or-nothing slot.
  Exits: SL/TP only (SL-first ambiguity), no time/trailing/manual.

## 8. WebSocket — reconnect exists, heartbeat missing

- Delta multiplexed transport + legacy single-symbol feed; reconnect
  with capped backoff + jitter, resubscribe, dedupe (256), disorder
  drop all exist. Heartbeat/ping-pong: MISSING (liveness is
  data-driven via staleness). No sequence-gap detection, no REST
  backfill (gaps counted, never repaired).

## 9. Paper/live parity — shared math, divergent scope

- Shared: InstitutionalPipeline, RiskEngine, OrderIntent,
  TradeSimulator/Registry, Account, OrderRegistry, sizing, analytics.
- Divergent: paper multi-symbol per-key runtimes vs LIVE
  single-symbol (`SYMBOLS[0]`) bespoke wiring; paper adapter vs
  live executor. LIVE stays single-symbol (scope pin, not expanded
  here).

## 10. Breakers / misc

- Daily breaker enforced ONLY when caps injected
  (`core/risk/portfolio.py:436-442`); default PAPER runtime has NO
  caps (neutral default). Weekly/monthly diagnostic-only;
  kill_switch never read; NaN/inf fail-OPEN (`_fnum` coerces to 0).
- Swing fractal cache (`swing_engine.py:55`) UNBOUNDED plain dict
  (per-engine lifetime growth).
- Dup dirs: `backtesting/backtester.py` + `core/backtesting/*` +
  `core/risk/*` CANONICAL (prod import combo); `risk/portfolio_risk.py`
  LEGACY (old tests only); `backtesting/logger.py` unreferenced.
- Gate A baseline (pre-change): 27/11/6/5/0/+0.117534. The mandated
  RR 6.0 gate WILL change production-pipeline outputs; the new
  fingerprint will be recorded with the delta proven RR-only.

## 11. Research/OOS status (untouched)

- 11G-K frozen (`f803fe7d…`, 8 hashes OK); 11G-L: 004/007 FAIL,
  rest insufficient/silent; 11G-M: empty eligibility; D3 sealed
  0/0/0. Conclusion stands: NO EDGE ESTABLISHED. Nothing here
  re-evaluates, optimizes, or promotes.
