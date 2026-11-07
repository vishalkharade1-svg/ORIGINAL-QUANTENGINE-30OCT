# QuantEngine Audit Report — 2026-09-14

## Remediation addendum — 2026-09-16

This report preserves the original audit snapshot below. The following findings
have since been remediated or superseded and must be read as historical:

- The active ignored `.env` was sanitized; the current-worktree secret scan
  passes.
- Published `origin/main` history was rewritten, independently verified free
  of reachable `.env` commits, and advanced through
  `0e2bd7ca834ee20f16e27ea5b5fe96901825c5ba`.
- Credential revocation/account review and retirement of stale clones,
  worktrees, forks, and caches remain required external incident actions.
- The data/risk/readiness hardening delivered in Phase 20 is unit tested and
  deliberately fail-closed. It does not validate Delta's private API,
  contract metadata, real candle lifecycle, or live order semantics.

The original live-trading prohibition remains in force.

## A. Executive summary

**Verdict: FUNCTIONAL BUT SIGNIFICANTLY BROKEN.**

The repository contains a coherent, testable *paper/backtest framework* for one Delta-oriented price-action strategy.  Its order/risk path is substantially more developed than a prototype: a pipeline produces `OrderIntent`s, the risk stage re-checks 1:6 R:R and geometry, and the only production exchange-write path found is behind `LiveSafetyGate`.

It is not a complete QuantEngine implementation and must **not** be used for live trading.  The decisive blockers are: live candles are fabricated from ticker marks and given zero volume; the active pipeline contains no order-flow, footprint, volume-profile, confluence, Fibonacci, VWAP, Bollinger, OBV, or Wyckoff stage; trading costs default to zero; exchange contract/market-data behaviour has only mock coverage; and real credentials are present locally and were committed historically.

Paper mode can run without exchange writes, but it is only safe as an engineering integration exercise.  It is **not safe as evidence of executable strategy economics** while data, venue metadata, fees, liquidity, and fill behaviour remain unverified.

## B. Scope, method, and runtime evidence

This audit inspected the current checkout, not the prior phase reports.  No production code was changed.  Existing untracked files were left untouched (`muse suggetions.md`, `muse suggetions1.md`).

| Check | Result |
|---|---|
| Python syntax (`.venv\\Scripts\\python -m compileall -q main.py core data backtesting config risk tests`) | **PASS** |
| Runtime imports in committed venv | **PASS** for httpx, websockets, dotenv, pandas, numpy and `main` |
| Documented venv test command | **BROKEN**: the local `.venv` lacks `pytest` despite it being pinned in `requirements.txt` |
| System-Python test collection | **3,022 tests collected** |
| Focused safety/math/execution suite | **209 passed** in 11.39 s |
| Earlier focused suite | **138 passed** in 4.26 s |
| Full suite | **NOT VERIFIED**. Two attempted full invocations remained CPU-bound past the tool window and were terminated; no full-suite success claim is made. |
| Pytest environment | Warnings: `.pytest_cache` write was denied. This is an environment hygiene problem, not a test pass/fail. |

The focused suites cover sizing, R:R/geometry, simulator, lifecycle, Delta auth/exchange, order executor, live gate, and operational tests.  They demonstrate those fixtures pass; they do **not** prove Delta's live schema, a real order lifecycle, or strategy profitability.

## C. Repository inventory and actual architecture

The checkout has 1,253+ tracked/listed paths, a large `_archive/` tree, a `research/` tree, `core/`, `data/`, `backtesting/`, `config/`, `risk/`, `tests/`, scripts, and prior audit artifacts.  The production entry point is `main.py`; paper mode enters `core.runtime.paper_main.build_paper_engine`, while the live branch creates a single `BrokerEngine` with `DeltaOrderExecutor`.

Actual active price path:

```text
Delta ticker WebSocket (one multiplexed connection)
  -> CandleBuilder using ticker mark price
  -> synthetic Candle(open/high/low/close; volume=0)
  -> RealTimeEngine (paper multi-symbol) OR legacy EventBus (live/analyse)
  -> InstitutionalPipeline
       indicators (EMA/ATR/ADX/RSI)
       trend/swing/structure/BOS/CHOCH/liquidity/displacement/FVG/OB
       regime -> setup -> decision -> execution selection -> RiskEngine
  -> OrderRegistry / OrderIntent
  -> paper TradeSimulator OR BrokerEngine -> DeltaOrderExecutor -> Delta REST
```

The intended order-flow branch is absent from that runtime. `InstitutionalPipeline` registers only the stages at `core/pipeline/institutional_pipeline.py:107-125`; no `DeltaEngine`, `LiveDeltaProvider`, footprint, price-ladder, volume-profile, or confluence engine is registered.  The order-flow package is defined but has no non-test/non-self production importers.  `core/pipeline/stages/price_ladder_stage.py:61` is an empty `pass` stage.

The live branch is single-symbol (`main.py` initializes `MarketState(symbol=settings.SYMBOLS[0])`), whereas the paper `RealTimeEngine` is multi-symbol.  The explicit paper-universe helper marks every configured symbol `SPOT` and supplies fixed tick/quantity metadata at `core/runtime/paper_main.py:257`; it does not retrieve the actual contract metadata for the configured instrument.

## D. Requirement compliance matrix

| Requirement | Repository implementation | Status | Evidence / issue |
|---|---|---|---|
| Delta REST / signed order path | Delta adapter, HMAC helper, executor | **PARTIALLY VERIFIED** | mock/unit-tested; real endpoint/schema/authentication **EXTERNAL VERIFICATION REQUIRED** |
| WebSocket market data | Delta ticker subscription | **IMPLEMENTED BUT INCORRECT for OHLCV** | ticker-only channel and `volume=0.0`: `data/delta/delta_subscription_stream.py:365,517` |
| REST market data / history | adapters/providers exist | **PARTIALLY VERIFIED** | not the canonical paper default (`UNIVERSE=explicit`) |
| OHLCV | candle builder on ticker marks | **MISLEADING / INCOMPLETE** | no trade volume; mark-price OHLC is not exchange OHLCV |
| Order flow / delta / footprint / DOM | isolated models/providers | **DEFINED BUT NOT INTEGRATED** | no active pipeline import; no trades/L2 subscription |
| Technical analysis | EMA, ATR, ADX, RSI | **PARTIALLY VERIFIED** | focused math tests pass; only these indicators are active |
| VWAP, OBV, Bollinger | research-only utility references | **NOT IMPLEMENTED in runtime** | no active runtime stages |
| Smart money / structure / OB / FVG / liquidity | pipeline stages and tests | **PARTIALLY VERIFIED** | causal/unit tests exist; live input/data quality invalidates production confidence |
| Fibonacci / Wyckoff / confluence | placeholders / future comments | **PLACEHOLDER / NOT INTEGRATED** | `core/confluence/confluence_engine.py:21-22,140-141` |
| 1:6 R:R | Decision and risk revalidation | **VERIFIED LOCALLY** | `MIN_RISK_REWARD=6.0`; focused edge tests pass |
| Position sizing / PnL | sizer, accounting, simulator | **PARTIALLY VERIFIED** | unit-tested for linear quote-currency assumptions; not instrument-aware for live options/inverse products |
| Paper trading | multi-symbol dry-run runtime | **PARTIALLY VERIFIED** | no exchange writes by design; economics are neutral by default |
| Live trading | gated Delta broker path | **ARCHITECTURALLY UNSAFE / EXTERNAL VERIFICATION REQUIRED** | single venue/symbol path, no real test, flawed market inputs |
| Backtesting / replay | Backtester and simulator | **PARTIALLY VERIFIED** | defensive intrabar tests present; zero default costs and no realistic liquidity prevent trust |
| Reconciliation | snapshot and fail-closed reconciler | **PARTIALLY VERIFIED** | local contract tested; real private exchange state schema unverified |
| Crypto options architecture | Delta product mapping models | **INCOMPLETE** | no Greeks, option-specific pricing/risk/sizing/PnL lifecycle |
| NIFTY/SENSEX options / brokers | none found | **NOT IMPLEMENTED** |
| Multiple exchanges/brokers | Delta only | **NOT IMPLEMENTED** |
| Mobile/control API | localhost/token-gated control and optional gateway | **PARTIALLY VERIFIED** | tests exist; operational TLS and deployment configuration unverified |

## E. P0 critical issues

### P0-01 — Live “candles” are ticker-derived marks with fabricated zero volume

- **Files:** `data/delta/delta_subscription_stream.py:355-365, 379-517`; `core/pipeline/institutional_pipeline.py:107-125`
- **Problem:** The sole live subscription is `ticker`. A mark is passed to `CandleBuilder`; emitted candles explicitly set `volume=0.0`. This is not a trade feed, OHLCV feed, or order-book feed.
- **Danger:** Any volume-dependent feature, volume confirmation, liquidity interpretation, delta/footprint claim, or volume-based market-structure judgement is invalid. Mark-price candles can also differ materially from executable last-trade candles.
- **Evidence:** Direct code inspection; no active trade/L2/order-flow engine exists.
- **Correction:** Subscribe to a documented real trade stream and, where needed, L2 stream; construct OHLCV from trades (or consume exchange OHLCV with explicit provenance); reject/halt trading when required data is missing/stale/gapped.
- **Regression tests:** captured real-frame schema fixtures; trade-volume conservation; mark-vs-last explicit policy; L2 sequence/gap/recovery; live strategy refuses insufficient data.

### P0-02 — Default economics are zero-cost and no liquidity/latency model is enforced

- **Files:** `config/risk_settings.py:352-360,383-392`; backtest/paper simulator paths
- **Problem:** Commission and slippage default to `0.0`; the paper profile is explicitly `explicit-zero-neutral` by default.
- **Danger:** Backtest/paper PnL, executable R:R, break-even, allocation, and any performance conclusion can be materially overstated. The code labels the condition but does not prevent a neutral-cost run from being mistaken for operational readiness outside its reports.
- **Correction:** Require a versioned venue/instrument fee, funding, spread, slippage, and fill model for any performance or promotion gate; annotate every result with the applied model; block readiness certification when neutral.
- **Regression tests:** nonzero maker/taker fee, funding, partial-fill, spread, adverse gap and per-instrument multiplier cases.

### P0-03 — Exchange credentials are exposed in the local `.env` and were historically committed

- **Evidence:** `.env` contains non-empty Delta credentials; it is ignored now, but `git log --all -- .env` shows it in historical commits through `131660f`.
- **Danger:** Treat the credentials as compromised; a repository clone/history or backup may expose live trading access.
- **Correction:** Immediately revoke/rotate both credentials, inspect access/audit logs, remove secrets from all reachable Git history and backups using an approved procedure, and use a secret manager. Do not rely solely on `.gitignore`.
- **Regression tests:** pre-commit/CI secret scanning including history and artifact directories; assert `.env` is never included in build context/logs.

## F. P1 high issues

### P1-01 — Order-flow, footprint, volume profile and confluence are non-operational

Defined classes create a misleading surface, but there is no pipeline connection or adequate upstream data. `LiveDeltaProvider` needs real trade objects; none are supplied by the live runtime. Treat all related feature claims as **DEFINED BUT NOT INTEGRATED**, not implemented.

### P1-02 — Explicit paper universe fabricates instrument classification and precision

`_eligible_instrument()` hard-codes `SPOT`, tick `0.01`, quantity step/minimum `0.001`. That is unsafe for derivatives/options and can make paper sizing/rounding unlike the venue. The live path loads a contract registry, but its correctness is externally unverified.

### P1-03 — Live mode only wires the first configured symbol

Paper has a multi-symbol runtime; live `main.py` creates one market for `settings.SYMBOLS[0]`. This contradicts multi-symbol/multi-instrument expectations and creates paper/live parity drift.

### P1-04 — Bracket order semantics are assumed, not proven

The executor sends native bracket fields (`core/execution/order_executor.py:340-355`) but has no venue-contract integration proof for trigger price, reduce-only exits, partial bracket fill, cancellation, or restart recovery. The live tests use fake transports.

### P1-05 — Exposure controls are dangerously permissive by default

`MAX_TOTAL_EXPOSURE_PCT = 25.0` permits unresolved notional up to 25x equity and comments that it normally does not bind. Eight pending orders plus 10x leverage must be reviewed against true margin, correlated exposure, contract multiplier, and liquidation rules before live use.

### P1-06 — Options support is metadata-only

Delta option mapping exists, but there is no option valuation, Greeks, expiry exercise, multiplier-aware sizing, IV surface, or option-specific risk/PnL path. NIFTY/SENSEX have no implementation.

### P1-07 — Full test-suite health is unproven in the delivered environment

The documented virtual environment cannot execute pytest. The system Python collected 3,022 tests, but a full green run was not obtained. Existing phase reports and test count statements therefore remain unverified.

## G. P2/P3 issues and cleanup inventory

- **P2:** Duplicate domain models exist (`data/candle_builder.Candle` and `core/history/candle.Candle`; several old backtesting/execution/risk modules in `_archive`). Establish one canonical external event schema.
- **P2:** `main.py` creates a legacy context/market/event bus/pipeline before selecting paper mode, then paper mode creates a different runtime and returns. This is unnecessary split architecture and obscures the canonical path.
- **P2:** Broad exception handling is widespread (notably stream, monitor, remote, reconciliation and runtime modules). Some paths count/log errors, but many bare `except Exception: pass` branches risk loss of the root cause.
- **P2:** The sync WebSocket client runs in a thread while surrounding runtime APIs are partly async/synchronous. It needs a documented ownership/cancellation/shutdown model validated against real disconnect storms.
- **P3:** `README.md` is only a one-line repository name. `STATUS.md` is very large and historical; it is not an operator runbook.
- **P3:** `pytest.ini` deliberately excludes major trees from bare collection. This is reasonable for archives, but it must be accompanied by a canonical CI matrix that states what is and is not certified.

Canonical live responsibility currently appears to be: `InstitutionalPipeline` (signals), `RiskEngine` (intent creation), `OrderRegistry` (identity), `BrokerEngine` (route/state), `DeltaOrderExecutor` (payload/write), `Reconciler` (local-vs-exchange checks). Research and `_archive` code should not be treated as production.

## H. Mathematics audit

| Area | Current implementation / status | Finding |
|---|---|---|
| R:R geometry | `risk=abs(entry-stop)`, `reward=abs(target-entry)`, plus directional geometry | **locally verified**. Focused tests include inverted long/short, zero and non-finite cases; RiskEngine re-checks the value. |
| 1:6 enforcement | `MIN_RISK_REWARD=6.0`, decision and risk guards | **locally verified**, but calculated pre-execution. Default zero costs mean reported/economic R:R is not venue-executable. |
| Linear sizing | quantity roughly risk amount / stop distance, then allocation/quantity hygiene | **partially verified** for linear products. It is not a proven contract-multiplier/tick-value/inverse/options sizer. |
| PnL | directional gross PnL, net costs, realized-R helpers | **partially verified** by focused tests. Funding, venue fees, multiplier/currency conversion and option valuation are absent/unverified. |
| ATR | Wilder/RMA tests present | **locally verified** in focused unit tests. |
| Volume/order flow | live input is zero volume; no active stages | **not mathematically meaningful in runtime**. |
| Backtest fill math | conservative same-bar stop-first policy and next-bar breakout handling | **partially verified**. It still lacks proven venue realism, costs and liquidity. |

Do not interpret a passing indicator/backtest unit test as validation of the strategy. It validates local deterministic behavior under fixtures.

## I. Trading logic, duplication, and lifecycle

The operational strategy is price-structure based: indicators -> trend/swings/structure/BOS/CHOCH -> liquidity/displacement/FVG/order blocks -> regime -> trade setup -> decision -> ranked execution candidate -> risk-sized intent.  The registry and economic-fingerprint mechanisms provide useful same-setup/order deduplication; focused lifecycle tests passed.

However, the active configuration is `BREAKOUT_CONTINUATION`, and the system's reported confidence/score is not supported by a verified live volume/order-flow foundation. Zones and setup lifecycle are relatively well represented in code, but market validity is limited by the feed.  No claim of statistically valid edge is supported by this audit.

## J. Backtest integrity verdict

**Current backtest results cannot be trusted as real-world performance evidence.** They can be used for deterministic regression checks only.  Reasons: neutral default costs, no funding/liquidity/latency model, data/feed mismatch with live ticker-mark candles, no verified contract metadata, and no completed independent full-suite/replay certification in this environment.  The conservative intrabar policy and causal tests are positive engineering controls, not a substitute for a calibrated execution model.

## K. Live-trading safety verdict

**No — this repository must not place live orders.** Live safety-gate code is a positive control, and the static write-path search found the order write routed through `DeltaOrderExecutor.execute`. But live readiness is blocked by P0-01 through P0-03, unverified bracket/schema semantics, non-authoritative instrument information on the default path, single-symbol live topology, and absent real end-to-end exchange validation.

## L. Exchange integration audit

**Verified locally:** request-signing and payload/unit contracts against fakes; hard live arming conditions; no exchange writes from paper runtime.

**Mocked:** fills, rejects, partial fills, balances, positions, reconciliation records, WebSocket messages, and cancellation outcomes in tests.

**Unknown / requires external verification:** current Delta API request schema/signature/timestamp tolerance; ticker/trade/L2 schema; symbol/product mappings; bracket semantics; reduce-only exits; actual fee/funding/margin/contract multipliers; rate limits; real reconnect and reconciliation after outage.

## M. Performance and observability

No benchmark establishes a production bottleneck. Likely risks are unbounded/expensive structural work over candle windows, synchronous WebSocket/thread coordination, repeated list/deque conversions, and broad exception suppression. Proven operational concerns are more important: the feed records counters/gaps, but unrepaired data gaps do not constitute a demonstrated end-to-end trading halt policy. Logs have useful IDs in several order paths, but no single structured, durable event ledger joins market data -> signal -> risk decision -> order -> exchange acknowledgement -> fill.

## N. Testing gap analysis

Highest-priority missing tests are real captured-data contract tests, sandbox exchange integration, L2/trade gap and sequence recovery, actual contract/multiplier sizing, fee/funding/slippage/PnL reconciliation, order bracket and reduce-only lifecycle, process-crash/restart with real responses, paper/live data-parity, multi-symbol live routing, and negative tests proving all volume/order-flow claims are unavailable when only ticker data is present.

## O. Architecture correction plan

```text
Provider adapters (trades, L2, OHLCV, contracts, private state)
  -> validated normalized event schema + provenance + sequence/gap state
  -> authoritative per-instrument MarketState
  -> price/volume/order-flow feature stages (only when inputs qualify)
  -> strategy/setup -> authoritative RiskDecision
  -> execution state machine / idempotency / broker adapter
  -> durable reconciliation and correlated structured observability
```

Keep research, archive, simulation, and production modules in explicit separate packages with one-way dependencies.  Make `RiskDecision` the only executable capability; every broker adapter should accept it, not arbitrary strategy objects.

# QUANTENGINE REPAIR ROADMAP

### PHASE 0 — Critical safety / correctness
Rotate exposed secrets; disable/revoke live keys; set an irreversible live-trading kill switch; add CI secret/history scanning. Acceptance: no live credentials or secret history; no live process can arm without a formal operator procedure.

### PHASE 1 — Data foundation
Replace ticker-mark candles with documented trade/OHLCV/L2 sources; normalize timestamps, provenance, sequence and gaps; halt affected symbols on stale/unrepaired data. Acceptance: recorded exchange frames reproduce deterministic normalized events.

### PHASE 2 — Mathematics
Implement instrument-aware tick, multiplier, linear/inverse/options sizing and PnL; require costs/funding/spread. Acceptance: independent hand calculations and venue sandbox reconciliation match.

### PHASE 3 — Market structure
Audit every structure feature against the new causal event store; remove or label unavailable features. Acceptance: prefix-invariance/no-lookahead and data-sufficiency tests per feature.

### PHASE 4 — Strategy / signal engine
Separate score from probability; formally define setup validity, execution assumptions and dedup identity. Acceptance: stable signal corpus from frozen data and full reason trace.

### PHASE 5 — Risk engine
Turn portfolio, leverage, margin, stale-data, spread and kill-switch checks into one authoritative `RiskDecision` gate. Acceptance: mutation test proves no order can bypass it.

### PHASE 6 — Execution
Use venue-confirmed client IDs, product constraints, state transitions, partial-fill/bracket/reduce-only logic and retry idempotency. Acceptance: sandbox lifecycle drills including network interruption.

### PHASE 7 — Reconciliation
Make private order/fill/position state authoritative at startup and periodically; require manual resolution on divergence. Acceptance: restart, missed-event and manual-action drills pass on sandbox.

### PHASE 8 — Backtest / replay
Replay the same normalized source events, with calibrated execution/cost profiles and conservative ambiguity policy. Acceptance: reproducible, provenance-pinned results and paper/live parity measurement.

### PHASE 9 — Paper trading
Run a long monitored paper soak on real normalized data, with configured realistic costs and no unresolved data/reconciliation events. Acceptance: signed operational report, not just green unit tests.

### PHASE 10 — Live readiness
Start only with a sandbox/canary, strict notional caps, independent monitoring, alerting, and rollback. Acceptance: all P0/P1 issues closed and external exchange verification documented.

## CURRENT STATUS

**FUNCTIONAL BUT SIGNIFICANTLY BROKEN**

### Top 10 problems

1. Ticker-mark candles falsely stand in for OHLCV and use zero volume.
2. Order flow/footprint/DOM is absent from the active runtime.
3. Costs/slippage default to zero.
4. Delta credentials require emergency rotation and history cleanup.
5. Live exchange behaviour is only fake-tested.
6. Paper metadata fabricates `SPOT`/precision.
7. Live is single-symbol while paper is multi-symbol.
8. Options are metadata, not a tradable option system.
9. Exposure defaults can reach 25x unresolved notional/equity.
10. Full suite cannot be verified from the documented venv.

### What must not be changed

Do not weaken `LiveSafetyGate`, remove the risk revalidation, replace conservative intrabar policy with optimistic outcomes, silently substitute market data, or promote research/simulation code to production.

### What can be safely optimized

After correctness gates: redundant deque/list conversions, debug-only logging, repeated indicator work, and test/runtime startup wiring.  Do not optimize strategy calculations before data truth and execution semantics are corrected.

### External exchange verification required

Delta private/public schemas, signatures, product mappings, contract constraints, fees/funding, bracket/reduce-only semantics, partial fills, rate limits, real WebSocket recovery, and sandbox reconciliation.
