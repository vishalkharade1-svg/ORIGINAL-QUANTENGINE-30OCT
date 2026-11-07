# ============================================================
# QuantEngine
# PROJECT MANIFEST
# ============================================================

Architecture Version : 1.0.3

Status : ACTIVE

Last Updated : Sprint 8 (Phase 6C: canonical setup identity + multi-symbol scanning, STATUS 111; Phase 6D: real-time multi-symbol subscriptions, STATUS 112; Phase 6E: real-time closed-candle integration, paper mode, STATUS 113; Phase 7: breakout directional asymmetry research, STATUS 114; Phase 7E: real-data out-of-sample causal validation, STATUS 115; Phase 8: portfolio risk & capital coordination, STATUS 116; Phase 8B: shared portfolio capital & allocation, STATUS 117; Phase 9A-9O: research readback + experiment stack, STATUS 118-132; Phase 9P: completion & production-readiness audit + milestone 9P-a: canonical multi-symbol RealTimeEngine wired into main.py via core/runtime/paper_main.py, STATUS 133; Phase 9P-b: account profit factor / expectancy reporting from the canonical completed-trade ledger, STATUS 134; Phase 9P-c: canonical runtime analytics / account reporting attach-point, STATUS 135; Phase 9P-d: live liquidity / history provider plumbing feeding the canonical 6B eligibility cascade, STATUS 136; Phase 9P-e: provider-universe live smoke / verification harness, STATUS 137; Phase 9P-f: paper control & monitoring API, STATUS 138; Phase 9P-g: production PAPER entrypoint integration, STATUS 139; Phase 9P-h: lightweight desktop control client, STATUS 140; Phase 9P-i: integration & operational hardening / runbook, STATUS 141)

============================================================

This document is the single source of truth for the
entire QuantEngine architecture.

Every production file MUST appear here.

No production file may exist without registration.

============================================================

# STATUS

Draft
Stable
Production Ready
Deprecated

============================================================
CONFIGURATION
============================================================

config/settings.py

Status
Production Ready

Purpose

Global project configuration.

Consumes

None

Produces

Settings

Dependencies

None

Tests

N/A

------------------------------------------------------------

config/secrets.py

Status

REMOVED -- this file never existed in the repository (no
live importer; Phase 12 audit confirmed absent). Listed
here in error since Sprint 8. Secrets live ONLY in the
operator environment (.env, untracked) -- never in source.
See Phase 12 addendum.

============================================================
DATA
============================================================

data/historical_loader.py

Status

Stable

Purpose

Loads historical candles.

Consumes

Exchange API

Produces

Candles

------------------------------------------------------------

data/websocket_client.py

Status

Stable

Purpose

Live market feed.

Consumes

Delta Exchange

Produces

Ticker
MarketState
Candle Events

------------------------------------------------------------

data/candle_builder.py

Status

Stable

Purpose

Converts ticks into candles.

Produces

Completed Candle

============================================================
CORE
============================================================

core/market_state.py

Status

Stable

Purpose

Current market snapshot.

Owner

Market Data Layer

============================================================
EVENTS
============================================================

core/events/event.py

Status

Production Ready

Purpose

Base Event

------------------------------------------------------------

core/events/candle_event.py

Status

Stable

Purpose

Completed candle event.

------------------------------------------------------------

core/events/event_bus.py

Status

Stable

Purpose

Dispatches events.

------------------------------------------------------------

core/events/event_dispatcher.py

Status

Stable

Purpose

Queue implementation.

------------------------------------------------------------

core/events/event_types.py

Status

Production Ready

Purpose

System event registry.

============================================================
PIPELINE
============================================================

core/pipeline/pipeline_context.py

Status

Stable

Purpose

Shared pipeline state.

Owner

Pipeline

------------------------------------------------------------

core/pipeline/institutional_pipeline.py

Status

Stable

Purpose

Runs institutional pipeline.

============================================================
INDICATORS
============================================================

core/indicators/indicator_engine.py

Status

Stable

Purpose

Calculates indicators.

Produces

IndicatorCache

------------------------------------------------------------

core/indicators/indicator_cache.py

Status

Stable

Purpose

Stores indicator results.

------------------------------------------------------------

EMA

ATR

ADX

RSI

Status

Stable

============================================================
MARKET ANALYSIS
============================================================

TrendEngine

MarketStructureEngine

LiquidityPoolEngine

LiquidityTargetEngine

DisplacementScanner

FVGScanner

OrderBlockScanner

Status

Stable

============================================================
STRATEGY
============================================================

RegimeEngine

TradeSetupBuilder

DecisionEngine

Status

Stable

============================================================
EXECUTION
============================================================

ExecutionEngine

Status

Stable (STATUS 101: feeds the decision batch through the shared
EconomicSetupRegistry.observe() chokepoint -- economic dedup
(identical fingerprint suppression + near-identical clustering)
happens BEFORE the batch cap, so MAX_PENDING_ORDERS is spent on
independent ideas -- then emits the ranked batch as
context.execution_signals -- top MAX_PENDING_ORDERS by score,
tie-broken by registration order, capped by the registry's
remaining pending slots, skipping every already-ordered setup --
with context.execution_signal as the best of the batch for legacy
consumers. Clears the execution signal the moment its chosen setup
already has a registry order, so a setup can never be
emit-processed twice)

Purpose

Creates execution signals.

------------------------------------------------------------

OrderRegistry

Status

Active (core/execution/order_registry.py -- STATUS 100; the
persistent cross-mode source of truth for ONE SETUP ID == ONE
PRIMARY ORDER == ONE TRADE. Lives on the shared PipelineContext;
create(bar) stamps the bar-anchored eligibility window
(eligible_from_bar = created_bar + ENTRY_DELAY_BARS; expires_at_bar
= eligible_from_bar + MAX_WAIT_BARS), advance(bar) EXPIRES only on
the expiry bar, invalidate() terminalizes a thesis break as
INVALIDATED, mark_filled() mints order_id + trade_id and consumes
a PENDING order exactly once. Lifecycle NEW -> PENDING -> FILLED |
INVALIDATED | CANCELLED | REJECTED | EXPIRED)

Purpose

Lifecycle source of truth for primary orders.

------------------------------------------------------------

EconomicSetupRegistry

Status

Active (core/setup/economic_setup_registry.py -- STATUS 101; the
persistent economic-identity layer sitting on the shared
PipelineContext beside order_registry. observe(setups,
order_registry, bar) runs every candle as the ExecutionEngine
chokepoint BEFORE the pending-slot cap: drops structurally
already-ordered setups, suppresses fingerprints already live as
PENDING, collapses identical-fingerprint candidates to the
highest-ranked canonical, clusters near-identical zones (entry +
stop + target each within tolerance = max(ECONOMIC_TICK_SIZE x
ECONOMIC_CLUSTER_TICKS, price x ECONOMIC_CLUSTER_PCT, ATR x
ECONOMIC_CLUSTER_ATR_FRACTION) -- no hard-coded BTC points), and
ranks canonicals deterministically (-score, -confidence,
-liquidity_alignment, -rr, -observed_bar, structural_id ascending).
Duplicates carry is_economic_duplicate + economic_canonical_id.
Session state: re-created on reset(), NOT cleared by reset_cycle().
Ranking delta vs the DecisionEngine: this registry predicts the
ECONOMIC redundancy of adjacent setup discoveries -- one market
idea == one pending slot)

Purpose

One economic idea == one execution slot (dedup + clustering).

============================================================
SIMULATION
============================================================

TradeSimulator

Status

Active (core/backtesting/trade_simulator.py -- canonical
single-position fill + SL/TP engine shared by Backtest, Paper
and Live; applies the PositionManager's quantity hygiene at
open_trade for every mode)

Purpose

Simulates trades.

------------------------------------------------------------

PositionManager

Status

Active (core/risk/position_manager.py -- STATUS 98; pure
order refinement + read-only position snapshots, keep NO state
of its own; enforced at the TradeSimulator.open_trade choke
point)

------------------------------------------------------------

Portfolio

Status

Active (risk/portfolio_risk.py -- STATUS 95; core/risk/portfolio.py
-- STATUS 116). The legacy risk/portfolio_risk.py SHARED manager
remains the backtest-only wired manager (dollar-risk pool + position
count + default-off allocation caps). Phase 8 promotes the portfolio
gate to a first-class core layer: core/risk/portfolio.py::
PortfolioRiskManager is a drop-in SUPERSET of the legacy
surface (can_open / register_trade / close_trade / current_risk /
open_positions / open_by_symbol / equity / reset) so PortfolioBacktester
works verbatim, AND adds the order-aware surface (order_allows /
register_open / release_closed) now wired into BOTH regimes -- backtest
(PortfolioBacktester) AND live/paper (RealTimeEngine/PaperRuntime/
BrokerEngine). Cardinal invariant: the layer GATES an otherwise-valid
trade but NEVER mutates the setup's entry/stop/target/direction/strategy
logic (order_allows is a pure decision; register_open / release_closed
are bookkeeping). Optional disabled-by-default caps: max_positions /
max_portfolio_risk (absolute) / max_total_exposure_pct /
max_per_symbol_notional / max_directional_risk_pct /
max_correlated_risk_pct / max_daily_loss_pct / equity /
correlation_groups. Default neutrality: no caps => always allows.
reset() per run(). -- STATUS 117 (Phase 8B): shared
capital-lifecycle foundation -- core/risk/capital.py::SharedCapital
(reservation-based equity envelope: equity / reserved / available;
can_reserve pure decision, reserve/release/cancel bookkeeping),
core/risk/portfolio_state.py::PortfolioState + CapitalCandidate
(unified state: shared capital + risk budget + directional/
correlated/per-symbol/total-exposure caps + reservation ledger;
can_accept pure decision, reserve/release/cancel lifecycle),
core/risk/allocator.py::CapitalAllocator + AllocationResult
(DELIBERATELY deterministic, no ranking). PortfolioBacktester and
RealTimeEngine gained optional portfolio_state=None; when provided
the per-symbol gate/release run through the SHARED state lifecycle
so backtest AND paper/live consume the same shared capital (parity);
None default is UNCHANGED. Phase 7E NO-GO and Phase 8 gate unchanged.

============================================================
BACKTESTING
============================================================

backtesting/backtester.py

Status

Active (canonical single-symbol engine; -- STATUS 101: the pending
order pass now runs EVERY candle -- open position or not -- with
eligible-only lifetime excursion roll (min_low_since_creation /
max_high_since_creation / bars_pending; the creation candle
contributes nothing), invalidation on a structural stop breach
BEFORE the fill check, exactly one fill when low <= entry <= high,
then advance() to expire on the expiry bar; ORDER_FILLED /
ORDER_EXPIRED / ORDER_INVALIDATED diagnostics carry the bar
metadata, ORDER_EXPIRED with the full Phase 4E excursion window +
entry_distance_from_nearest_price. Ledger metrics:
pending_orders_average / pending_orders_max). -- STATUS 102
(Phase 4F): after the expiry pass every candle it runs
economic_registry.sync_lifecycles + entry_tracker.advance() (both
no-ops when absent), the fill gate is entry-mode-aware (an order
whose entry_mode is not in ACTIVE_ENTRY_MODES stays PARKED -- fills
refused, excursions + invalidation still roll), and the max-pending
metric is explained by pending_orders_max_bar +
pending_orders_max_directions (per-direction breakdown at the max
bar). Model towards MARKET_CONFIRMATION via a config flip only.

Purpose

Institutional replay engine.

------------------------------------------------------------

portfolio_backtester.py

Status

Active (multi-symbol driver -- STATUS 95)

Purpose

Runs one canonical Backtester per symbol across a multi-symbol
history dict; wires the shared PortfolioRiskManager in as each
engine's portfolio_gate / portfolio_release hook.

------------------------------------------------------------

logger.py

Status

Draft

Purpose

Backtest logging.

============================================================
OPTIMIZATION
============================================================

OptimizationEngine

Status

Planned

============================================================
SMART MONEY PRO
============================================================

WyckoffEngine

Status

Planned

------------------------------------------------------------

FibonacciEngine

Status

Planned

------------------------------------------------------------

GannEngine

Status

Planned

------------------------------------------------------------

FootprintEngine

Status

Planned

------------------------------------------------------------

VolumeProfileEngine

Status

Planned

============================================================
AI
============================================================

AIEngine

Status

Planned

============================================================
LIVE TRADING
============================================================

PaperTradingEngine

Status

Active (core/paper_trading -- STATUS 92)

------------------------------------------------------------

BrokerEngine

Status

Active (core/live -- STATUS 93; live placement dry-run by
default, LIVE_EXECUTE=1 + Delta API keys to arm)

============================================================
PERFORMANCE ANALYTICS
============================================================

PerformanceAnalytics

Status

Active (core/analytics -- STATUS 94; consumes the shared
TradeRegistry + Account from Backtest/Paper/Live)

============================================================
PERFORMANCE DASHBOARD
============================================================

PerformanceDashboard

Status

Active (core/dashboard -- STATUS 96; pure display layer over
the shared PerformanceReport -- render, ASCII equity curve,
trades table, CSV export)

============================================================
VALIDATION LAYER
============================================================

WalkForwardTester

Status

Active (core/validation/walk_forward.py -- STATUS 97; rolling
out-of-sample windows over the canonical Backtester with
train-window candidate selection by the shared analytics report)

------------------------------------------------------------

MonteCarloSimulator

Status

Active (core/validation/monte_carlo.py -- STATUS 97; seeded
bootstrap resampling of the closed-trade PnL sequence:
profit / drawdown / survival distributions)

------------------------------------------------------------

StrategyOptimizer

Status

Active (core/validation/optimizer.py -- STATUS 97; cartesian
parameter-grid sweep ranked by PerformanceAnalytics metrics)

============================================================
PHASE 4F (STATUS 102): ENTRY FEASIBILITY / RETRACEMENT /
MULTI-MODE ENTRY
===========================================================

EntryFeasibility

Status

Active (core/setup/entry_feasibility.py -- STATUS 102; measures
|entry - creation price| on four axes -- absolute / percent of
price / ATR_14 multiples / ticks -- and classifies IMMEDIATE /
NEAR / RETRACE / DEEP_RETRACE / TOO_FAR via configurable
ATR-normalized thresholds; pure function + snapshot dataclass;
consumed by TradeSetupBuilder (stamp) and EntryTracker (record))

EntryTracker

Status

Active (core/setup/entry_tracker.py -- STATUS 102; persistent
per-structural_id diagnostic record of what price actually did
after the creating candle: retracement toward entry, touch
(low <= entry <= high), bars until nearest approach / touch,
target-direction continuation, distance remaining at terminal,
MISSED_CONTINUATION; FILLED/INVALIDATED freeze, EXPIRED snapshot
then full-window roll; report() at ALL / BULLISH / BEARISH;
self-gates on ENABLE_ENTRY_DIAGNOSTICS -- no-leak proven)

EntryMode

Status

Active (core/execution/entry_mode.py -- STATUS 108; the PHASE 5C
Entry Model Router. select_entry_mode honors the setup's carried
entry_mode else routes configured_entry_mode(); AUTO / undeclared
modes RAISE EntryModeRouterError (never a silent fallback);
active_entry_modes() collapses only empty config to LIMIT_RETEST.
entry_model.py is the canonical vocabulary (Limit / MarketConfirm /
BreakoutContinuation) re-exported through entry_feasibility. Since
STATUS 105 / Phase 5D the configured production default is
BREAKOUT_CONTINUATION)

ExecutionComparisonMode

Status

Active (core/validation/execution_comparison.py -- STATUS 108; PHASE
5D: per-mode ISOLATED execution comparison. Same market data / risk /
fees / slippage executed once per mode, each in its OWN
pipeline + simulator + backtester; reports funnel + executed trade
ledger + PerformanceAnalytics metrics + fees / slippage per
independent run -- research shadows are never blended into the live
ledger)

Phase 5D field flow (STATUS 108)

Config (config/risk_settings.py): ENTRY_MODE = "BREAKOUT_CONTINUATION",
ACTIVE_ENTRY_MODES = ("BREAKOUT_CONTINUATION",) -- BREAKOUT is the
deliberately selected canonical production default; LIMIT_RETEST
remains the mode-less baseline channel and a selectable comparison
mode. Backtester step 4a: MARKET_CONFIRMATION fills only on the
canonical reach-and-close-beyond trigger; a mode-less legacy order is
anchored to the LIMIT_RETEST channel, never re-routed to the
configured ENTRY_MODE.

Instrument

Status

Active (core/registry/instrument.py -- STATUS 109, PHASE 6A; the
canonical exchange-agnostic instrument record: instrument_id /
symbol / exchange / product_type / underlying_asset / quote_asset /
expiry_time / strike_price / option_type / tick_size / quantity_step /
minimum_quantity / trading_enabled / state / metadata; round_price /
round_quantity / valid / valid_precision / to_dict / from_dict.
Discovery hands THIS object downstream -- never raw Delta JSON)

ProductDiscovery

Status

Active (data/delta/product_client.py + product_normalizer.py +
product_discovery.py -- STATUS 109, PHASE 6A; DYNAMIC product
discovery from Delta /v2/products through an INJECTABLE transport
(FakeTransport in tests, zero network). Normalizer maps real payloads
(lowercase contract_type via product_type_from_delta, asset dicts,
safe numeric coercion, is_delisted/is_disabled/is_unlisted -> ->
trading_enabled) to canonical Instruments; refresh_instrument_registry
runs discover -> registry.upsert -> mark_present -> save and reports
discovered / newly_listed / delisted / total_catalog. DISCOVER
EVERYTHING -- no hardcoded symbols; the eligibility layer decides)

InstrumentRegistry

Status

Active (core/registry/instrument_registry.py -- STATUS 109, PHASE 6A;
persistent JSON catalog + lifecycle. FIRST sighting -> NEWLY_LISTED
candidate; repeat with changed economics re-validates; DELISTED
reappearing product re-lists as candidate; unchanged NEWLY_LISTED ->
ACTIVE once sighted again; mark_present confirms prior-pass sightings
and DELISTs what vanished (graceful, never deleted); mark_eligible /
mark_ineligible / executable() gate state; repeat upserts PRESERVE
lifecycle state)

ProductTypes

Status

Active (core/registry/product_types.py -- STATUS 109, PHASE 6A;
canonical product type vocabulary SPOT / PERPETUAL / FUTURE /
CALL_OPTION / PUT_OPTION / UNKNOWN + lifecycle states NEWLY_LISTED /
ACTIVE / ELIGIBLE / INELIGIBLE / DELISTED; only EXECUTABLE_STATES
reach execution; product_type_from_delta maps the Delta contract types)

Phase 6A discovery field flow (STATUS 109)

Flow: ProductClient.fetch() (injectable transport) ->
DeltaProductNormalizer -> canonical Instrument ->
InstrumentRegistry.upsert (NEWLY_LISTED on first sighting, ACTIVE on
a later confirmed pass, DELISTED when absent) -> persistent JSON
save -> InstrumentEligibility gates before any instrument may reach
execution. A newly listed product is picked up by the NEXT discovery
pass with zero restart. Full suite 549/549 OK, compileall clean.

UniversePolicy

Status

Active (core/universe/universe_policy.py -- STATUS 110, PHASE 6B;
declared eligibility thresholds: min_quote_volume_24h (None removes
the bound but never the DATA requirement) + min_history_bars (None =
history gate off; e.g. 300 for the 1m lookback window). Explicit and
narrow by default: a misconfigured manager degrades to an EMPTY
universe, never a silent everything-goes catalog)

UniverseManager

Status

Active (core/universe/universe_manager.py -- STATUS 110, PHASE 6B;
runs the full gate cascade over registry.discoverable() with
INJECTABLE liquidity + history providers; NEWLY_LISTED single
sightings -> NOT_CONFIRMED (never eligible same pass); DELISTED can
never re-enter the universe; every verdict is WRITTEN BACK to the
registry (ELIGIBLE / INELIGIBLE + reason; mark_eligible clears the
reason); no provider / no data -> empty universe; executable_symbols()
is the Phase 6C scanning input; refresh() = discovery heartbeat +
eligibility cascade. Uses `registry if registry is not None` -- an
empty InstrumentRegistry is FALSY via __len__)

MarketUniverse

Status

Active (core/universe/market_universe.py -- STATUS 110, PHASE 6B;
the immutable ELIGIBLE cut: policy / instruments / timeframe /
captured_at / reasons; symbols / get_by_symbol / contains / count /
symbols_text. Scanning and execution consume THIS snapshot -- a
discovered-but-not-eligible instrument never reaches it)

RefreshScheduler

Status

Active (core/universe/refresh_scheduler.py -- STATUS 110, PHASE 6B;
left alone discovery + eligibility on a cadence with an injectable
clock: due / run_if_due / force_refresh; interval <= 0 always due;
a failed discovery pass is recorded (errors) and the loop continues
with last_universe / last_summary intact)

InstrumentEligibility

Status

Active (core/registry/eligibility.py -- STATUS 110, PHASE 6B;
evidence-based trading gates extended: the liquidity gate
(NO_LIQUIDITY_DATA / LOW_LIQUIDITY) plus a history/lookback gate
(NO_HISTORY_DATA / INSUFFICIENT_HISTORY) plus the confirmation gate
(NOT_CONFIRMED first-sighting denials); envelope is instrument.valid)

CanonicalSetupIdentity

Status

Active (core/identity/instrument_identity.py -- STATUS 111, PHASE 6C;
the namespaced setup identity {exchange}:{instrument_id}:{timeframe}:
{direction}:{strategy}:{setup_id}, built ONCE by TradeSetupBuilder at
setup creation and carried VERBATIM onto OrderIntent and Trade --
never reconstructed downstream. build_setup_identity validates
non-empty segments + BULLISH/BEARISH (IdentityError on malformed);
split_setup_identity round-trips with the setup_id suffix preserved
verbatim. Legacy single-symbol harnesses without an
exchange/instrument_id keep canonical_id == "" and are
byte-identical)

SymbolPipeline

Status

Active (core/scanning/symbol_pipeline.py -- STATUS 111, PHASE 6C;
ONE instrument, ONE fully isolated pipeline per scan: fresh
PipelineContext + MarketState (exchange + instrument_id),
injectable world factory (default InstitutionalPipeline), fresh
EventBus / TradeSimulator / Backtester -- zero shared mutable state.
data_source contract get_candles(symbol, timeframe, limit);
accumulates every candle's setups plus the cumulative decision /
order / trade registries into the per-symbol result; NO_DATA_SOURCE /
NO_DATA -> SKIPPED)

MultiSymbolScanner

Status

Active (core/scanning/multi_symbol_scanner.py -- STATUS 111, PHASE 6C;
consumes ONLY the eligible cut via MarketUniverse.eligible_instruments()
/ registry executable() / any iterable -- never a hardcoded symbol
list; deterministic (exchange, instrument_id, symbol) ordering
independent of universe insertion order; per-symbol failure isolation
(caught -> FAILED + error, neighbours continue); empty universe
degrades to a clean empty result)

MultiSymbolScanResult

Status

Active (core/scanning/scan_result.py -- STATUS 111, PHASE 6C;
ScanStatus SUCCESS/SKIPPED/FAILED; SymbolScanResult holds
setups / decisions / orders / trades / pipeline; MultiSymbolScanResult
aggregates scanned / successful / skipped / failed / symbols / flat
setups-decisions-orders-trades slices / for_symbol() / summary())

Identity flow fields (STATUS 111)

Config: SetupCandidate.canonical_id / OrderIntent.canonical_id /
Trade.canonical_id (default "" -- additive, backward compatible);
MarketState.exchange / MarketState.instrument_id (default "").

Flow: TradeSetupBuilder stamps candidate.canonical_id once
(core.identity.instrument_identity) -> RiskEngine copies it VERBATIM
onto OrderIntent -> TradeSimulator.open_trade copies it VERBATIM onto
Trade -> registries / scan results / analytics read the SAME string
end to end.

MultiSymbolSubscriptionManager

Status

Active (data/realtime/subscription_manager.py -- STATUS 112, PHASE 6D;
owns ONE shared multiplexed transport (Delta subscribes many symbols
on a single websocket) + one SubscriptionWorker per eligible
instrument; sync() consumes MarketUniverse.eligible_instruments() or
any iterable and diffs desired - current -> ADD / REMOVE / KEEP in
place (no restart required; FAILED workers re-added next pass);
poll() fires clock-deadline reconnects + STALE transitions with
per-worker failure isolation; stop_all() releases the connection so a
later sync rebuilds it)

SubscriptionWorker

Status

Active (data/realtime/stream_worker.py -- STATUS 112, PHASE 6D; one
logical subscription, explicit lifecycle state machine STOPPED /
CONNECTING / LIVE / RECONNECTING / STALE / FAILED -- no implicit
booleans; event-driven and non-blocking, retries scheduled on
clock deadlines so one failing stream can NEVER stall another;
forming ticks keep the subscription fresh, closed candles pass the
integrity gate once and in order)

CandleRouter

Status

Active (data/realtime/candle_router.py -- STATUS 112, PHASE 6D;
per-symbol closed-candle integrity gate: delivered AT MOST once, in
chronological order; FORMING candles (closed=False) never reach
strategy logic; the bounded seen-timestamp memory survives reconnect
so a replayed candle is a duplicate and an older one is out-of-order
-- BREAKOUT triggers stay causally aligned to NEXT_BAR_OPEN)

DeltaSubscriptionStream

Status

Active (data/delta/delta_subscription_stream.py -- STATUS 112, PHASE 6D;
production multiplexed transport following Delta's websocket model:
one connection, one channels payload listing every desired symbol,
per-symbol CandleBuilder rolls closed candles on bucket boundaries,
throttled forming heartbeats, on_down() fanned to every route;
websockets sync client imported lazily -- offline tests use a fake)

Realtime subscription states (STATUS 112)

Config: first-class lifecycle states instead of is_connected booleans;
StreamHealth max_stale_seconds (30.0 default) decides STALE;
ReconnectPolicy exponential backoff defaults base 1.0 / factor 2.0 /
max 60.0 / optional max_attempts budget (None = retry forever).

Flow: universe refresh snapshot (Phase 6B scheduler) -> sync() ->
multiplexed transport subscribe/unsubscribe per symbol -> forming
ticks (health only) + closed candles (integrity gate) -> consumer
callback (Phase 6E wires this into SymbolPipeline). Candle gains
`closed` (FORMING/CLOSED provenance) and `symbol` delivery scoping,
both defaulted so the backtest candle shape is unchanged.

Tests: tests/test_realtime.py (32 tests, stdlib-only, FakeTransport +
FakeClock offline). Full suite 626/626 green, compileall clean.
Commit: independent Phase 6D milestone; Phase 7 BREAKOUT directional
research stays separate.

===========================================================
PHASE 6E -- REAL-TIME CLOSED-CANDLE INTEGRATION, PAPER MODE
(STATUS 113)
===========================================================

RealTimeEngine

Status

Active (core/runtime/realtime_engine.py -- STATUS 113, PHASE 6E;
the orchestrator wiring 6B universe refresh + 6D closed-candle
delivery into the frozen 6C SymbolPipeline, paper-only: refresh
scheduler pulse -> registry.reconcile + subscription manager sync
-> manager.poll() -> _on_closed_candle -> symbol resolves to the
eligible instrument record -> (exchange, instrument_id) identity
key -> that runtime only. Identity-key routing can never leak a
BTC candle into the ETH pipeline)

PipelineRegistry

Status

Active (core/runtime/pipeline_registry.py -- STATUS 113, PHASE 6E;
stable per-instrument pipeline ownership keyed by
instrument_identity_key(exchange, instrument_id). reconcile()
diffs the eligible cut -> ADD / RETAIN / RETIRE; retired pipelines
move to a readable snapshot. A retained instrument keeps the SAME
SymbolPipeline object (continuous structural window) across
refreshes -- never a rebuild; new instruments get a fresh isolated
pipeline via the injectable world_factory)

PaperRuntime

Status

Active (core/runtime/paper_runtime.py -- STATUS 113, PHASE 6E;
the per-instrument continuous paper unit. Owns ONE frozen
SymbolPipeline and drives it through the canonical BrokerEngine
with dry_run=True (world on_candle -> RiskEngine OrderIntent ->
TradeSimulator paper fill -> SL/TP exits -> TradeRegistry paper
ledger). Execution boundary = the injected PaperExecutionAdapter;
canonical_id (Phase 6C) flows setup -> order -> trade verbatim)

ExecutionPort

Status

Active (core/runtime/execution_port.py -- STATUS 113, PHASE 6E;
the ONE paper/live execution seam. ExecutionPort protocol +
PaperExecutionAdapter: execute() audits the would-be intent and
returns the paper envelope; every live-only op (fetch/cancel/
balance/positions) raises PaperOnlyError so a paper port can never
place real orders. The future LiveDeltaExecutionAdapter is the only
other implementation, swapped at this boundary)

=====

PHASE 9P-a -- PAPER MAIN BRIDGE (main.py multi-symbol runtime)
(STATUS 133)
=====

PaperMainBridge

Status

Active (core/runtime/paper_main.py -- STATUS 133, PHASE 9P-a; the
canonical PAPER-mode startup bridge between the CLI entry point
(main.py) and the Phase 6E multi-symbol RealTimeEngine runtime.
Before this the entry point drove only the legacy single-symbol
PaperTradingEngine / websocket_client path. build_paper_engine()
assembles the same RealTimeEngine -> PipelineRegistry -> PaperRuntime
-> BrokerEngine (dry_run) stack that test_runtime_integration
exercises; every collaborator (universe_manager, transport_factory,
world_factory, clock) is injectable so offline tests drive the
identical build path. ExplicitSymbolUniverseManager supplies the
eligible cut from settings.SYMBOLS (UNIVERSE="explicit", the
documented fallback until live liquidity/history providers exist);
discovery is a no-op and the RefreshScheduler still re-polls the
shared manager on cadence. tick() = one non-blocking poll step;
run_paper_forever() = the blocking loop for main.py. Paper-only by
construction: dry_run=True through the PaperExecutionAdapter, zero
exchange writes, no auto-promotion)

Tests: tests/test_paper_main_runtime.py (8 tests, stdlib-only,
FakeClock + FakeTransport + scripted world offline): explicit
universe eligible cut (+ blank filtering); multi-symbol assembly with
paper-only dry_run; identity routing isolation (BTC/ETH; a BTC
candle never mutates the ETH pipeline); forming candle never
delivered; unknown symbol unrouted without crashing; tick() drives
one poll step; PaperOnlyError on live port ops. Full canonical suite
tests/ = 1370 passed (baseline 1362 + 8), compileall clean.

=====

PHASE 9P-b -- ACCOUNT PROFIT FACTOR / EXPECTANCY REPORTING
(STATUS 134)
=====

ProfitFactorExpectancyReporting

Status

Canonical, account/analytics layer (core/analytics/performance.py +
core/risk/account_state.py -- STATUS 134, PHASE 9P-b). Closes the
reporting gap: profit factor (Gross Profits / Gross Losses) and
expectancy (mean completed-trade net P&L) are now reported
mathematically correctly from the canonical completed-trade ledger,
with a SINGLE canonical calculation and NO duplicate accounting
surface.

Canonical source: core.backtesting.trade_registry.TradeRegistry
closed trades (status == "CLOSED"); Trade.pnl is the per-trade NET
P&L (gross minus commission minus slippage, as booked by the
simulator). Completed = closed; open positions, rejected / expired /
unfilled orders and unrealized P&L are excluded (the analytics layer
already filters by status == "CLOSED").

Canonical calculation: PerformanceAnalytics / PerformanceReport (the
same report surface the dashboard consumes) -- NOT a second
accounting system and NOT a second metric implementation. The
account (core/risk/account.py) is a counter-only accumulation (it
never retains per-trade outcomes), so it cannot derive profit factor
or expectancy; the dead declared AccountState.profit_factor /
AccountState.expectancy fields (never computed, never read) were
REMOVED to eliminate a misleading duplicate surface.

Definitions:

    winning trade     net P&L > 0
    losing trade      net P&L < 0
    breakeven trade   net P&L == 0 (NEITHER win NOR loss)
    gross profit      sum of positive net P&L
    gross loss        absolute sum of negative net P&L
    profit factor     gross profit / gross loss
                      (inf when gross profit > 0 and no gross loss;
                      0.0 when no gross profit, incl. all-breakeven)
    expectancy        net profit / total  (mean over ALL completed
                      trades incl. breakevens in the denominator)

Breakeven trades are counted in `total` (and thus the expectancy
divisor) but excluded from win/loss counts, gross profit / gross
loss, win/loss streaks, and per-direction win rates (phase 9P-b
correctness fix; pre-9P-b classified pnl==0 as a win).

Det. edge cases: empty -> missing-value 0.0 (project convention);
all-win -> +inf; all-loss -> 0.0; all-breakeven -> 0.0; negative
expectancy preserved; breakeven never a win or loss; open positions
excluded; deterministic idempotent report; costs honored (net pnl).

Tests: tests/test_account_profit_factor_9pb.py (13 tests,
stdlib-only): task fixture [+100,+200,-50,-100,0] -> gross_profit
300, gross_loss 150, profit_factor 2.0, total 5, wins 2, losses 2,
breakeven 1, net 150, expectancy 30 (breakeven neutral in denominator,
excluded from gross); all-win -> inf; all-loss -> 0.0; breakeven-only
-> 0.0 neither win nor loss; empty -> 0.0; negative expectancy;
breakeven-not-a-win regression; open positions excluded; deterministic
repeat; costs honored on net pnl; reconcile with booked account;
AccountState exposes NO duplicate profit_factor/expectancy; metrics()
dict includes breakeven. Full canonical suite tests/ = 1383 passed
(baseline 1370 + 13), compileall clean. Research-only expectancy/
profit-factor references (9H/9K/9L/9M researcher, readability, ML,
breakout asymmetry) are deliberately untouched -- they are research
layer, not account reporting.

=====

PHASE 9P-c -- CANONICAL RUNTIME ANALYTICS / ACCOUNT REPORTING
ATTACH-POINT (STATUS 135)
=====

RuntimeAnalyticsAttachPoint

Status

Canonical, runtime/analytics layer (core/runtime/paper_runtime.py +
core/runtime/realtime_engine.py -- STATUS 135, PHASE 9P-c). Gives
the running PAPER runtime a deterministic, canonical way to obtain
its performance report with NO second accounting system, NO second
Profit-Factor calculation, NO second expectancy calculation, and NO
restored account-level duplicate surface. The canonical calculation
remains PerformanceAnalytics / PerformanceReport (the SAME object
surface the backtest / validation / dashboard consume).

Attach-points (both PURE delegation -- nothing is recomputed):

    PaperRuntime.report()
        -> PerformanceAnalytics.analyze(runtime.account,
                                         runtime.ledger)
        The runtime already owns both canonical inputs: its Account
        (counter-only state holder) and its TradeRegistry ledger
        (PAPER_TRADE_REGISTRY). Smallest architecture-compatible
        change.

    RealTimeEngine.performance(symbol=None)
        symbol given  -> the single active runtime's report for that
                         symbol (None for an unknown symbol, matching
                         the universe-routing semantics).
        symbol None   -> aggregate PerformanceReport across ALL
                         active runtimes' completed trades, with a
                         shared starting balance (sum of the per-
                         runtime starting balances) so final equity
                         reconciles across the whole PAPER book.

Canonical data source: TradeRegistry CLOSED trades only (status ==
"CLOSED"), Trade.pnl = net per-trade P&L (gross minus commission
minus slippage). Data-source integrity: open positions, unrealized
P&L, and rejected / expired / unfilled / cancelled orders never reach
the ledger -- the BrokerEngine drops a failed route before booking,
and the analytics closed-only filter excludes everything open.
Breakeven trades remain NEITHER win NOR loss (the 9P-b classifiers).

Real-time semantics: report is generated ON-DEMAND only (never in
the candle path, so it never blocks the event loop), deterministic
for the same completed-trade state, and reflects a newly closed
trade on the next access. No caching (do not optimize prematurely);
no race conditions introduced because generation is a pure read of
the ledger.

Account / AccountState stay counter-only: profit_factor and
expectancy are NOT restored to AccountState; they live solely on the
PerformanceReport. Dashboard/API/mobile: no new dashboard or API
built in this milestone -- these accessors are the small reusable
internal reporting attachment point for future consumers (mobile
will view performance through this canonical report without coupling
the analytics layer to a mobile implementation).

Tests: tests/test_runtime_report_9pc.py (12 tests, stdlib-only,
offline multi-symbol engine + direct PaperRuntime): runtime canonical
report identity; completed-trade-only; open trades excluded;
rejected/expired/unfilled never in the ledger; breakeven neutral; PF
+ expectancy identity with canonical analytics; report updates after
a close; deterministic repeat; account state stays counter-only;
per-symbol isolation on a BTC+ETH engine; aggregate over all symbols
(shared starting balance reconciles final equity); empty aggregate;
deterministic aggregate. Full canonical suite tests/ = 1395 passed
(baseline 1383 + 12), compileall clean.

=====

PHASE 9P-d -- LIVE LIQUIDITY / HISTORY PROVIDER PLUMBING
(STATUS 136)
=====

DeltaLiquidityProvider / DeltaHistoryProvider

Status

Canonical, universe-provider layer (core/universe/liquidity_provider.py
+ core/universe/history_provider.py + core/runtime/paper_main.py +
config/settings.py -- STATUS 136, PHASE 9P-d). Fills the ONE genuinely
missing gap in the Phase 6B universe architecture: real provider-backed
eligibility data for the canonical UniverseManager. Before this phase,
UniverseManager accepted injectable `liquidity_provider` /
`history_provider` (duck-typed: quote_volume_24h(symbol)->float|None,
history_bars(symbol,timeframe)->int|None) but NO real provider existed;
the PAPER runtime fell back to UNIVERSE="explicit" (settings.SYMBOLS).
Implemented ONLY the actually-missing plumbing -- no new universe
architecture, no second manager, no re-rewrite of MarketUniverse /
UniverseManager / SymbolPipeline / subscriptions: the providers FEED
the existing eligibility cascade.

DeltaLiquidityProvider
    Fetches the REAL Delta /v2/tickers payload once per refresh (one
    REST call, not one per symbol -- a multi-symbol eligibility pass
    hits the exchange once), caching a symbol -> turnover map. Each
    symbol's `turnover_usd` (24h USD turnover) maps to the canonical
    quote_volume_24h input. Data honesty: missing / empty / unparseable
    / zero turnover -> None -> the cascade DENIES (NO_LIQUIDITY_DATA);
    missing data is NEVER assumed liquid, and a transport failure on a
    symbol returns None for that symbol (the loop never dies, the gate
    still denies). Transport / fetch injectable for offline tests.

DeltaHistoryProvider
    Reports the COUNT of bars available via the existing real
    DeltaHistory.candles() (real /v2/history/candles) over a bounded
    lookback window (PROVIDER_HISTORY_LOOKBACK_DAYS, default 7).
    Returns None on a failure so missing history DENIES
    (NO_HISTORY_DATA) -- never "assume sufficient history". History
    client injectable for offline tests.

Config (config/settings.py)
    MIN_QUOTE_VOLUME_24H / MIN_HISTORY_BARS (operator thresholds;
    an unconfigured liquidity threshold still REQUIRES a measured
    figure -- a numeric bound is optional, a data requirement is not;
    invalid values fail fast), PROVIDER_HISTORY_LOOKBACK_DAYS, and the
    UNIVERSE="provider" selector.

Runtime wiring (core/runtime/paper_main.py)
    build_provider_universe_manager() assembles the CANONICAL
    UniverseManager + InstrumentRegistry + real providers;
    build_paper_engine(universe_mode=...) selects the provider path
    when UNIVERSE=="provider" while PRESERVING the explicit fallback
    (the default). Providers run in the SAME synchronous cadence-based
    universe refresh path as the existing product discovery
    (RefreshScheduler -> manager.build_universe), NOT in the real-time
    candle delivery path -- no blocking HTTP added to the live event
    loop.

Proof: tests/test_provider_plumbing_9pd.py (28 tests, stdlib-only,
offline with mocked Delta responses + fake providers over the real
InstrumentRegistry / InstrumentEligibility): the critical acceptance
path (REAL/NORMALIZED PROVIDER DATA -> canonical UniverseManager ->
eligibility cascade -> ELIGIBLE multi-symbol set); real /v2/tickers
endpoint + turnover parsing; empty/zero/invalid turnover -> None;
missing symbol -> None; transport failure -> None (no raise); history
bar-count + lookback passthrough; error -> None; threshold coercion
(invalid raises, NaN/inf rejected); provider policy (unconfigured ->
requires_history False); explicit fallback default preserved; provider
mode builds canonical manager with injected fakes. LIVE EXCHANGE
VERIFIED (separate from code verification): /v2/tickers turnover_usd
present for liquid symbols (e.g. BTCUSDT) and empty for inactive;
/v2/history/candles returns 1440 1m bars for BTCUSDT over 1 day
(2026-09-03). Full canonical suite tests/ = 1423 passed (baseline
1395 + 28) + compileall clean.

Phase 9P-e: provider-universe live smoke / verification harness
(core/runtime/provider_universe_smoke.py + tests/test_provider_universe_smoke_9pe.py
-- STATUS 137). Reproducible, read-only/PAPER-only live-exchange smoke
harness for the 9P-d provider-universe path: real Delta data -> the
CANONICAL 6B eligible universe -> subscriptions -> PAPER runtime, with
safe bounded shutdown and a structured report. Reuses ONLY the
canonical UniverseManager / InstrumentRegistry / eligibility cascade /
SymbolPipeline / subscriptions / PaperRuntime / the single liquidity+
history provider architecture + build_paper_engine (UNIVERSE="provider");
provider-selection is always `provider`, never accidental `explicit`.
Harness primes DeltaLiquidityProvider.refresh() before each
build_universe() (quote_volume_24h reads the snapshot map), surfaces
RefreshScheduler discovery errors into report.errors (NetworkUnavailable
-> NETWORK, else API), distinguishes DATA_UNAVAILABLE from
ELIGIBILITY_REJECTED, and defaults bounded/terminating (engine.stop()
closes transport + sets the stop event; pump loop is daemon and breaks
on stop -- no hanging WebSocket).

CLI: `python -m core.runtime.provider_universe_smoke [--timeframe X]
[--polls N] [--interval S] [--passes N(default 2)] [--symbols A,B,...]
[--min-volume F] [--min-bars I]`. Fresh registry needs >= 2 passes to
graduate NEWLY_LISTED -> ACTIVE via the Phase 6A confirmation state
machine. Discovery is filtered to the chosen symbols in-memory (one
real /v2/products call -- no per-symbol REST explosion; history remains
per-symbol as required).

Proof: tests/test_provider_universe_smoke_9pe.py (17 tests, stdlib-only,
offline with mock transport/fakes over the real cascade): mode provider
required/selected; real-provider construction; live-data success
(eligible cut -> 3 runtimes/pipelines/subscriptions); network/API/
history failure classification; empty eligible universe reported
(exit 3); classify_reason; PAPER-only guard (LIVE_MODE without
PAPER_MODE refuses); clean shutdown (WS closed, no dangling workers);
structured deterministic report; fresh-registry confirmation (1 pass ->
0 eligible NOT_CONFIRMED; 2 passes -> graduated eligible); LOW_LIQUIDITY
rejected cut vs AVAILABLE bucket separation. LIVE EXCHANGE VERIFIED on
2026-09-03 against real api.delta.exchange REST + WebSocket: default
1m 3 symbols -> 3/3 ELIGIBLE -> 3 runtimes/pipelines/subscribed,
paper_only=true, clean ~13s bounded exit; --min-volume 5000000
--min-bars 1000 -> 0 eligible, ALL LOW_LIQUIDITY from REAL turnover
(thresholds NOT weakened to manufacture a cut; DATA AVAILABLE kept
distinct from ELIGIBILITY REJECTED); --min-volume 100000 --min-bars 300
-> mixed cut BTCUSDT/ETHUSDT/SOLUSDT ELIGIBLE vs DOGEUSDT LOW_LIQUIDITY
(real sub-100K turnover). Runtime Safety: PAPER-only (paper_only=true),
LIVE_MODE-without-PAPER guard + bounded CLI; no live orders; empty
(0 eligible) universe reported as such (exit 3), not manufactured as
success. Full canonical suite tests/ = 1440 passed (baseline 1423 +
17) + compileall clean.

===== Phase 9P-f (Paper Control & Monitoring API -- STATUS 138)
Read-only-first Control & Monitoring HTTP API + a safe PAPER-only
control seam over the canonical RealTimeEngine, enforcing
API -> Command/Query -> Existing Runtime (the engine stays the single
source of truth; the API adds no strategy/risk/order/live logic).
stdlib-only (no new dependency).
core/runtime/lifecycle.py: EngineLifecycle -- thin control manager
owning a daemon control poll thread + RLock-serialized state model
(STOPPED/STARTING/RUNNING/STOPPING/FAILED) + commands allowlist
{start, stop, restart, emergency_stop}; emergency_stop is a
highest-priority local PAPER shutdown, strictly idempotent (2nd call
= zero duplicate shutdown work, no error, stays STOPPED); start
failure -> FAILED (recoverable); bounded joins.
core/monitoring/api_server.py: stdlib ThreadingHTTPServer hard-bound
to 127.0.0.1, bearer-token constant-time hmac.compare_digest auth,
fail-closed when tokenless; GET read endpoints /health /universe
/subscriptions /runtimes /market /signals /positions /orders
/account /risk /performance /errors (delegate to existing
statuses()/performance()/portfolio.snapshot()/runtime.state()/
subscriptions); POST /control with _assert_paper_capable (refuses
LIVE-mode or any non-dry_run runtime); no GET mutates state; API
never calls poll() directly.
core/monitoring/service.py (enabled/config_token/start_api/fail-closed
ControlApiConfigError); config/settings.py knobs CONTROL_API_ENABLED /
TOKEN / HOST / PORT / POLL_SECONDS.
Runtime Safety: PAPER-only (refuses non-dry_run), token + localhost,
fail-closed, no determinism/lifecycle change to engines, no
live/order path. No certificate/TLS code exists anywhere in the repo
and 9P-f does no outbound TLS (no verify=False/CERT_NONE workarounds).
Proof: tests/test_lifecycle_9pf.py (19), test_api_server_9pf.py (19),
test_monitoring_service_9pf.py (3) = 48 over the real
ThreadingHTTPServer on 127.0.0.1 ephemeral port. Full suite tests/ =
1488 passed (baseline 1440 + 48) + compileall clean.
Commit: independent Phase 9P-f paper control and monitoring API
milestone (04739eb).

===== Phase 9P-g (Production PAPER Entrypoint Integration -- STATUS 139)
Narrow runtime-entrypoint integration wiring core/monitoring/service
into the production application: one coherent startup model,
main.py -> PAPER application -> (Control API | EngineLifecycle ->
RealTimeEngine -> PaperRuntime).
core/runtime/lifecycle.py: EngineLifecycle.wait([timeout]) blocking
seam (returns current state; releases when the lifecycle leaves a
running state) via a _stopped_event wired into start() (cleared) /
stop()/emergency_stop()/start-failure (set).
core/monitoring/service.py: _active_server duplicate-server guard
(refuses a second start while one is running), stop_api(server), and
the production entrypoint helpers start_paper_service() ->
(lifecycle, server), block_until_stopped() (waits then shuts down
BOTH lifecycle and server), run_paper_with_monitoring() (drive engine
via EngineLifecycle + gated API + block + clean shutdown).
main.py: the PAPER path calls run_paper_with_monitoring(engine) in
place of the blocking run_paper_forever(engine) (removed the explicit
engine.refresh(), since lifecycle.start() -> engine.start() ->
refresh()); the API is enabled ONLY when explicitly
CONTROL_API_ENABLED=true + token, so the disabled default preserves
the pre-9P-g behaviour exactly; run_paper_forever kept for
direct-loop callers.
Runtime Safety: localhost + bearer token + PAPER-only preserved; no
live API, no mobile UI, no strategy/risk/order API; API and PAPER
runtime share the SAME authoritative engine; shutdown stops both
cleanly.
Proof: tests/test_paper_entrypoint_9pg.py (4) drives the real
acceptance path offline (real build_paper_engine with fakes + real
HTTP server -> GET /health /universe /performance -> POST
/control/stop -> blocker drains, server+lifecycle+engine stopped),
plus API-disabled-default (lifecycle runs, NO HTTP server);
test_monitoring_service_9pf.py + test_lifecycle_9pf.py grow 6 more.
Full suite tests/ = 1498 passed (baseline 1488 + 10) + compileall
clean.
Commit: independent Phase 9P-g production PAPER entrypoint integration
milestone.

===== Phase 9P-h (Lightweight Desktop Control Client -- STATUS 140)
Thin, read-only-first Tkinter/ttk desktop control & monitoring
terminal over the existing Control API. The UI is a renderer/
controller only: it consumes GET reads and issues the four
allowlisted POST /control lifecycle commands -- it NEVER imports
engine internals, recomputes strategy/risk/position/order/
performance, constructs orders, or touches an exchange. stdlib-only,
zero new dependencies (requirements.txt unchanged; tkinter is
bundled with CPython).
core/client/ package, launched `python -m core.client.app` (or
`python -m core.client`):
config.py           host/port/token/poll; defaults 127.0.0.1:8787;
                    token from QENGINE_CLIENT_TOKEN /
                    CONTROL_API_TOKEN env (never hardcoded);
                    as_dict() never exposes the token.
http_client.py      ApiClient GET/POST with bearer auth via urllib,
                    timeouts, typed errors (Authentication/
                    Connection/Timeout/Server/BadResponse/
                    ControlRejected); ReconnectingClient tracks
                    connected/disconnected.
poller.py           single daemon background worker; one coordinated
                    read cycle per interval with a no-overlap guard;
                    per-endpoint error isolation; clean stop via
                    Event; results to a thread-safe queue.
controller.py       pure display logic mapping CycleResult snapshots
                    to rows; only write path is ControlPath verbs
                    start/stop/restart/emergency_stop against the
                    real POST /control {"command": ...} contract.
app.py              DesktopClient: header connection/engine status,
                    Dashboard / Universe / Market / Trading(Signals,
                    Positions, Orders, Account, Risk) / Performance /
                    Logs tabs, control bar with confirmations (incl.
                    a stronger Emergency Stop confirmation), poll ->
                    queue -> root.after() drain (HTTP never on the
                    Tkinter thread), DISCONNECTED -> CONNECTED
                    auto-reconnect with no engine restart.
Engine isolation: client imports only stdlib + its own core.client
modules (grep-verified: no core.runtime/engine/strategy/risk/
execution/exchanges/pipeline, no TradeRegistry/BrokerEngine/
RealTimeEngine). No secrets in source; token only in the
Authorization header, never logged/displayed/in URLs. No invented
endpoints (consumes exactly the 9P-f GETs + POST /control). Closing
the UI stops ONLY the poller -- it never stops the engine.
Proof: tests/test_client_9ph.py (25, stdlib-only, in-process fake
http.server Control API, no network): HTTP client GET/POST/bearer-
header/timeout/401/500/malformed-JSON/unreachable; ControlPath exact
/control+command body; ReconnectingClient connected/disconnected;
config defaults/custom/from_env/no-token-in-as_dict; poller results-
reach-queue / connection-failure-no-crash / clean stop; controller
dashboard/universe/empty-universe/performance-report/positions/
errors-"no-secret". Offline runtime smoke verified (fake engine +
REAL Control API + REAL ApiClient/Poller): health RUNNING, universe
BTCUSDT/ETHUSDT, performance rows, POST /control stop -> STOPPED +
engine.started False. Full suite tests/ = 1523 passed (baseline
1498 + 25) + full compileall clean. Known limitations: presentation-
only (no charting/advanced analytics/order-entry/live/credential
management -- out of 9P-h scope); tkinter needs a display (logic is
display-free, headlessly tested); single universe view; no mobile/
web client yet (future clients can consume the SAME API).
Commit: independent Phase 9P-h lightweight desktop control client
milestone.

===== Phase 9P-i (Integration & Operational Hardening / Runbook -- STATUS 141) =====

No-new-feature phase proving and documenting the complete existing PAPER
stack: fresh env -> engine -> Control API -> desktop client.

Changed:
  core/client/app.py      -- fixed invalid escape sequence `\ ` in the
      module docstring (a SyntaxWarning emitted on every import/compile
      detected by `python -m compileall .`); re-drew the ASCII art so
      the package compiles warning-free.

New:
  tests/test_integration_9pi.py  -- 12 offline, committed tests closing
      the full loop with the REAL core.client package (ApiClient/Poller/
      ReconnectingClient/ControlPath/controller renders) against the REAL
      Control API + REAL EngineLifecycle + a canonical fake PAPER engine
      over localhost. Covers: real reads (health/universe/runtimes/
      performance); poller coordinated CycleResult; controller renders
      real server data verbatim (never recomputed); all four lifecycle
      verbs end-to-end through the real client; ReconnectingClient probe;
      client-teardown-does-NOT-stop-the-engine; API disabled runs
      lifecycle without HTTP; API enabled without token fails closed;
      bearer token never appears in any response body or error string.
  tests/test_client_isolation_9pi.py -- 2 committed import-isolation
      regression tests: a FRESH-interpreter subprocess imports every
      core/client module and asserts the resulting core.* import set is
      ONLY core/client (+ the stdlib support boundary) -- never runtime/
      live/risk/execution/exchanges/pipeline/research/backtesting/
      analytics/registry/universe/events etc., and no engine objects
      (TradeRegistry/BrokerEngine/RealTimeEngine/PipelineContext/...).
  docs/RUNBOOK.md -- complete operational run guide (env setup, install,
      exact env-var configuration for PAPER local / PAPER+Delta / Control
      API / client, start engine, enable API, start client, verify, safe
      shutdown, emergency stop, reconnection, troubleshooting table,
      security notes, localhost-only multi-machine note, verification
      checklist).

Audits (re-verified, no defects found requiring code change): canonical
PAPER path is singular (paper_main -> RealTimeEngine -> PaperRuntime ->
BrokerEngine dry_run); Control API disabled-by-default / localhost-only /
constant-time bearer / fail-closed / read-only except four allowlisted
PAPER verbs; EngineLifecycle state model + idempotency; PAPER-only safety
(no live-order path, API asserts paper-capable before control); provider
universe cascade (missing/zero data DENIES, never fabricated eligible);
no hardcoded secrets in source (keys/token env-only, never logged/URLs/
reports).

Full canonical suite tests/ = 1535 passed (1523 baseline + 12 new);
compileall clean AND warning-free; git diff --check clean; tracked .pyc
restored; requirements.txt unchanged (zero new runtime dependencies);
tests independent/offline/deterministic (no Delta/Internet/credentials/
Tk-display dependency).
Commit: independent Phase 9P-i integration & operational hardening /
runbook milestone.

=====

Flow: eligible cut (Phase 6B) -> PipelineRegistry ADD/RETAIN/RETIRE
-> manager sync (Phase 6D) -> closed candle -> identity-key routing
-> PaperRuntime.process_closed_candle -> paper fill + lifecycle
(SIGNAL / PAPER_ORDER_CREATED / PENDING / FILLED / OPEN_POSITION /
TARGET-STOP-EXIT / CLOSED_TRADE -> paper ledger).

Tests: tests/test_runtime_integration.py (6 tests, stdlib-only,
scripted world + FakeTransport + FakeClock offline): eligible-to-
subscription-to-pipeline flow; dynamic BTC+ETH -> BTC+SOL (BTC
object-retained, ETH retired + unsubscribed, SOL created); candle
routing isolation (BTC candle never mutates the ETH pipeline);
duplicate protection end-to-end incl. the reconnect boundary
(replay before AND after reconnect delivered at most once);
deterministic paper execution (canonical_id preserved, entry model
preserved, PnL booked) winner + defensive stop loss; PaperOnlyError
live-op guarantee. Full suite 632/632 green, compileall clean.
Commit: independent Phase 6E milestone; Phase 7 BREAKOUT directional
research stays separate.

===========================================================
PHASE 7 -- BREAKOUT DIRECTIONAL ASYMMETRY RESEARCH
(STATUS 114)
===========================================================

BreakoutAsymmetryResearch

Status

Active, RESEARCH-ONLY (core/research/breakout_asymmetry/ -- STATUS
114, PHASE 7; the harness that establishes WHY the same
BREAKOUT_CONTINUATION architecture behaves differently per
direction. DELIBERATELY SEVERED from production: consumes ONLY
frozen CausalValidationState records and emits only evidence,
never a strategy change; nothing in the package is imported by any
engine. Submodules: features.py (16-axis FeatureExtractor 7A),
outcomes.py (OutcomeClassifier 7B buckets + conservative WIN/LOSS +
MFE/MAE/payoff/PF/expectancy/win-rate/MAE-DD), origins.py
(OriginDecomposition 7C with E geometry contributing MFE + MAE +
RR), counterfactual.py (7D EXECUTION-HELD-CONSTANT), report.py
(AsymmetryReport verify/hypothesis/summary/dump), demo.py +
results/phase7_report.json on a synthetic mirror dataset)

Tests: tests/test_breakout_asymmetry.py (18 tests, stdlib-only,
offline synthetic causal data): dataset load + merge; outcome
bucketing + conservative win/loss; PF/expectancy/win-rate/MFE/MAE/
payoff/MAE-DD math; origin decomposition truth (E geometry
dominates, F held constant); counterfactual; full report assembly +
verify()/summary()/dump() round-trip; fidelity that the described
bullish-vs-bearish asymmetry shape decomposes to the correct origin.
Full suite 650/650 green, compileall clean.
Commit: independent Phase 7 research milestone -- evidence points to
setup/geometry (origin E) as the dominant cause, NOT execution (F
held constant); a directional BREAKOUT_CONTINUATION BULLISH/BEARISH
policy (7E) is NOT introduced in this phase -- it remains gated
behind out-of-sample validation on real (non-synthetic) causal data.

===========================================================
PHASE 7E -- REAL-DATA OUT-OF-SAMPLE CAUSAL VALIDATION
(STATUS 115)
===========================================================

Phase7eRealDataValidation

Status

Active, RESEARCH-ONLY (core/research/breakout_asymmetry/realdata.py --
STATUS 115, PHASE 7E; the milestone that answers the single question
gating any directional policy: does the SYNTHETIC directional
hypothesis (bearish-strong / bullish-weak, the shape the user baseline
reported) survive on UNSEEN REAL causal data? DELIBERATELY SEVERED and
IMMUTABLE-BASELINE: consumes ONLY the FROZEN production causal pipeline
(the d3eb2c8 state; PipelineContext + InstitutionalPipeline + EventBus
+ TradeSimulator + Backtester.run() with ENTRY_MODE pinned to
BREAKOUT_CONTINUATION, then restored verbatim) and emits ONLY evidence
-- no threshold, no strategy, no frozen code changes. Submodules:
fetch_and_cache_oos_candles (fetches ~10,000 real BTCUSDT 1m bars live
from Delta via HistoricalLoader, caches the pinned OOS window to the
git-ignored data/history/BTCUSDT_1m_oos.json for reproducible offline
re-runs, returns chronological Candle objects), run_oos_causal_pipeline
(replays real candles through the identical frozen path), _verdict (the
7E.9 A/B/C gate: tests the SIGN of the directional profit signal --
win-rate AND expectancy -- NOT a bare geometric |asymmetry|, so a real
gap that is absent or REVERSED reads NO-GO/outcome B rather than a
spurious GO), run_7e + main (builds the AsymmetryReport over the real
states, renders the verdict, dumps results/phase7e_real_oos_report.json
with provenance metadata). report.py::verify() reconciled to the FULL
classified population (692 triggers == 692 outcomes == 692 bucketed)
with never_entered (18) surfaced as a diagnostic.

Tests: tests/test_breakout_asymmetry_7e.py (8 tests, stdlib-only;
offline except the cached-sample run): directional gate GO when the
hypothesis reproduces / NO-GO when REVERSED (bullish stronger -- the
real result) / NO-GO when near-symmetric / INCONCLUSIVE when one
direction is absent or the sample is too thin; OOS cache round-trip +
chronological order; run_oos_causal_pipeline config restoration.
Full suite 658/658 green, compileall clean.

REAL RESULT (10,000 bars / 692 settled states: 268 BULLISH / 424
BEARISH): both directions PROFITABLE; bullish slightly STRONGER (win
79.2% vs 74.5%, PF 1.32 vs 1.23, expectancy +0.067R vs +0.059R); the
bearish-strong / bullish-weak hypothesis is REJECTED (win-rate gap
-4.7pp below the 5.0pp floor, reversed sign) -> 7E VERDICT NO-GO
(outcome B). The 7E gate is NOT crossed -- NO directional
BREAKOUT_CONTINUATION BULLISH/BEARISH branch; baseline d3eb2c8
immutable; no production code modified.

===========================================================
PHASE 8 -- PORTFOLIO RISK & CAPITAL COORDINATION (core layer)
(STATUS 116)
===========================================================

PortfolioRiskManagerCore

Status

Active (core/risk/portfolio.py -- STATUS 116, PHASE 8). The
portfolio risk gate is promoted from a backtest-only adapter
(risk/portfolio_risk.py) to a FIRST-CLASS core layer that now
governs BOTH the backtest path (PortfolioBacktester) AND the
live/paper path (RealTimeEngine / PaperRuntime / BrokerEngine),
so ONE shared portfolio policy coordinates aggregate exposure /
concurrency / directional / correlated / drawdown / risk-budget /
capital allocation across every symbol in both regimes.

CARDINAL INVARIANT (carried forward verbatim): the portfolio
layer GATES (accept/decline) an otherwise-valid trade but NEVER
mutates the setup's entry / stop / target / direction / strategy
logic. order_allows(order) is a PURE DECISION (inspects order +
current portfolio state, sets last_reason on a False verdict,
never touches order/ledger/strategy); register_open(order) /
release_closed(trade) are BOOKKEEPING. Flow:
SymbolPipeline -> Strategy decision -> RiskEngine -> OrderIntent
-> Portfolio Risk Gate -> Execution.

Wiring (this phase):
  * BrokerEngine gained optional portfolio_gate(order) /
    portfolio_release(closed_trade) hooks; the gate is consulted
    in _route() after order resolution and BEFORE open_trade /
    execute; a False verdict returns WITHOUT routing (logged
    PORTFOLIO_GATE_DECLINED); release fires in both _book_closed
    (paper) and _book_live_close (live).
  * PaperRuntime threads the gate/release into its BrokerEngine.
  * RealTimeEngine gained portfolio_manager=None (defaults to a
    default-NEUTRAL manager); every PaperRuntime shares the SAME
    _portfolio_gate / _portfolio_release closures; .portfolio
    exposes it.
  * PortfolioBacktester continues to work verbatim (legacy
    duck-typed surface is a drop-in SUPERSET of risk/
    portfolio_risk.py) and can now accept the core manager.

Caps (optional, disabled by default): max_positions;
max_portfolio_risk (ABSOLUTE aggregate-R budget); equity-scaled %
max_total_exposure_pct / max_directional_risk_pct /
max_correlated_risk_pct / max_daily_loss_pct; absolute-currency
max_per_symbol_notional; equity basis; correlation_groups. Default
neutrality: no caps => always allows.

Tests: tests/test_portfolio_risk_core.py (17, stdlib-only; default
neutrality, order_allows pure-decision invariant, last_reason, each
dimensional cap, release-free + PnL fold + direction/correlation
ledgers, reset determinism, legacy primitive surface drives
PortfolioBacktester with the core manager, live/paper shared-gate
integration). Full suite 675/675 green, compileall clean. Phase 7E
NO-GO stands -- no directional policy introduced.

===========================================================
PHASE 8B -- SHARED PORTFOLIO CAPITAL & ALLOCATION
(STATUS 117)
===========================================================

SharedPortfolioCapital

Status

Active (core/risk/capital.py SharedCapital -- STATUS 117, PHASE 8B;
the reservation-based shared capital foundation). Infra phase, NOT
strategy optimization. equity = basis + realized PnL;
reserved_capital = sum of live reservations; available_capital =
deployment_cap - reserved_capital. can_reserve(amount) is a PURE
DECISION (last_reason = insufficient_capital on decline, never
mutates); reserve / release / cancel are BOOKKEEPING (cancel returns
capital with NO realized PnL -- the failed-execution-after-reservation
path).

PortfolioState

Status

Active (core/risk/portfolio_state.py -- STATUS 117, PHASE 8B; the
UNIFIED portfolio state + reservation ledger). Owns the SharedCapital
envelope, the risk budget (max_portfolio_risk, absolute R),
equity-scaled total / directional / correlated % caps, absolute
per-symbol capital, correlation_groups, and the reservation ledger
(rid -> {symbol, direction, group, risk, capital}). CapitalCandidate
is pure data built from primitives or from an OrderIntent via
from_order(). can_accept(candidate) is the PURE decision gate
(risk_budget / insufficient_capital / total_exposure /
per_symbol_capital / directional_limit / correlation_limit);
reserve(candidate) -> rid; release(rid, pnl) / cancel(rid) manage the
capital lifecycle (A reserve -> B reserve -> A closes -> release ->
C now allowed).

DeterministicCapitalAllocator

Status

Active (core/risk/allocator.py -- STATUS 117, PHASE 8B). DELIBERATELY
DETERMINISTIC allocation in strict input order with NO ranking (that
belongs to a later 8C / Confluence layer). Reproduces the canonical
example: equity $10,000 / max_portfolio_risk 2R -> BTC ACCEPT 0.8R /
ETH ACCEPT 0.7R / SOL REJECT-DEFER (2.4R > 2R, remaining 0.5R).

Wiring: PortfolioBacktester + RealTimeEngine gained optional
portfolio_state=None; when provided the per-symbol gate/release run
through the SHARED state lifecycle (can_accept + reserve on open;
release on close folding PnL into shared equity) so backtest AND
paper/live consume the same shared capital (byte-identical +10 PnL ->
10010 through both paths). None default is UNCHANGED. Phase 7E NO-GO
and Phase 8 gate unchanged.

Tests: tests/test_portfolio_capital_8b.py (20, stdlib-only). Full
suite 695/695 green, compileall clean. Confluence Engine (Phase 9)
built ON this foundation later -- Wyckoff/ML not yet, no
BREAKOUT/rules/7E modified.

Phase 4F field flow (STATUS 102)

Config (config/risk_settings.py): MAX_PENDING_ORDERS_TOTAL = 8,
MAX_PENDING_ORDERS_PER_SYMBOL = 8, MAX_PENDING_ORDERS_PER_DIRECTION
= 4, MAX_PENDING_ORDERS_PER_CLUSTER = 1, entry-feasibility ATR
thresholds IMMEDIATE 0.10 / NEAR 0.35 / RETRACE 0.75 / DEEP 1.50,
ENTRY_MODE = LIMIT_RETEST, ACTIVE_ENTRY_MODES = ("LIMIT_RETEST",),
ENTRY_TRACKING_WINDOW_BARS = 60, MISSED_CONTINUATION_TARGET_FRACTION
= 0.5, ENABLE_ENTRY_DIAGNOSTICS = True, REENTRY_COOLDOWN_BARS = 30.

Flow: EconomicSetupRegistry.observe (STATUS 101) ->
ExecutionEngine entry_tracker.track chokepoint ->
ExecutionEngine + RiskEngine per-direction pending budget ->
RiskEngine stamps entry_mode + feasibility class on OrderIntent ->
TradeSimulator carries entry_mode onto Trade ->
Backtester sync_lifecycles + entry_tracker.advance + mode-aware
fill gate every candle. EconomicSetupRegistry lifecycle ACTIVE /
COOLDOWN with mark_terminal / sync_lifecycles / reentry cooldown
suppression (FILLED clears, EXPIRED / INVALIDATED cooldown).

Tests: tests/test_entry_feasibility.py (17 tests, stdlib-only).
Full suite 412/412 green.

===========================================================
PHASE 4G (STATUS 103)
===========================================================

StructuralZoneFreshness

Status

Active (core/order_blocks/zone_freshness.py -- STATUS 103; PURE
at-creation helpers: freshness states + rank, entry-rejection
taxonomy + labels + conservative priority, timeframe-aware
max_order_block_age_bars, compute_zone_age (direct current - origin
measurement, never a counter), age_bucket, classify_freshness,
effective_zone_tolerance / zones_overlap (Phase 4E tolerance
formula), cluster_structural_zones (greedy, order-stable, stamps
cluster_id / is_canonical / canonical_zone_id), and
evaluate_entry_eligibility -> (structurally_valid, trade_eligible,
primary_reason, diagnostics). No function reads a bar after the
creating candle.)

ZoneEligibilityLog

Status

Active (core/setup/zone_eligibility.py -- STATUS 103; session-state
ledger on PipelineContext, first-appearance-per-structural_id dedup
identical to the EntryTracker; observe() records EVERY canonical
zone -- eligible or rejected -- with its at-creation age/freshness/
distance/reason; report() emits ENTRY ELIGIBILITY + ORDER BLOCK
FRESHNESS aggregates ALL / BULLISH / BEARISH. Diagnostic only:
nothing it stores is read by any engine.)

Phase 4G field flow (STATUS 103)

Config (config/risk_settings.py): MAX_ORDER_BLOCK_AGE_BARS = 500
(+ BY_TIMEFRAME override map), FRESH_ORDER_BLOCK_AGE_BARS = 5,
MAX_LIMIT_ENTRY_DISTANCE_ATR = 30.0, MIN_RISK_WIDTH_ATR = 0.10,
ENABLE_STRUCTURAL_CLUSTERING = True, MIN_ORDER_BLOCK_DISPLACEMENT =
50.0 and MAX_ORDER_BLOCK_TOUCHES = 3 (diagnostic-only thresholds).

Flow: OrderBlockScanner stamps age_bars / age_time_seconds /
origin_bar / created_bar / freshness / distance(+_atr) on every
emitted block (measured from the origin candle in the current
window); lifecycle sets last_tested bar/timestamp on each touch.
TradeSetupBuilder (ENABLE_STRUCTURAL_CLUSTERING=True) runs
cluster_structural_zones over active blocks BEFORE candidate
generation -- only canonical zones build candidates; each candidate
gets evaluate_entry_eligibility stamped (structurally_valid /
trade_eligible / entry_rejection_reason / zone_diagnostics) + the
zone snapshot (zone_age_bars / zone_freshness / zone_distance(+_atr)
/ zone_cluster_id / zone_canonical_zone_id / zone_is_canonical), and
zone_eligibility.observe() is called for every canonical candidate.
DecisionEngine rejects trade_eligible=False candidates outright
(SETUP_REJECTED reason=<entry_rejection_reason>, deduped per (reason,
fingerprint)); RiskEngine adds the defense-in-depth MIN_RISK_WIDTH_ATR
gate on every order-minting path. Tests/test_backtester.py prints the
ORDER BLOCK FRESHNESS REPORT + ENTRY ELIGIBILITY REPORT blocks.

Tests: tests/test_zone_freshness.py (19 tests, stdlib-only). Full
suite 431/431 green, compileall clean. Regression: 5000-bar
BEFORE/AFTER table in STATUS 103 (intended gate, no tuning).

===========================================================
PHASE 4G EXTENSION (STATUS 104)
===========================================================

EntryShadow

Status

Active (core/setup/entry_shadow.py -- STATUS 104; diagnostic-only
shadow comparison: on EVERY trade-eligible canonical setup it
measures what LIMIT_RETEST / MARKET_CONFIRMATION /
BREAKOUT_CONTINUATION would have done over the same post-creation
window (window = ENTRY_TRACKING_WINDOW_BARS 60, expiry = real
30-bar MAX_WAIT_BARS). ShadowFill + EntryShadowState dataclasses,
observe/advance/_roll/_settle/report. Trigger contract: LIMIT =
candle trades through E with the stop breach checked BEFORE the fill
(backtester step-3-before-step-4, invalidation beats a same-bar
fill); MARKET = reach E AND close beyond it (bull close >= E / bear
close <= E), entry at candle close -- can never fill a stop-ward
sweep closing on the wrong side; BREAKOUT = exceed E on the trade
side AND close beyond it (bull high > E and close > E / bear low < E
and close < E), anchored on the OB reference level E (OrderBlock.
entry) not a running creation-bar extreme; models trigger
independently; SHADOW_ENTRY_MODES gates which shadows are measured,
LIMIT_RETEST always measured. Resolution mirrors trade_simulator: SL
before TP per bar, same-bar both-hit = LOSS; MAE/MFE from the FIRST
bar AFTER the entry bar (entry bar excluded), capped at stop/target
on the resolution bar; untriggered models are never resolved;
_safe_div treats None as 0.0. Pure diagnostics -- nothing it stores
is read by any engine; no threshold changed, LIMIT_RETEST the sole
executable mode.)

Phase 4G extension field flow (STATUS 104)

Config (config/risk_settings.py): ENABLE_ENTRY_SHADOW = True,
SHADOW_ENTRY_MODES = ("MARKET_CONFIRMATION", "BREAKOUT_CONTINUATION")
(reuses MAX_WAIT_BARS = 30, ENTRY_TRACKING_WINDOW_BARS = 60,
MISSED_CONTINUATION_TARGET_FRACTION = 0.5).

Flow: PipelineContext owns the EntryShadow session state
(_new_entry_shadow factory + reset, lazy like every other session
state). TradeSetupBuilder calls shadow.observe() right beside
elig_log.observe() for every trade-eligible canonical candidate
(population == zone_eligibility trade_eligible by construction).
Backtester calls entry_shadow.advance(candle, bar, order_registry)
every candle beside entry_tracker.advance; order context
(order_id / created_bar / expires_at_bar) is attached once from the
registry; reached_within_expiry is decided at settle vs the real
expiry. Tests/test_backtester.py prints the ENTRY MODEL COMPARISON
REPORT blocks ALL / BULLISH / BEARISH (3-model table + ATR-distance
vs expiry buckets + correlation) gated on ENABLE_ENTRY_SHADOW.

Verification: tests/test_entry_shadow.py (20 tests, stdlib-only:
per-model triggers, invalidation-before-fill, bearish mirrors,
SL-before-TP same-bar, MFE/MAE caps, MAE excludes the entry bar,
UNRESOLVED settle, missed-continuation gap-runner, ATR-vs-expiry
buckets + negative correlation, default horizon, population ==
eligibility, order-context attach over a 63-candle world reaching
settle, SHADOW_ENTRY_MODES gating, byte-identical no-leak
fingerprints). Full suite 451/451 green, compileall clean.
Regression: 5000-bar table + ATR-vs-expiry analysis in STATUS 104
(verdict: retest reaches are rare and lose; distance in ATR is the
binding constraint, not expiry bars; nothing changed
execution-wise).

==========================================================
PHASE 4H (STATUS 105)
==========================================================

CausalValidator

Status

Active (core/setup/causal_validation.py -- STATUS 105; diagnostic-only
causal BREAKOUT_CONTINUATION validation: re-runs the STATUS 104
hypothesis under RULE 1 freeze-at-creation, RULE 2 trigger-at-close
(bull high > E and close > E / bear low < E and close < E, decided from
only the trigger candle's range + close, stop breach checked BEFORE the
trigger), RULE 3 next-bar execution (entry at the OPEN of trigger + 1;
a last-in-window trigger counts as a trigger without an entry), RULE 4
deterministic intrabar SL/TP ambiguity (CONSERVATIVE stop-first =
primary / OPTIMISTIC / EXCLUDE, all rendered from one walk that always
records the CONSERVATIVE outcome + ambiguity flag). CausalValidator +
CausalValidationState + format_causal_report. Reports
(ALL/BULLISH/BEARISH): triggers / triggers-without-executable-next-bar /
fills / ambiguous trades / W-L-UNRESOLVED-EXCLUDED / win rate / profit
factor / gross P/L (R) / expectancy & average R / max drawdown (R and %)
/ avg bars to entry / MAE-MFE (ATR), plus the MARKET_CONFIRMATION
rejection-stage counters (candidates / rejected_structure /
rejected_trend / rejected_distance / rejected_volume /
rejected_orderflow / triggered). Pure diagnostics -- nothing it stores
is read by any engine and it produces NO order; no threshold changed,
LIMIT_RETEST the sole executable mode, BREAKOUT_CONTINUATION still a
shadow.)

Phase 4H field flow (STATUS 105)

Config (config/risk_settings.py): ENABLE_CAUSAL_VALIDATION = True,
INTRABAR_POLICY = "CONSERVATIVE" (reuses ENTRY_TRACKING_WINDOW_BARS =
60).

Flow: PipelineContext owns the CausalValidator session state
(_new_causal_validator factory + field + reset, lazy like every other
session state). TradeSetupBuilder calls validation.observe() right
beside shadow.observe() for every trade-eligible canonical candidate
(same population). Backtester calls causal_validation.advance(candle,
bar, order_registry) every candle beside entry_shadow.advance; order
context (order_id / created_bar / expires_at_bar) is attached once from
the registry. Tests/test_backtester.py prints the PHASE 4H CAUSAL
BREAKOUT VALIDATION blocks ALL / BULLISH / BEARISH gated on
ENABLE_CAUSAL_VALIDATION.

Verification: tests/test_causal_validation.py (32 tests, stdlib-only:
freeze under mutation, trigger contract, stop-breach-before-trigger,
next-bar open entry, gap-against entry executes, last-in-window
non-executable trigger, all three intrabar policies, EXCLUDE drops the
trade, excursion/R-multiple math, full report-math table, confirmation
partition invariant + co-existence, population dedup / eligibility /
order-context, ENABLE gating no-op, post-decision no-look-ahead).
Full suite 483/483 green, compileall clean. Regression: 5000-bar Phase
4H report in STATUS 105 (verdict: the breakout win rate survives strict
causal execution -- 292/304 filled at next-bar open, 238W/38L/16U,
86.2% win rate, PF 2.58, +0.217R expectancy, zero ambiguous intrabar
candles; MAE 21 ATR vs 1R risk warns of deep post-trigger countermoves;
MARKET_CONFIRMATION's 0 fills attributed 213 distance / 91 structure /
0 trend / 0 triggered; nothing changed execution-wise).

===========================================================
MOBILE
============================================================

Android Dashboard

Status

Planned

------------------------------------------------------------

iOS Dashboard

Status

Planned

Phase 9A -- Research Journal + Causal Opportunity Ledger (foundation)

Status

Active (core/research/journal/* -- STATUS 118). Infrastructure-only
(NOT AI/ML/strategy optimization). A durable, deterministic research
record of every market opportunity lifecycle (setup -> eligibility ->
order -> fill/expiry/invalidation -> trade -> close) as a pure
OBSERVER of the frozen engine. It NEVER alters a decision, order,
setup, risk or portfolio object.

Modules (live import surface):
  research_enums.py       -- Provenance (BACKTEST/PAPER/LIVE),
      SetupLifecycle, OrderLifecycle, Result, EntryReached, EventType
      (stable string contracts)
  research_event.py       -- deterministic immutable event, sequence +
      bar derived event_id (no random UUIDs)
  setup_record.py         -- observed setup facts incl. ALL verbatim
      rejection reasons (never a generic REJECTED)
  order_record.py         -- observed order lifecycle + excursion
      (min/max_high_since_creation, entry_distance_from_nearest_price,
      bars_pending, entry_reached)
  trade_record.py         -- observed outcome + R = pnl/risk_amount;
      MAE/MFE consumed from the authoritative CausalValidator (never
      fabricated)
  opportunity_record.py   -- immutable unified lifecycle view + resolved
      terminal outcome
  research_repository.py  -- append-safe stdlib storage, deterministic
      ordering by (exchange, instrument_id)
  research_journal.py     -- per-bar observer/reconciler (reads settled
      PipelineContext + TradeRegistry; fail-safe, never raises into
      trading; symbol-scoped keys)
  journal_query.py        -- read-only filters (provenance / entry_mode /
      rejection-reason / terminal-outcome / symbol / status / result)
  journal_summary.py      -- counts + breakdowns (reuses the
      authoritative WIN/LOSS/R/PnL language)

Wiring (all default-off, behaviour identical when None): Backtester
run(candles, journal=None); PortfolioBacktester run(history,
journal=None); PaperRuntime + RealTimeEngine journal=None (PAPER
provenance). The LIVE interface is prepared ONLY via
journal.on_bar_observed as the attach point; live trading is NOT
enabled. Explicit Provenance NEVER inferred from filenames.

Nothing this layer does changes any trading decision: it only
records observed facts. Counterfactual / simulation outcomes
(SimulatedTrade, CounterfactualOutcome, StrategyExperiment) are
SEPARATED and DEFERRED to later phases. NO-AI / NO-ML standing rule
holds -- this is pure fact-recording infrastructure. Phase 7E NO-GO
and 6C/6D/6E/7/8/8B frozen layers are untouched (only optional
journal params added).

------------------------------------------------------------

Phase 9B -- Deterministic Parameter Experimentation + Counterfactual
Opportunity Replay Lab

Status

Active (core/research/lab/* -- STATUS 119). Research / simulation
ONLY (NOT production optimization, NOT AI/ML). Adds the deterministic
machinery that answers, for an explicitly supplied configuration:
"what would have happened under a different RR / expiry /
entry-offset / entry-model / stop / target geometry?". It consumes
recorded OpportunityRecords + historical candles and NEVER feeds
experimental decisions back into production.

Modules (live import surface):
  provenance.py          -- LabProvenance: COUNTERFACTUAL / SIMULATED,
      distinct from the 9A BACKTEST/PAPER/LIVE provenance
  experiment_config.py   -- immutable frozen ExperimentConfig (entry
      model + params, stop_mode, target_mode, rr, expiry,
      changed_filters); never mutates production defaults
  simulated_trade.py     -- first-class SimulatedTrade, frozen,
      provenance === COUNTERFACTUAL, NEVER enters the TradeRegistry
  counterfactual.py      -- CounterfactualOutcome (one replay result;
      to_trade() materialization)
  opportunity_replay.py  -- causal candle-by-candle replay from the
      decision bar forward; stop-before-target exit ordering mirrors
      TradeSimulator; decision-time ATR reused from core/indicators/atr;
      no lookahead; MAE/MFE tracked from fill only
  entry_models.py        -- experimental LIMIT_RETEST /
      BREAKOUT_CONTINUATION / MARKET_CONFIRMATION entry semantics
  exit_models.py         -- EXISTING_STOP / ATR / CUSTOM stop +
      EXISTING_TARGET / FIXED_RR / ATR / CUSTOM target geometry
  evidence.py            -- immutable EvidenceSnapshot (real
      decision-time facts only; Wyckoff reserved, NOT fabricated)
  metrics.py             -- deterministic PF / win-rate / expectancy / R
      / drawdown over COUNTERFACTUAL trades only
  experiment_result.py   -- machine-readable ExperimentResult + human
      summary
  experiment_runner.py   -- batch replay; deterministic experiment_id =
      sha1(config params + baseline id), NO random UUIDs; per-opportunity
      fail-tolerance (error -> warning, never corrupts other runs)
  parameter_grid.py      -- THIN deterministic Cartesian sweep
      (itertools.product; caller insertion order; expiry_bars -> expiry
      alias; rr=[] -> zero; no overrides -> one baseline; unknown keys
      raise KeyError; base_config never mutated; fresh config per
      combination; no shared mutable state; NO opt-in optimization)
  recovery.py            -- opportunity recovery classification

Isolation: the lab reads OpportunityRecords + candles only. It never
writes the production TradeRegistry, Journal, PortfolioState, risk or
strategy configuration. No lookahead, no optimization selection, no
ML/AI. ParameterGrid only reports what happened under each explicitly
specified configuration -- automatic optimization is deferred to a
later research/AI layer. Phase 7E NO-GO and 6C/6D/6E/7/8/8B frozen
layers are untouched (the lab is fully additive; no production edits).

------------------------------------------------------------

Phase 9C -- Counterfactual Opportunity Simulator

Status

Active (core/research/counterfactual/* -- STATUS 120). Research ONLY
(NOT production optimization, NOT AI/ML). The deterministic
one-opportunity engine that answers, for an explicitly supplied
alternative configuration: "this trade was rejected / unfilled under
the baseline; what would have happened under this exact entry model /
RR / expiry / offset / stop / target?". It consumes the frozen
OpportunityRecords (9A) + historical candles and NEVER feeds any
experimental decision back into production.

Modules (live import surface):
  counterfactual_config.py   -- immutable CounterfactualConfig wrapping
      the deterministic 9B ExperimentConfig; explicit unknown-param
      rejection; unsupported entry model -> loud ValueError;
      outcome_bars outcome horizon (None == production TradeSimulator
      holding contract); deterministic identity = 9B experiment_id_for
      over merged params + outcome horizon + baseline (NO UUIDs);
      setup_view() hands EXPERIMENTAL levels to the canonical deciders
      without mutating any production/journal object
  opportunity_categories.py  -- deterministic 9A-fact-only
      classification: FILLED / REJECTED / MISSED_CONTINUATION /
      INVALIDATED / ENTRY_NOT_REACHED / NON_EVALUABLE (derived ONLY
      from terminal_outcome + verbatim rejection_reasons)
  opportunity_simulator.py   -- OpportunitySimulator: STRICT contract --
      explicit is-not-None source extraction (a present 0.0 is NOT
      missing); direction validation; geometry validation (finite,
      risk>0, stop/target on correct side) -> deterministic
      NON_EVALUABLE, never RR=0; CANONICAL entry routing through the
      frozen production deciders core/execution/entry_model
      .get_entry_model (LIMIT_RETEST / MARKET_CONFIRMATION /
      BREAKOUT_CONTINUATION) -- entry semantics NOT reimplemented
      (closes the 9B lab reimplementation gap); no-decidable mode ->
      NON_EVALUABLE + warning, never invented; entry window
      expiry-bounded; BREAKOUT next-bar-open fill with NO_EXECUTABLE_BAR
      distinct from ENTRY_NOT_REACHED; outcome walk within the EXPLICIT
      outcome_bars horizon including the fill bar (paper-engine parity);
      stop-before-target ordering mirrors TradeSimulator.update; R / PnL
      / MAE / MFE from the ACTUAL fill (risk = |fill - stop|, LOSS ==
      -1R) matching the canonical _r_multiple contract; bars_in_trade
      counts the fill bar; source OpportunityRecord never mutated
  simulated_trade.py / counterfactual_outcome.py -- documented REUSE
      shims for the frozen 9B SimulatedTrade / CounterfactualOutcome
      (provenance === COUNTERFACTUAL)
  counterfactual_runner.py   -- CounterfactualRunner: run_config /
      run_configs / grid; native 9B ParameterGrid integration, every
      combination evaluated independently, deterministic order and
      unique ids, base config preserved, never blended

Isolation: the simulator reads OpportunityRecords + candles only. Every
successful simulation materializes to a COUNTERFACTUAL SimulatedTrade
that NEVER enters TradeRegistry / Account / PortfolioState /
SharedCapital / paper / live / production journal; the source
OpportunityRecord is unchanged after 1 and after many simulations.
No lookahead, no optimization selection, no ML/AI -- opportunity
recovery (REJECTED TOO_FAR_FROM_MARKET / INSUFFICIENT_RISK_WIDTH /
STALE_ZONE / unfilled LIMIT / missed continuation) is measured only,
never pushed to production. Phase 7E NO-GO and 6C/6D/6E/7/8/8B frozen
layers are untouched (fully additive; no production edits).

------------------------------------------------------------

Phase 9D -- Experiment Matrix + Research Analyzer

Status

Active (core/research/analyzer/* -- STATUS 121). Research analysis
ONLY (NOT production optimization, NOT ML/AI). The ANALYZER (not an
optimizer): it consumes the frozen OpportunityRecords (9A) and the
deterministic 9C CounterfactualOutcome collections and produces --
for every explicitly supplied alternative configuration -- the
evidence that answers WHAT HAPPENED, WHAT COULD HAVE HAPPENED, WHY THE
OPPORTUNITY WAS MISSED, WHICH ALTERNATIVE CONFIGURATION RECOVERED IT,
HOW MANY addition trades / wins / losses that would add and at what
cost in R / PnL / MAE, whether it holds across bullish / bearish /
instruments / timeframes, and whether it is robust or a small-sample
artifact. It NEVER promotes a configuration.

Modules (live import surface):
  baseline.py             -- read-only BaselineOutcome view of an
      OpportunityRecord on the SAME outcome surface the metrics read
      (like-for-like baseline vs experiment); filled-without-result
      stays UNSETTLED; r from authoritative journal r else
      pnl/risk_amount; mae/mfe kept None when journal omits them
  experiment_metrics.py   -- metrics_for: reuses the FROZEN 9B
      lab.metrics formulas and augments total/avg/median R, gross
      profit-R / gross loss-R, avg/median MAE & MFE, avg/median
      bars-to-entry; group_metrics / group_sizes by direction /
      exchange / instrument / timeframe / strategy / category /
      entry_model / experiment_id; zero denominators -> 0.0, PF
      inf-parity, never NaN
  opportunity_analysis.py -- category distribution reusing ONLY the 9C
      classify_opportunity vocabulary; verbatim rejection-reason
      distribution; missed-continuation counts
  recovery_analysis.py    -- RecoveryReport: per-opportunity transition
      BASELINE -> EXPERIMENT from existing tokens (REJECTED /
      ENTRY_NOT_REACHED / MISSED_CONTINUATION -> WIN / LOSS /
      STILL_*; FILLED -> BETTER / WORSE / SAME / NOT_FILLED); cost of
      recovery (additional trades/wins/losses, incremental R & PnL,
      recovery rate, rejected-reason buckets, missed-continuation
      isolated); opportunity identity preserved
  comparison.py           -- ExperimentComparison: baseline-vs-experiment
      and experiment-vs-experiment deltas (incremental fills/wins/
      losses/R/PnL, delta expectancy / win-rate / PF / MAE / MFE,
      sample counts); inf-safe, never NaN; exact config provenance
  robustness.py           -- deterministic lightweight assessment:
      insufficient / small sample, no-significance claim, loss
      expansion, directional imbalance, in-sample-only -> OOS required;
      no statistical procedure, no overfitting language
  experiment_matrix.py    -- ExperimentMatrix: composes the FROZEN 9B
      ParameterGrid + the 9C-only outcome_bars dimension into
      deterministic independent CounterfactualConfigs; caller insertion
      order, empty ranges -> zero combos, base config never mutated,
      deterministic 9C ids, unknown keys fail loudly, never blended
  research_report.py      -- ResearchReport: BASELINE / EXPERIMENTS /
      RECOVERY / REJECTED / ENTRY_MODEL_COMPARISON / DIRECTIONAL /
      METRICS / ROBUSTNESS / WARNINGS sections preserving exact config
      provenance; to_dict() + render(); ANALYZER-NOT-OPTIMIZER statement
  research_analyzer.py    -- ResearchAnalyzer: read-only orchestration;
      ALWAYS like-for-like per-experiment baseline (restricted to the
      opportunities that experiment evaluated); strict provenance guard
      (every experiment carries its exact CounterfactualConfig or fails
      loudly); analyze_results / run_and_analyze; simulation ALWAYS
      stays in 9C (the analyzer only reads already-causal facts)

Isolation: the analyzer reads OpportunityRecords + 9C counterfactual
outcomes only (COUNTERFACTUAL provenance only). It NEVER mutates
OpportunityRecord / CounterfactualConfig / CounterfactualOutcome /
Journal / TradeRegistry / Account / PortfolioState / SharedCapital.
No AI / ML, no optimizer, no automatic parameter selection or
promotion, no ranking ("higher expectancy", not "best"). No lookahead
-- it never re-simulates; it only summarizes 9C's already-causal
facts. It reports evidence only; any future AI research layer
(9E/9F/9G) consumes this structured evidence and still requires human
review + OOS validation before production consideration. Phase 7E
NO-GO and 6C/6D/6E/7/8/8B frozen layers are untouched (fully additive;
no production edits).

------------------------------------------------------------

Phase 9E -- Research Intelligence / Recommendation Engine

Status

Active (core/research/intelligence/* -- STATUS 122). Deterministic,
research ONLY (NOT production optimization, NOT ML/AI). A read-only
layer that CONSUMES a 9D ResearchReport (and optionally the
already-produced 9C CounterfactualOutcomes and supplied confluence
features) and produces structured, explainable, evidence-backed research
RECOMMENDATIONS. It NEVER simulates (9C owns simulation), never
modifies strategy / execution / risk / portfolio / live-or-paper
behavior, never imports or invokes any AI / LLM / ML, never
auto-promotes, and never reinterprets the Phase 7E NO-GO as a
production directive (directional analysis stays research-only, never a
directional production rule). Recommendation STATUS is a research label
(OBSERVATION / HYPOTHESIS / PROMISING / INCONCLUSIVE / REJECTED /
REQUIRES_OOS / BLOCKED -- never "approved for production").

Modules (live import surface):
  recommendation_types.py -- the closed plain-string vocabulary:
      RECOMMENDATION_STATUSES, RECOMMENDATION_CATEGORIES, evidence
      grades INSUFFICIENT_SAMPLE / SMALL_SAMPLE / LIMITED / MODERATE /
      STRONG, the 9D robustness terms ROBUST / NON_ROBUST / OOS_REQUIRED
      / LOSS_EXPANSION / DIRECTIONAL_IMBALANCE / NO_CLEAR_ADVANTAGE,
      RECOVERABLE_BASELINE_CATEGORIES
  recommendation.py      -- immutable Recommendation with a
      deterministic recommendation_id (sha1 over category + candidate
      ids + parameters_changed; same evidence -> same id, no UUIDs);
      carries baseline / candidate metrics, recovery facts, deltas,
      robustness_status, sample_size, warnings, recommendation_status
  evidence.py            -- EvidencePackage per candidate: exact
      experiment_id + config provenance + baseline / candidate metrics +
      like-for-like comparison + recovery + robustness + sample_size;
      deterministic NON-statistical evidence_strength by settled count
      (never "significant")
  opportunity_recovery.py-- OpportunityRecoveryInsight: per-category
      recovery from the 9D recovery-transitions (REJECTED /
      ENTRY_NOT_REACHED / MISSED_CONTINUATION -> WIN / LOSS / STILL_*),
      count-weighted; distinguishes recovered WIN (success) from
      recovered LOSS (costs R, never a success); recovery_rate and
      successful_recovery_rate
  parameter_insights.py  -- per-parameter comparison of experiments that
      vary along ONE config parameter (rr / expiry / entry_offset /
      entry_offset_atr / entry_model / stop_mode / target_mode /
      outcome_bars) reported as MOVES not "best"; deterministic
      numeric-then-string value ordering; only params with >1 distinct
      value are reported
  directional_analysis.py-- per-direction (BULLISH/BEARISH) and
      per-symbol decomposition of 9D group metrics; directional-imbalance
      flag propagated; symbol_breakdown flags broad-vs-symbol-specific
      advantage; honest "no symbol breakdown ..." when no outcomes are
      supplied (never fabricated)
  confluence_analysis.py -- infrastructure for FUTURE feature/confluence
      evidence (Wyckoff / footprint / Fibonacci / flow / volume /
      liquidity / market-structure / FVG / order-block / displacement /
      smart-money). Works with ZERO confluence data: reports
      CONFLUENCE_DATA_UNAVAILABLE and no fabricated rows; passes through
      supplied decision-time features read-only
  robustness_gate.py     -- deterministic robustness STATUS classifier
      folding 9D findings + recovery cost + directional balance:
      INSUFFICIENT_SAMPLE / LOSS_EXPANSION / OOS_REQUIRED / NON_ROBUST /
      ROBUST / INCONCLUSIVE; never claims significance; never
      blocks/enables production
  hypothesis.py          -- deterministic Hypothesis objects (traceable,
      id-stable; one per recommendation plus directional-imbalance / OOS
      caveats) -- the structured input a future AI interpreter consumes
  research_intelligence.py -- ResearchIntelligence orchestrator over a
      9D report (+ optional outcomes_by_experiment + confluence) ->
      immutable IntelligenceReport (recommendations sorted by id,
      EvidencePackage list, confluence, insights recovery/parameter/
      directional/symbol, hypotheses, deterministic LEAD as first of
      PROMISING / REQUIRES_OOS / HYPOTHESIS; to_dict() ships a standing
      NON-PRODUCTION reminder; render() deterministic)

Isolation: the intelligence layer reads a 9D report (+ read-only 9C
outcomes and supplied confluence) only. It NEVER mutates the source
report / outcomes / configs / Journal / TradeRegistry / Account /
PortfolioState / SharedCapital. NO simulation, NO optimization, NO
auto-promotion, NO ranking-as-'best', NO AI / ML / LLM (only packages
evidence for a future interpreter), NO lookahead, confluence is NEVER
fabricated. Confluence / directional / symbol evidence is NEVER a
production rule. Phase 7E NO-GO and 6C/6D/6E/7/8/8B/9A-9D frozen layers
untouched (fully additive; no production edits).

------------------------------------------------------------

Phase 9O -- Research UX: Recommendation Readback

Status
Active (core/research/readback/* -- STATUS 132). An autonomous,
deterministic, research-only explanation layer that consumes the frozen
9N RecommendationReport and converts it into a human-usable readback of
WHY each recommendation exists, what evidence supports it, what failed,
what remains uncertain, and exactly why it is still research-only. It
consumes ONLY the frozen 9N report (never re-running OOS / conditional
ML / regime), never selects a strategy, never emits an order, never
touches a ledger, and never changes a parameter. The central boundary
is that VALIDATED_RESEARCH_FINDING is the strongest possible statement
(a research artifact) and TRADABLE_STRATEGY is IMPOSSIBLE at this
boundary by construction: the closed RESEARCH_VERDICTS vocabulary has
no tradable member, entry/report constructors reject one, is_tradable
is a property permanently False, production_status is always
RESEARCH_ONLY, and emission_check() verifies NEVER_EMITTED tokens are
absent from the ACTUAL serialized body.

Modules (live import surface):
  constants.py       -- closed RESEARCH_VERDICTS (SEVEN_E_BLOCKED /
       NO_EVIDENCE / INCONCLUSIVE / REJECTED / REQUIRES_MORE_OOS /
       CONDITIONAL / PROMISING / VALIDATED_RESEARCH_FINDING; no tradable
       member) + PRODUCTION_STATUS + UNCERTAINTY_ROSTER +
       NEGATIVE_EVIDENCE_ROSTER + NEVER_EMITTED
  types.py           -- frozen ReadbackEntry + frozen ReadbackReport
       (deterministic O+10hex id excluding report_id; is_tradable False;
       render / to_dict / to_json / emission_check)
  explain.py         -- verdict_for_9n_status (total injective 9N->9O
       mapping; top 9N tier -> VALIDATED_RESEARCH_FINDING, never
       TRADABLE); explain_entry / explain_report (1:1 pairing joined on
       hypothesis_id|oos_report_id); build_readback constructor/validator
  __init__.py        -- aggregated live import surface (16 names)

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|trading|ledger|account|portfolio|risk|market_data|
setup|pipeline; no AI SDK, no scipy, no random, no uuid, no datetime, no
numpy; consumes ONLY the frozen 9N report -- no simulation, no
optimization, no parameter modification. It NEVER mutates the Journal /
TradeRegistry / Account / PortfolioState / SharedCapital, runs NO
optimization, NO auto-promotion, and can never claim a methodology for
trading live. Phase 7E NO-GO and 6C/6D/6E/7/8/8B/9A-9N frozen layers
untouched (fully additive; no production edits).

Proof: tests/test_researcher_9o.py 48/48 OK (closed verdict vocabulary
with no tradable member + entry/report reject any tradable verdict,
total injective 9N->9O verdict mapping, 1:1 entries == recommendations +
joined evidence from the frozen finding, aspect coverage OOS/regime/
discovery/counterfactual/baseline/supporting-metrics/negative, closed
uncertainty + negative-evidence tags, deterministic report id + rerun +
reordered-build equal, frozen report/entry + is_tradable False +
production_status immutable, NEVER_EMITTED tokens absent from the
serialized body, no production imports/import-boundary + no
random-uuid-datetime-scipy-sklearn, canonical e2e report_id O881c3a9a39
over the frozen 9N Ne4c9dc7886). FULL SUITE: 1355/1355 OK (1307 prior +
48 new 9O; zero existing-test changes). compileall clean; tracked .pyc
restored before commit. No BREAKOUT/rules/7E results modified.

------------------------------------------------------------

Phase 9N -- Research Recommendation & Evidence Readback

Status

Active (core/research/recommendation/* -- STATUS 131). An autonomous,
deterministic, research-only readback layer that turns the frozen 9M OOS
/ 9L conditional-ML / 9K regime results into actionable, human-readable
research recommendations -- completely disconnected from production. It
consumes the frozen reports (never re-simulating, never re-deriving,
never optimizing, never modifying strategy parameters) and, for every
consumed discovery, emits a RecommendationFinding answering WHAT was
discovered, WHY it might have worked, WHERE it worked, WHERE it failed,
HOW robust it is, and WHAT should be investigated next. The
recommendation vocabulary is deliberately small and conservative
(7E_BLOCKED / NO_EVIDENCE / INCONCLUSIVE / REJECTED / REQUIRES_MORE_OOS
/ CONDITIONAL / PROMISING / ROBUST_RESEARCH_FINDING) and the ONLY
directive a finding may carry is INVESTIGATE_FURTHER -- never "change
the strategy", never "deploy now". A 7E NO-GO finding is always
7E_BLOCKED; a regime-scoped (conditional) claim is NEVER promoted into a
universal PROMISING / ROBUST_RESEARCH_FINDING tier; ROBUST_RESEARCH_
FINDING requires an unconditional claim with HIGH robustness. Every
finding retains its full evidence chain (recommendation -> OOS readback
-> hypothesis readback -> optional 9L/9K ancillary readback -> narrative
answers -> limitations), and every REJECTED period and every limitation
is kept visible. Each finding flattens 1:1 into a Recommendation that
preserves the frozen OOS report id in its evidence_ids. The frozen
RecommendationReport can never be production_ready (construction with
True raises ValueError; assignment raises FrozenInstanceError;
is_production_ready is a property always False) or emit a promotion
token; emission_check() proves the isolation contract against the
ACTUAL serialized body.

Modules (live import surface):
  constants.py       -- closed vocabulary + locked INVESTIGATE_FURTHER
       directive + five READBACK_QUESTIONS + closed WHY/WHERE narratives
       + LIMITATIONS roster + PRODUCTION_DIRECTIVES + frozen review protocol
  ladder.py          -- deterministic total 9M final_status -> 9N mapping
       (7E always blocked; conditional never universal; top rung needs
       unconditional + HIGH)
  evidence.py        -- build_finding: full evidence chain + narrative
       answers + limitations (nothing hidden); to_recommendation: 1:1
       flattening preserving the OOS report id in evidence_ids
  engine.py          -- RecommendationEngine.run(oos_report, ml_report,
       regime_report, hypothesis_ids) -> frozen RecommendationReport;
       unknown gate keys raise; empty report honest; 1:1 findings ==
       recommendations asserted
  types.py           -- frozen OosReadback / HypothesisReadback /
       AncillaryReadback / ReadbackAnswers / RecommendationFinding /
       Recommendation / EvidenceSummary / RecommendationStatistics /
       ReviewOverview
  report.py          -- frozen RecommendationReport + build_report;
       deterministic N+10hex id (payload excludes report_id, stable under
       reordered recommendations); production_ready always False
       (ValueError + FrozenInstanceError); is_production_ready property
       False; emission_check() dict proves NEVER_EMITTED tokens absent
       from the report body
  __init__.py        -- aggregated live import surface (26 names)

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|trading|ledger|account|portfolio|risk|market_data|
setup|pipeline; no AI SDK, no scipy, no random, no uuid, no datetime, no
numpy; consumes FROZEN reports only -- no simulation, no optimization, no
parameter modification. It NEVER mutates the Journal / TradeRegistry /
Account / PortfolioState / SharedCapital, runs NO optimization, NO auto-
promotion, and the directive is always INVESTIGATE_FURTHER. Phase 7E
NO-GO and 6C/6D/6E/7/8/8B/9A-9M frozen layers untouched (fully additive;
no production edits).

Proof: tests/test_researcher_9n.py 77/77 OK (closed vocabulary + locked
directive, ladder unit coverage over the full 9M ladder incl. 7E always-
blocked and conditional-never-universal and LOW-robustness blocks the top
rung, evidence-chain retention + deterministic finding ids + frozen
containers + 1:1 to_recommendation preserving the OOS report id in
recommendation.evidence_ids, engine reading a real frozen 9M report (object
and dict) + hypothesis filter + empty honest + unknown gate ValueError +
1:1 and statistics.n_recommendations == len(recommendations), production
guard: construction with production_ready=True raises ValueError,
assignment raises FrozenInstanceError, is_production_ready property False,
promotion tokens absent from the serialized body + no production imports/
import-boundary + no random-uuid-datetime-scipy-sklearn, deterministic
report id equal across repeat build + reordered recommendations, canonical
e2e report_id Ne4c9dc7886 + finding N7ff6711cff mapping the 6/6 walk-forward
clean long recovery to ROBUST_RESEARCH_FINDING, wf-false -> PROMISING,
conditional -> CONDITIONAL, 7E -> BLOCKED). FULL SUITE: 1307/1307 OK (1230
baseline + 77 new 9N; zero existing-test changes). compileall clean;
tracked .pyc restored before commit. No BREAKOUT/rules/7E results modified.

------------------------------------------------------------

Phase 9M -- Multi-Period Out-of-Sample Validation

Status

Active (core/research/oos/* -- STATUS 130). An autonomous, deterministic,
research-only multi-period OOS replay layer over the frozen 9K/9L
discoveries. It partitions the trailing 50% of the frozen chronological
window into 6 unseen out-of-sample periods, replays the fixed candidate
grid (the 3 production-supported entry models) within each period against
the genuine 9C baseline counterfactual, and applies survival / sign-
consistency / economic gates plus a GLOBAL Sidak familywise correction
over the TOTAL enumerated hypothesis family -- never a per-finding
decision. Per-period verdicts use a closed vocabulary (VALIDATED /
PROMISING / INCONCLUSIVE / REJECTED / UNAVAILABLE) and roll up a finding
ladder (BLOCKED -> UNAVAILABLE -> INCONCLUSIVE -> REJECTED ->
OOS_PARTIAL -> OOS_PROMISING -> OOS_ROBUST -> VALIDATED_RESEARCH_ONLY);
the top rung additionally requires an explicit walk-forward declaration.
Evidence is never merged across symbols, directions (LONG -> BULLISH,
SHORT -> BEARISH) or regimes -- robustness LOW blocks the top rung. A 9M
run persists NOTHING, never lands a strategy, and the frozen OosReport
can never be production-ready (ValueError guard) or emit a promotion
token. Protocol is locked by default and never re-optimized (OOS_PERIODS
6, DISCOVERY_FRACTION 0.5, MIN_OOS_TRADES_PER_PERIOD 10, probabilities
gated by required_min_n over the family, PURGE/EMBARGO 0, split protocol
frozen; no shuffle, chronological only).

Modules (live import surface):
  constants.py       -- closed vocabulary + ladder + locked protocol
       defaults + SEVEN_E_NO_GO + CANDIDATE_ALTERNATIVES (3 fixed
       entry models)
  oos_types.py       -- frozen HypothesisOosResult / OosSummary /
       OosPeriodEvidence; economic_statistics / survival_ratio;
       scalar-safe to_dict
  period.py          -- partition (864/432/432/6, boundaries 72) +
       outcome_leakage (NOT_REQUIRED / PROTECTED / UNAVAILABLE)
  validator.py       -- evaluate_pool / evaluate_period (counterfactual
       replay + baseline delta + n_candidate_filled counts fills)
  aggregator.py      -- summarize_periods + final_status ladder +
       multiple_testing Sidak + per_period_summary
  robustness.py      -- classify LOW/MEDIUM/HIGH with passes/reasons;
       per-symbol / direction / regime evidence separated, never merged
  engine.py          -- OosValidationEngine.run -> frozen OosReport;
       totals-gate over TOTAL family, leak guard PROTECTED, 7E BLOCKED,
       unknown gate keys raise loudly
  report.py          -- frozen OosReport; deterministic M+10hex id;
       is_production_ready ALWAYS False (enforced); emission_check
       proves NEVER_EMITTED tokens absent from the report body
  __init__.py        -- aggregated live import surface (29 names)

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|trading|ledger|account|portfolio|risk|market_data|
setup|pipeline; no AI SDK, no scipy, no random, no uuid, no datetime, no
numpy; decision/fill-time windows only -- no lookahead; no shared mutable
state, no registry, no network. It NEVER mutates the Journal /
TradeRegistry / Account / PortfolioState / SharedCapital, runs NO
optimization, NO auto-promotion. Phase 7E NO-GO and 6C/6D/6E/7/8/8B/9A-9L
frozen layers untouched (fully additive; no production edits).

Proof: tests/test_researcher_9m.py 37/37 OK (protocol surface closed
vocabulary + ladder exact, Sidak familywise exact math incl. family-2
corrected_alpha 0.025320565519103666, partition math 864/432/432/6 +
boundaries 72, aggregator ladder REJECTED/OOS_PARTIAL/OOS_PROMISING/
INCONCLUSIVE/OOS_ROBUST via final_status units, recovery unit 40 R ->
n_recovered 40 capture_gain 1.0 INCONCLUSIVE, canonical e2e report_id
Me686dca76c wf-true / M8be132b4e4 wf-false: 6/6 VALIDATED + HIGH
robustness + familywise true + leak PROTECTED + survival_ratio 1.0,
7E BLOCKED, SHORT UNAVAILABLE, bounds INCONCLUSIVE via override,
byte-identical determinism rerun + no-lookahead future-bar mutability
rerun + no random-uuid-datetime-scipy-sklearn-snapshot + no production
imports/import-boundary + promotion tokens absent from report body).
FULL SUITE: 1230/1230 OK (1193 baseline + 37 new 9M; zero existing-test
changes). compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E results modified.

------------------------------------------------------------

Phase 9L -- Advanced ML + Regime / Opportunity Discovery

Status

Active (core/research/conditional_ml/* -- STATUS 129). An autonomous,
deterministic, research-only conditional-ML evidence layer that fuses the
frozen 9G stats/ML machinery with the frozen 9K regime framework. Each
9A opportunity becomes an immutable decision-time OpportunityContext
(regime at the decision bar AND at the counterfactual fill bar, 9F
decision-time features, baseline entry state). The engine then replays
the FIXED bounded alternative grid -- exactly the 3 production-supported
entry models (LIMIT_RETEST / MARKET_CONFIRMATION / BREAKOUT_CONTINUATION)
-- through 9C counterfactual simulation -- deliberately NOT an auto-ML
optimizer: no 100k-combination search, no pick-highest-profit. Pipeline
in fixed order: generate -> filter -> temporal TRAIN|VALIDATION|OOS ->
conditional outcome probabilities -> recovery probability (missed/
rejected baselines) -> conditional entry-model selection -> regime-
conditional feature interactions -> regime transition detection
(generated vs filled) -> symbol segmentation -> OOS confidence/
calibration -> GLOBAL multiple-testing correction -> robustness ->
economic significance -> minimum sample -> limitations -> frozen
research finding. Every surface retains EVERY finding (INCONCLUSIVE /
gap / negative included -- nothing hidden). The GLOBAL guard is stricter
than any per-surface gate: Sidak familywise over the TOTAL enumerated
hypothesis family plus Holm within the interaction family, and proper
two-sided tail p-values (strong evidence -> small p, never inverted).
OOS calibration pairs every probability surface with its calibraion
(ECE / Brier / slope; a gap is a finding). A 9L run persists NOTHING,
never lands a strategy, and the frozen ConditionalMlReport can never be
production-ready (ValueError guard) or emit a promotion token.

Modules (live import surface):
  types.py           -- fixed CANDIDATE_ALTERNATIVES grid + frozen
       evidence containers (OpportunityContext / RecoveryFinding /
       AlternativeEvidence / EntrySelection / InteractionFinding /
       TransitionFinding / SymbolBehaviour / CalibrationBin/Summary);
       fixed INTERACTION_FEATURES roster + MAX_INTERACTION_TESTS
  guards.py          -- required_min_n / familywise_alpha (Sidak) /
       holm_survives / z_prop_win / z_mean_diff (pure math.erf tails)
  probabilities.py   -- fixed-form additive-logit OutcomeModel; trained
       ONCE on TRAIN, evaluated on VALIDATION/OOS; no hyper-parameter
       search; clipped, clamped, deterministic
  contexts.py        -- opportunity -> OpportunityContext (decision-time
       regime + fill regime, 9F features, entry state; no lookahead)
  recovery.py        -- recovery probability per (alternative, regime)
       for missed/rejected baselines; non-fill counts as failed
       recovery (honest, no fabrication)
  entries.py         -- conditional entry-model selection per cell with
       every alternative row RETAINED when INCONCLUSIVE
  interactions.py    -- regime-conditional feature interactions
       (size-2/3 only, same-feature combos structurally excluded, hard
       cap reported when reached, train->OOS sign consistency)
  transitions.py     -- generated-regime -> filled-regime table, stable
       buckets always STABLE, CHANGED only on material delta
  symbols.py         -- symbol x regime cells with gated justified flag
  calibration.py     -- OOS-only confidence/calibration (ECE/Brier/
       slope; bins all retained; a gap is a finding)
  engine.py          -- ConditionalMlEngine.run -> frozen report;
       robustness (pipeline, chronological split, fixed grid, cap) +
       limitations; global Sidak/Holm guard + frozen-safe flag injection
  report.py          -- frozen ConditionalMlReport; is_production_ready
       ALWAYS False (enforced), emission_check proves NEVER_EMITTED
       tokens absent from the report body
  __init__.py        -- aggregated live import surface (39 names)

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|trading|ledger|account|portfolio|risk|market_data|
setup|pipeline; no AI SDK, no scipy, no random, no uuid, no datetime, no
numpy on the probability path (pure math); no footprint/volume
fabrication (order-flow features stay UNAVAILABLE on OHLCV fixtures). It
compiles / tests / runs in this numpy-only environment identically.

Isolation: research-only, deterministic, immutable inputs; NO lookahead
(divergent futures after every decision/fill bar produce byte-identical
reports); NO production internals imported; NO auto-promotion
(NEVER_EMITTED tokens absent from every report body); no trade / order /
ledger directive ever emitted. The 7E NO-GO and frozen 6C-6E/7/8/8B/9A-
9K layers stay untouched.

------------------------------------------------------------

Phase 9K -- Regime / Conditional Opportunity Discovery

Status

Active (core/research/regime/* -- STATUS 128). An autonomous,
deterministic, research-only "under-which-market-conditions" engine that
consumes ONLY the frozen 9A-9I layers (and the frozen 9J layer read-only).
It segments frozen 9A records by the deterministic 9C category AND a
decision-time MarketRegime (window ends AT the decision bar -- no
lookahead), then for each candidate configuration (strict 9B vocabulary,
loud failure on unknown axes) measures the candidate vs the frozen
baseline INSIDE every regime cell: within-cell expectancy, recoveries,
delta versus baseline, global-vs-within edge, and split breadth. Findings
are closed-status (CONDITIONAL / CONDITIONAL_WEAK / INCONCLUSIVE /
NOT_SUPPORTED) and EVERY cell and finding is retained -- no hiding of
negative results. Material findings are validated chronologically
(expanding-train / trailing-test walk-forward, no shuffle, majority of
adequate windows positive and above baseline), guarded by a conservative
Sidak familywise + sample-requirement multiple-testing correction, and
reported with observed-only 9F feature splits and per-finding robustness
coverage. A 9K run persists NOTHING, never lands a strategy, and its
frozen RegimeReport can never be production-ready (ValueError guard) or
carry a production directive (ConditionalFinding guard).

Modules (live import surface):
  regime_types.py    -- closed dimension vocabularies + frozen evidence
       containers (MarketRegime / RegimeObservation / ConditionalCell /
       ConditionalFinding / FeatureSplit / WalkForwardWindow/Summary);
       REGIME_DIMENSIONS + PRIMARY_REGIME_DIMENSIONS; deterministic ids
  indicators.py      -- pure decision-time regime indicators
       (trend_vs_range / direction_structure / volatility_regime /
       atr_regime / displacement_strength / liquidity / fvg /
       order_block / wyckoff_phase), data-gated UNAVAILABLE, reusing the
       frozen core.research.features.indicators atr/sma/volatility
  detector.py        -- detect_regime -> MarketRegime at the decision
       bar; closed dimension vocabulary + validate_dimension
  segmenter.py       -- 9A records -> RegimeObservations via frozen 9C
       classify_opportunity + regime; honest empty-regime (no decision
       bar) handling; in_cell / cell_labels / regime_coverage / by_category
  conditional.py     -- _validate_candidate / build_config (frozen 9C
       identity) / conditional_discovery / feature_splits: candidate vs
       baseline in every cell, recoveries, split breadth, statuses
  walkforward.py     -- temporal_windows (chronological, no shuffle) /
       validate_conditional (survival = 2/3 of adequate windows positive
       and above baseline, min_validation_n; thin windows counted)
  multiple_testing.py-- Sidak familywise alpha + required_min_n =
       min_cell_n + ceil(log2(1+H)); findings flagged (never hidden)
  engine.py          -- OpportunityDiscoveryEngine.run -> RegimeReport;
       robustness coverage + limitations + next_research (9M / 9L / 9N)
  report.py          -- frozen RegimeReport; is_production_ready ALWAYS
       False (enforced), emission_check proves NEVER_EMITTED tokens absent

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|trading|ledger|account|portfolio|risk|market_data|
setup|pipeline; no AI SDK, no random, no uuid, no datetime; no footprint/
volume fabrication; regime windows end at the decision bar. It compiles /
tests / runs in this numpy-only environment identically.

Isolation: research-only, deterministic, immutable inputs; NO lookahead; NO
simulation (9C owns it); NO production internals imported; NO auto-
promotion (NEVER_EMITTED tokens absent from every report; ConditionalFinding
can never be a production directive); no trade / order / ledger directive
ever emitted. The 7E NO-GO and frozen 6C-6E/7/8/8B/9A-9J layers stay
untouched.

------------------------------------------------------------

Phase 9J -- Strategy Discovery / Experiment Engine

Status

Active (core/research/discovery/* -- STATUS 127). An autonomous,
deterministic, research-only discovery engine that consumes ONLY the frozen
9A-9I layers. It audits the unified 9I ResearchDataset for opportunity gaps,
generates recovery-first, evidence-gated alternative-experiment hypotheses,
schedules them against an explicit budget (INJECTED experiments are never
suppressed; research-memory dedup is reported as skipped), runs each over the
frozen 9C-9G machinery, and passes each result through the closed Discovery
gate ladder: BLOCKED (7E NO-GO) -> INCONCLUSIVE -> REJECTED (no advantage /
loss-expansion / directional contradiction) -> PROMISING (economic
trade-off) -> REQUIRES_OOS -> REJECTED (OOS did not confirm) -> PROMISING
(thin settled) -> VALIDATED (research-only, never production-ready). OOS can
never be bypassed. Every experiment is retained (rejected/blocked included),
scores are deterministic and complete, and any report emitted carries
emission_check with is_production_ready / is_production_directive always
False (frozen dataclass). The engine runs entirely in-memory: it persists
NOTHING, never lands a strategy, and never auto-promotes.

Modules (live import surface):
  candidate_space.py   -- validate_overrides / vocabulary: closes the
      supported 9B axis set; unsupported axes and known-unsupported entry
      models fail loudly; expiry must be a positive int
  gaps.py              -- detect_gaps / generate_hypotheses /
      dedup_hypotheses: deterministic gap audit + recovery-first
      executable hypotheses (RR/stop/entry-offset/entry-model/expiry/
      confirmation) with sha1 ids and evidence
  scheduler.py         -- deterministic order, budget counts GENERATED only,
      invalid candidates skipped loudly, memory dedup marked skipped
  discovery_runner.py  -- StrategyDiscoveryEngine.run: drives frozen
      9C/9D/9E/9F/9G over scheduled hypotheses; recovery_count +
      per_category + added_R; deterministic report / memory recording
  robustness_filter.py -- the closed 10-step gate ladder (OOS never
      bypassed; 7E NO-GO preserved as BLOCKED)
  baseline_comparator.py-- economic_assessment (capture_gain / expectancy /
      loss-rate / drawdown deltas, loss_expansion); avg-MAE risk_delta is
      report-only; verdict CAPTURE_TRADE_OFF or
      RECOVERY_CAPTURES_VALUE_WITHOUT_WORSE_ECONOMICS
  confluence_discovery.py -- observed-only 9F feature associations vs
      recovered REJECTED observations; never fabricated

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|risk|portfolio|engine|trade|account|strategy; no AI
SDK, no random, no uuid, no datetime; experimental runs persist nothing. It
compiles / tests / runs in this numpy-only environment identically.

Isolation: research-only, deterministic, immutable inputs; NO lookahead; NO
simulation (9C owns it); NO production internals imported; NO auto-
promotion (NEVER_EMITTED tokens absent from every report); no trade / order /
ledger directive ever emitted. The 7E NO-GO stays untouched as BLOCKED.
Strategy/production/risk/execution/portfolio/live-or-paper and 6C-6E / 7 / 8 /
8B / 9A-9I frozen layers untouched (fully additive; no production edits).

------------------------------------------------------------

Phase 9I -- Unified Research Dataset / Knowledge & Data Intelligence

Status

Active (core/research/dataset/* -- STATUS 126). A deterministic,
research-only knowledge/data layer that unifies every frozen 9A-9H
surface into one queryable ResearchDataset. Rows come from 9A journal
records, 9B/9C counterfactual outcomes, 9D analysis, 9E intelligence,
9F feature snapshots, 9G ML/statistical research, and 9H autonomous
investigations -- normalized into a single ResearchRow model with
stable deterministic sha1 ids (never UUID/timestamp), a closed
DatasetSource vocabulary, an observation_id join key, identity fields
for grouping, and two evidence bags (kv descriptive + measured
quantitative). This answers the original research goal: it MEASURES
why structurally valid setups were missed and WHICH alternative
entries / offsets / expiry / RR / confirmation could capture them
profitably -- without assuming a combination is profitable, without
optimizing for maximum profit, and without destroying robustness or
risk constraints. Every number cites the frozen 9C-9G evidence;
nothing here promotes a configuration to production.

Modules (live import surface):
  row.py       -- ResearchRow + DatasetSource + SOURCES (closed 7-source
      vocabulary); to_dict / row_from_dict round-trip
  collectors.py-- collect_journal / collect_counterfactual /
      collect_analysis / collect_intelligence / collect_features /
      collect_ml / collect_researcher: read-only normalizers (inputs
      never mutated)
  dataset.py   -- ResearchDataset: append-only, dedup by row_id,
      deterministic atomic JSON persist/load, corrupt->fresh
  queries.py   -- entry_pipeline_breakdown (why only some entered, by
      category + rejection reason), recovery_candidates (which missed
      could have been captured profitably under an alternative config,
      with recovered R and the recovering config), unify_by_observation
      (cross-source join), aggregate (group-by / count / sum / mean /
      win_rate), answer_context (compact 9I evidence dict for 9H)

Dependency isolation (contract): imports ONLY core.research.* surfaces --
never core.execution|risk|portfolio|engine|trade|account|strategy; no AI
SDK, no random, no uuid, no datetime. It compiles / tests / runs in this
numpy-only environment identically.

Isolation: research-only, deterministic, immutable inputs; NO lookahead;
NO simulation (9C owns it); NO production internals imported; NO auto-
promotion; no trade / order / ledger directive ever emitted. The 7E NO-GO
stays untouched. Strategy/production/risk/execution/portfolio/live-or-paper
and 6C-6E / 7 / 8 / 8B / 9A-9H frozen layers untouched (fully additive; no
production edits).

------------------------------------------------------------

Phase 9H -- Autonomous AI Researcher Core

Status

Active (core/research/researcher/* -- STATUS 125). A provider-neutral,
research-only autonomous researcher scientist that observes the frozen
9A-9G evidence, forms hypotheses ONLY from the supported 9B/9C experiment
vocabulary (unsupported params / entry models / expiry fail loudly rather
than silently diverge), runs each experiment through the frozen 9C-9G
machinery read-only, keeps a persistent Research Memory (sha1
question-fingerprint dedup + recorded history + next-suggestion), and
returns ranked, evidence-cited conclusions through an EvidenceEvaluator
ladder VALIDATED / HYPOTHESIS / REJECTED / INSUFFICIENT_EVIDENCE /
OBSERVATION. Every conclusion cites its evidence package or returns
INSUFFICIENT_EVIDENCE -- it is never allowed to guess. OOS validation can
never be bypassed (MIN_OOS_SETTLED=5 + a 9E robustness gate that downgrades
VALIDATED otherwise). production_ready=False is a hard invariant: the
researcher NEVER places orders, NEVER mutates the input records, NEVER
looks ahead, NEVER auto-promotes. External AI providers are OPTIONAL -- a
guarded OpenAI/Anthropic/OpenRouter/Ollama stub degrades to
PROVIDER_UNAVAILABLE when the SDK is absent, and the deterministic
NullProvider delivers the full behaviour with zero external AI (no top-level
AI-SDK imports anywhere).

Modules (live import surface):
  types.py         -- EvidenceContext / Hypothesis / ExperimentResult /
      ResearchRecommendation / InvestigationReport + closed experiment
      vocabulary + STANDING_LIMITATION + deterministic sha1 ids
  providers.py     -- AIProvider ABC; always-available deterministic
      NullProvider with evidence-gated rule drafts; guarded OpenAI /
      Anthropic / OpenRouter / Ollama stubs (lazy importlib.util.find_spec)
      -> PROVIDER_UNAVAILABLE; ProviderUnavailable; REGISTERED /
      available_providers
  memory.py        -- ResearchMemory: record / recall / dedup /
      next_suggestion; optional atomic JSON persistence; corrupt file ->
      fresh
  planner.py       -- ResearchPlanner: validate_override against the closed
      vocabulary; deterministic H+10hex hypothesis ids; memory dedup;
      deterministic sort
  experiments.py   -- ExperimentExecutor / ExperimentRun: drives the FROZEN
      9C CounterfactualRunner.grid -> 9D ResearchAnalyzer -> 9E
      ResearchIntelligence plus 9F StatisticalBaseline / temporal_split OOS
      fold / guarded FeatureAnalyzer; per-bundle ExperimentResult
  evaluate.py      -- EvidenceEvaluator ladder + 9E robustness gate (never
      bypassed) + sha1 R+10hex recommendation ids; failed experiments
      retained, nothing pruned
  researcher.py    -- build_context + AutonomousResearcher.investigate ->
      InvestigationReport with full DATASET -> HYPOTHESIS -> EXPERIMENT ->
      RECOMMENDATION -> LIMITATION evidence chain; DEFAULT_BASE_CONFIG;
      production_ready=False
  __init__.py      -- 9H public surface

Dependency isolation (contract): the package imports ONLY core.research.*
surfaces -- never core.execution|risk|portfolio|engine|trade|account|
strategy at any line, and never any AI SDK at module top level. It compiles,
tests and runs in this numpy-only environment with sklearn / scipy AND every
AI SDK ABSENT (verified: the provider-neutrality and guarded-degradation
paths are exercised directly by the suite).

Isolation: research-only, deterministic, immutable inputs; NO lookahead;
NO simulation (9C owns it); NO production internals imported; NO auto-
promotion; no trade / order / ledger directive ever emitted. The 7E NO-GO
stays untouched. Strategy/production/risk/execution/portfolio/live-or-paper
and 6C-6E / 7 / 8 / 8B / 9A-9G frozen layers untouched (fully additive; no
production edits).

------------------------------------------------------------

Phase 9G -- ML / Statistical Research Layer

Status

Active (core/research/ml/* -- STATUS 124). DISCOVERS statistical
relationships; it does NOT decide what gets traded. Consumes the 9F
decision-time FeatureSnapshots + 9C/9D outcomes and produces
deterministic, chronologically-split statistical / simple-ML /
feature-interaction / opportunity-recovery research -- the evidence
foundation the later 9H autonomous AI researcher consumes. Strictly
research-only: never touches strategy / execution / risk / portfolio /
live-or-paper behavior, never auto-promotes, never emits a trade
directive, never imports production internals or any deep-AI dependency;
every result is ASSOCIATION (never causation, never a trade decision).
NO-TEMPORAL-LEAKAGE: chronological TRAIN | VALIDATION | OOS plus
expanding-window walk-forward, no random shuffling; the 9F decision-time
rule (features only from candles strictly < decision_bar) is inherited
-- no future information enters any feature vector.

Modules (live import surface):
  split.py         -- deterministic chronological temporal_split (TRAIN |
      VALIDATION | OOS, no shuffle, no leak) + expanding walk_forward
  statistics.py    -- 9G.1 StatisticalBaseline (n / wins / losses /
      unsettled_rate / win_rate / loss_rate / entry_reached_rate / avg_R /
      expectancy / avg_MAE / avg_MFE / R-distribution); effect sizes;
      conditional_statistics P(WIN | value) / P(ENTRY_REACHED | value) /
      P(POSITIVE_R | value); honest None on zero denominators
  models.py        -- 9G.2 encode_target (ENTRY_REACHED / WIN / POSITIVE_R /
      EXPECTED_R / RECOVERY_SUCCESS, unsettled masked out); deterministic
      pure-numpy NumpyLogisticRegression + NumpyDecisionTree (ALWAYS
      available); SimpleModel 'numpy'/'sklearn' backend; sklearn optional +
      guarded -> ML_BACKEND_UNAVAILABLE; pure-numpy rank-sum AUC
  interaction.py   -- 9G.3 interaction_analysis ASSOCIATION tables over
      observed feature-value combos (Wyckoff + FVG + OB + Fibonacci +
      volatility + liquidity_sweep -> ENTRY_REACHED% / WIN% / avg R /
      avg MAE / avg MFE / n / sufficient_sample); absent/partial combos not
      reported; tiny samples honestly flagged
  analyzer.py      -- MlAnalyzer -> immutable MlResearchReport (chronological
      split + walk-forward + 9G.1 baseline/conditional + 9G.2 ML on TRAIN
      scored on VALIDATION/OOS + 9G.3 interaction + FIRST-CLASS
      opportunity-recovery research -> recovery_rate + expected R/MAE/MFE +
      proposed alternative entry/RR/expiry/model; to_dict() carries
      association_not_causation + no_trade_directive; render() deterministic)
  __init__.py      -- 9G public surface

Dependency isolation (contract): the production/paper engine and the whole
product install, compile, test and run with sklearn/scipy ABSENT (verified
in this environment: sklearn and scipy are NOT installed). Every statistical
baseline is pure math/numpy; the simple-ML backends are pure-numpy and
deterministic; sklearn is an OPTIONAL guarded backend that degrades to
ML_BACKEND_UNAVAILABLE -- the research stack is never a production dependency
and no production module imports core.research.ml.

Isolation: research-only, deterministic, immutable inputs; NO temporal
leakage; NO simulation (9C owns it); NO production internals imported; NO
deep-AI (torch/tensorflow/keras/xgboost/lgbm/mlx etc.); NO auto-promotion;
no trade directive ever emitted. The 7E NO-GO stays untouched.
Strategy/production/risk/execution/portfolio/live-or-paper and 6C-6E / 7 /
8 / 8B / 9A-9F frozen layers untouched (fully additive; no production edits).

------------------------------------------------------------

Phase 9F -- Confluence / Feature Evidence

Status

Active (core/research/features/* -- STATUS 123). Deterministic,
research-only evidence layer that makes the later 9G ML / AI research
meaningful. A decision-time, NO-LOOKAHEAD FeatureSnapshot is recorded per
opportunity at its EXACT decision bar (a bounded CausalWindow of bars
strictly index < decision_bar; the decision bar itself is never a feature
source), canonical confluence / market-structure / technical features are
derived deterministically, and the evidence is joined to the already-
labelled 9C / 9D outcomes into read-only CORRELATION tables. It NEVER
simulates (9C owns simulation), never modifies strategy / execution /
risk / portfolio / live-or-paper behavior, never imports or invokes any
AI / ML / LLM, never auto-promotes, never fabricates an unavailable
feature, and never quietly turns the Phase 7E NO-GO directional hypothesis
back into a production rule (a snapshot is EVIDENCE, not a
direction/size/action instruction).

Modules (live import surface) / files:
  causal_window.py        -- immutable CausalWindow / CandlePoint +
      extract_causal_window(candles, decision_bar, lookback): bounded
      decision-time history (bars < decision_bar); missing volume tolerated
      as None and NEVER fabricated; invalid OHLC rows dropped; never mutates
      inputs
  indicators.py           -- pure, data-gated deterministic indicators
      ATR / SMA / EMA / rolling_volatility / bollinger_position / OBV; each
      returns UNAVAILABLE (None) on too-short / misaligned series; OBV
      returns the accumulated total only over aligned equal-length series
  confluence_features.py  -- 13 deterministic producers: wyckoff_phase,
      market_structure, atr_regime, bollinger_position, sma_slope,
      obv_trend, liquidity_sweep, fvg_present, displacement_strength,
      order_block, fibonacci_zone (entry vs 0.382/0.5/0.618 swing band), and
      volume_profile / footprint_flow which return UNAVAILABLE because no
      order-flow / volume-profile data stream exists (never synthesized)
  feature_snapshot.py     -- immutable FeatureSnapshot preserving the
      opportunity's OWN decision-time entry / stop / target / atr + direction
      / instrument / timeframe / decision_bar / WindowSize + feature map +
      available_feature_count()
  dependency_analysis.py  -- build_dependency -> DependencyAnalysis of
      per-feature per-VALUE buckets: entry_reached_rate, rejected->recovered
      rate, missed-continuation count, WIN/LOSS win_rate, avg_R, avg_MAE,
      avg_MFE, direction / symbol segmentation; ZERO-outcome buckets report
      n but NEVER fabricate win_rate / R / rates; deterministic ordering;
      CORRELATION OF EVIDENCE only
  feature_analyzer.py     -- FeatureAnalyzer orchestrator: snapshot(record,
      candles) + analyze(...) -> immutable FeatureEvidenceReport with
      snapshots + a ConfluenceAnalysis fed into the FROZEN 9E
      name/value/sample/outcomes/experiment_id surface + the DependencyAnalysis;
      NO derivable feature -> CONFLUENCE_DATA_UNAVAILABLE (never claims
      confluence that does not exist); render() deterministic
  __init__.py             -- 9F public surface (CausalWindow / CandlePoint /
      extract_causal_window / FeatureSnapshot / ALL_PRODUCERS /
      DependencyAnalysis / FeatureDependency / build_dependency /
      FeatureAnalyzer / FeatureEvidenceReport / indicators)

Isolation: the feature layer records decision-time snapshots and joins them
to read-only 9C / 9D outcomes. It NEVER mutates records / candles / outcomes
/ Journal / TradeRegistry / Account / PortfolioState / SharedCapital. NO
simulation, NO optimization, NO auto-promotion, NO AI / ML / LLM, NO
lookahead (bars strictly before the decision bar), NO production imports,
footprint / volume-profile are UNAVAILABLE until order-flow data exists.
Phase 7E NO-GO and 6C/6D/6E/7/8/8B/9A-9E frozen layers untouched (fully
additive; no production edits).

------------------------------------------------------------

============================================================
TESTS
============================================================

Every production module SHALL have a matching

tests/test_<module>.py

before Production Ready status.

============================================================
ADDENDUM — STAGE 1–3 + STAGE 4 (paper certification)
============================================================

No NEW production modules in Stage 4 (additive functions only);
two Stage 1–3 modules registered here for completeness:

core/risk/costs.py — CostSpec (frozen formula), from_settings()
(production defaults), paper_cost_profile()/paper_profile_name()/
paper_venue_realistic() (Stage 4 paper-only profile; never
production defaults, never research ladders). Covered by
tests/test_hardening_stage123.py, tests/test_stage4_*.

core/live/reconciler.py — fail-closed local-vs-exchange
comparator (MATCH/IN_FLIGHT/MISMATCH/UNKNOWN/SKIP), atomic
snapshot journal, explicit resolve(). Wired into
core/live/broker_engine.py + main.py LIVE. Covered by
tests/test_hardening_stage123.py, tests/test_stage123_*,
tests/test_stage4_*.

Stage 4 additive production changes (no new modules):
- config/risk_settings.py: paper cost block
  (PAPER_COMMISSION_PER_TRADE/RATE/SLIPPAGE_BPS/PROFILE_NAME/
  VENUE_REALISTIC) + KILL_SWITCH_ENV_VAR. Production defaults
  and all thresholds unchanged.
- core/risk/risk_engine.py: kill_switch_active() seam enforced
  at analyze() entry (mandatory order path).
- core/risk/order_intent.py: actual_risk_reward field (realized
  fill RR stamped by mutating fills; gated risk_reward kept).
- backtesting/backtester.py: realized-RR stamp + log at
  NEXT_BAR_OPEN entry mutation (observability only; fill
  semantics unchanged).
- docs/import_manifest.md: Stage 1–3 + Stage 4 addenda.

============================================================
ADDENDUM — PHASE 12 (safety/execution/data recertification)
============================================================

No strategy, threshold, or research-hypothesis change. All
entries below are engineering correctness / safety /
durability fixes with regression tests. LIVE stays NO-GO;
EDGE stays NOT ESTABLISHED; OOS stays ABSENT.

NEW production modules (registered here for completeness):
- core/execution/order_ack.py -- acknowledgement truth:
  AckResult + classify_ack()/classify_exception() mapping a
  raw exchange ack to ACKNOWLEDGED / FILLED / PARTIAL /
  REJECTED / CANCELLED / EXPIRED / UNKNOWN (fail-closed;
  never infers FILLED). Covered by
  tests/test_execution_ack_12.py.

Phase 12 production changes (no new modules besides above):
- core/live/broker_engine.py: live route classifies every
  ack (FILLED only on fill evidence; PARTIAL/UNKNOWN halt
  via reconciler); executor exceptions clear transient
  state + halt (fail-closed); kill switch blocks ALL
  routing (dry + live); fill confirmation on position
  sighting / fetch-confirmed fill; ack_state +
  fill_confirmed + last_error state (reset-aware); journal
  persists ack_state + order_seq.
- core/execution/order_executor.py: deterministic client
  order ids (registry order_id, sanitized; monotonic
  fallback counter; no wall clock/UUID) + order_seq_value/
  reset_order_seq.
- core/live/reconciler.py: snapshot journal gains additive
  ack_state + order_seq keys (schema still v1; RAM-truth +
  30-bar cadence limitations classified, not removed).
- core/backtesting/accounting.py: directional_geometry_ok()
  + order_rr() canonical helpers (LONG stop<entry<target,
  SHORT target<entry<stop; finite-only; None on
  unmeasurable).
- core/setup/trade_setup_builder.py + core/risk/
  risk_engine.py: geometry gate before RR (inverted stops
  rejected); RiskEngine RR via order_rr().
- core/risk/account_state.py + core/risk/account.py:
  UTC day/ISO-week/month window keys +
  roll_pnl_windows()/roll_state_pnl_windows().
- core/risk/risk_engine.py: loss_limit_blocked() +
  per-candle enforcement of MAX_DAILY/WEEKLY/MONTHLY_LOSS
  (exact-equality blocks; non-finite blocks fail-closed).
  MAX_OPEN_POSITIONS stays structurally enforced by the
  single-position model (simulator slot + route guards),
  pinned by tests/test_risk_gates_12.py.
- backtesting/backtester.py: legacy scripted path gated
  (kill + geometry + RR; hand-injected orders can no
  longer bypass); pending fills blocked under kill
  (diagnostics still roll); NEXT_BAR_OPEN fills revalidate
  actual RR >= 6 BEFORE mutation (eroded fills refused,
  setup untouched).
- core/paper_trading/paper_trading_engine.py: kill blocks
  paper fills (management still runs).
- core/market_structure/swing.py + swing_engine.py +
  swing_registry.py: confirmed_bar stamp (index + right) +
  confirmed_as_of() embargo helper. Emission unchanged
  (rescan already guarantees confirmation); explicitness
  + adversarial tests added.
- data/candle_builder.py: load_history applies the same
  timestamp normalization as streaming (ms == s).
- data/historical_loader.py: paginated acquisition
  decrements by NEW candles (sparse-history under-fetch
  fixed).
- data/delta/delta_subscription_stream.py: per-symbol
  unrepaired-gap ranges (bounded) + gap_status()
  (CONTINUOUS vs DATA_GAP_UNREPAIRED) + deterministic
  repair_gaps() via injectable fetcher (normalize +
  validate + sort + dedupe; never fabricated, never
  merged into live builders).
- core/events/event_dispatcher.py: explicit maxlen (FIFO
  eviction + drop counter; normal operation never evicts).
- core/indicators/indicator_cache.py: documented retention
  (keys == registered names; series trimmed to window).
- core/analytics/performance.py: total_modeled_costs +
  cost_basis on every report ("gross theoretical" vs
  "friction-adjusted"; never executable, never OOS).
- requirements.txt: loguru pin removed (zero importers;
  orphan core/logger.py quarantined to
  _archive/core_logger_orphaned_phase12.py).
- data/websocket_client.py: classified LEGACY/DEPRECATED
  (single-symbol, no heartbeat); canonical feed is the
  multiplexed DeltaSubscriptionStream + 6D manager.

ORPHAN / RESEARCH-ONLY classification (no code wired to
fake integration -- Phase 12 §19):
- core/orderflow/ (delta/footprint/price-ladder):
  ORPHANED in production (price_ladder_stage has zero
  importers); live 11G order-flow research only.
- core/volume_profile/: ORPHANED (no pipeline consumer).
- Wyckoff / Fibonacci / confluence engine: RESEARCH-ONLY
  descriptive producers (core/research/features/); absent
  from the production strategy path by design in this
  phase (strategy expansion explicitly out of scope).
- Production strategy path (CONNECTED): indicators,
  trend, swing, structure, BOS/CHoCH, liquidity,
  displacement, FVG, order blocks (+lifecycle), breaker,
  mitigation, regime, setup/decision/execution/risk.

TERMINOLOGY: there are no top-level Phases 11H-11U. The
11G program ran sub-phases A-U (research/phase11g*,
docs/audit/phase11g_*.md); their negative/waiting
verdicts (L: no edge; M: holdout NO-GO; Q-U: data
insufficient) stand undisturbed by Phase 12.

SECURITY: .env untracked (verified); .env.example
keys-only (tested); logs/engine.log removed from tracking
(working file preserved, ignored); historical .env in
pre-hygiene commits NOT purged (operator decision) --
any credential that ever lived there must be treated as
compromised and rotated by the operator. Credential
rotation was NOT performed by Phase 12 (no authorized
mechanism exists in-repo).

Covered by: tests/test_execution_ack_12.py (23),
tests/test_risk_gates_12.py (25), tests/
test_confirmed_bar_12.py (9), tests/test_market_data_12.py
(8), tests/test_memory_bounds_12.py (4),
tests/test_security_12.py (6), plus fixture updates
proving the 1:6 gate on previously-sub-6:1 scripted
orders (hardening/contract/breakout/position suites).

============================================================
ADDENDUM — PHASE 13 (recertification; strategy frozen)
============================================================

Phase 13 changed NO thresholds, NO strategy logic, NO risk
limits. Two correctness hunks only: (1) execution-time
directional geometry gate in backtesting/backtester.py
(gap-through-target fills refused; gap-through-stop was
already unreachable via invalidate-first); (2) same gate
on the legacy paper execution_signal fallback in
core/paper_trading/paper_trading_engine.py. New tests:
tests/test_lookahead_13.py (3 boundaries x 3 futures),
SHORT-gap direct-drive tests + LONG gap tests in
tests/test_backtester_breakout.py, sign-adversarial class
in tests/test_trade_simulator.py, paper fixture migration
to 1:6-compliant geometry. Viability outcome B (LOW
EXECUTABLE OPPORTUNITY) is a reported research result,
not a defect backlog. Full suite 2849 green. See
docs/phase13_independent_recertification.md and
STATUS.md entry 146. EDGE = NOT ESTABLISHED. OOS =
ABSENT. LIVE = NO-GO.

============================================================
ADDENDUM — PHASE 14 (forensics; strategy frozen)
============================================================

Phase 14 changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics. Forensic analysis only,
plus one test file and one artifact:
tests/test_edge_forensics_14.py (22 tests: funnel
terminal-exclusivity, phantom-win classification, single
quantity multiplication, funding absence, VERIFIED/
ASSUMED/UNAVAILABLE cost scenarios, LONG/SHORT gap
boundaries at stop/target, OOS boundary integrity,
frozen-gate pins, safe-default posture);
research/results/phase14_executable_edge_forensics.json
(deterministic forensic record: all 25 Gate-A orders,
erosion distributions, cost scenarios, gate matrix;
byte-identical regeneration proven). Bar-mapping
correction recorded (entry bar = trigger_bar list index;
stamps agree exactly). Full suite 2849 green. See
STATUS.md entry 147. EDGE = NOT ESTABLISHED. OOS =
ABSENT. LIVE = NO-GO.

============================================================
ADDENDUM — PHASE 15 (readiness; strategy frozen)
============================================================

Phase 15 changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics, NO production files at all
(zero modified production/test files; one new test file).
Evidence-readiness audit only: Gate-A dataset classified
DIRECT_TARGET_VENUE-by-record with flat-bar caveat (92.6%
flat minutes); instrument/fees/funding/microstructure
readiness itemized (funding + microstructure UNAVAILABLE);
OOS infrastructure AVAILABLE (splitter/gate/protocol
frozen) with evidence ABSENT (no periods fabricated);
sample N=2 INSUFFICIENT; viability outcome B reaffirmed
from execution records (2 fills/5000 bars). New tests:
tests/test_researcher_15.py (33, all 25 mandated areas).
New artifact (deterministic, byte-identical regen):
research/results/phase15_evidence_readiness.json. Full
suite 2904 green. See STATUS.md entry 148. EDGE = NOT
ESTABLISHED. OOS = ABSENT. LIVE = NO-GO.

============================================================
ADDENDUM — PHASE 16 (readiness regression; strategy frozen)
============================================================

Phase 16 changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics, NO production files at all
(zero modified production/test files; one new test file +
one new research-only helper package). Readiness-regression
only: extracts the Phase-14/15 VERIFIED/ASSUMED/UNAVAILABLE
cost schedules and OOS sample-size math into the pure
deterministic core/research/readiness/ helpers
(sample_math + scenarios) and pins all 25 mandated areas
as regression. New tests:
tests/test_readiness_16.py (36). New helpers:
core/research/readiness/__init__.py + sample_math.py +
scenarios.py (research-only, no production imports).
Phase-14/15 artifacts untouched. Full suite 2940 green.
See STATUS.md entry 149. EDGE = NOT ESTABLISHED. OOS =
ABSENT. LIVE = NO-GO.

============================================================
ADDENDUM — PHASE 17 (acquisition + feasibility; strategy frozen)
============================================================

Phase 17 changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics, NO production files at all
(zero modified production/test files; one new test file +
one new research-only acquisition package + two operator
scripts). Acquisition/feasibility only: independent
fresh-data fetch strictly after Gate-A (11461 BTCUSDT 1m
bars, git-ignored cache) + deterministic provenance/
quality/feasibility helpers + OOS period budgeting (25k
bars/period, 0 adequate of 6 -> OOS_BLOCKED). New tests:
tests/test_oos_feasibility_17.py (27, 9 classes). New
helpers: core/research/acquisition/__init__.py +
provenance.py + quality.py + feasibility.py
(research-only, no strategy/execution imports). New
scripts: scripts/fetch_phase17_fresh.py +
scripts/build_phase17_artifact.py (read-only/deterministic).
New artifact (deterministic, byte-stable regen):
research/results/phase17_oos_feasibility.json.
Phase-14/15/16 artifacts untouched. New suite unittest
27/27 green. See STATUS.md entry 150. EDGE = NOT
ESTABLISHED. OOS = ABSENT. LIVE = NO-GO.

============================================================
ADDENDUM — PHASE 18 (genuine OOS validation; strategy frozen)
============================================================

Phase 18 changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics, NO production files at all
(zero modified production/test files; one new test file +
one new research-only validation package + one builder
script). Genuine OOS validation only: 6 independent
per-period frozen runs over 11461 fresh bars (OOS_01 2/0,
OOS_02 0/0, OOS_03 2/0, OOS_04 2+1P/0, OOS_05 8/0, OOS_06
0/0 orders/fills) + global continuous sanity (32 orders,
0 fills); 0 completed trades everywhere -> OOS_BLOCKED.
New tests: tests/test_oos_validation_18.py (30). New
helpers: core/research/oos_validation/__init__.py +
periods.py + execution.py + report.py (research-only).
New script: scripts/build_phase18_artifact.py
(deterministic). New artifact (deterministic, byte-stable
regen): research/results/phase18_oos_validation.json.
Phase-14/15/17 artifacts untouched. New suite unittest
30/30 green. See STATUS.md entry 151. EDGE = NOT
ESTABLISHED. OOS = BLOCKED (genuine execution, 0 trades).
LIVE = NO-GO.

============================================================
ADDENDUM — PHASE 19 (OOS data extension; strategy frozen)
============================================================

Phase 19 changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics, NO production files at all
(zero modified production/test files; one new test file +
one new research-only extension package + two scripts).
Data-extension only: merged 11461 prior bars + 438 new
Tier-A bars -> 11899 bars (1788601500->1789315380);
frozen 6 per-period + global runs still 0 fills
everywhere -> OOS_BLOCKED (DIRECT_OOS_DATA_LIMITATION).
New tests: tests/test_oos_data_extension_19.py (25
covering 29 areas). New helpers:
core/research/extension/__init__.py + extension.py
(research-only, stdlib-only). New scripts:
scripts/fetch_phase19_extension.py (read-only) +
scripts/build_phase19_artifact.py (deterministic). New
artifact (deterministic, byte-stable regen):
research/results/phase19_oos_data_extension.json.
Phase-14/15/17/18 artifacts untouched. New suite unittest
25/25 green. See STATUS.md entry 152. EDGE = NOT
ESTABLISHED. OOS = BLOCKED. LIVE = NO-GO.

============================================================
ADDENDUM - OOS EXECUTION READINESS (preregistration + gates;
strategy frozen, 9M untouched)
============================================================

Readiness-gating only (answers "are we ready to run the frozen
OOS experiment"; never executes it): DISCOVERY ->
PREREGISTRATION -> READINESS GATES -> (blocked) FROZEN
EXECUTION. Changed NO thresholds, NO strategy logic, NO risk
limits, NO execution semantics, NO production files at all
(zero modified production/test files; one new test file +
two new research-only readiness modules). New modules:
core/research/readiness/preregistration.py
(FrozenPreregistration, immutable, content_hash identity,
refuses 7E + production-ready) +
core/research/readiness/oos_execution_readiness.py
(GateVerdict, OOSExecutionReadinessReport, evaluate(),
observe_dataset(); 6175 contiguous-bar 11G-Q gate, 300000
fresh-bar frozen-protocol derivation at measured Gate-A
rates, 60-fill evidence gate; missing evidence stays
UNAVAILABLE/BLOCKED, never passes). New tests:
tests/test_oos_execution_readiness.py (28: immutability,
arithmetic, fixtures A-H, lookahead, isolation, real-data
BLOCKED). Real-data verdict on current caches (11899 bars,
0 fills, no venue schedules, OHLCV-only): OOS_EXECUTION_
READINESS = BLOCKED. 9M implementation/tests, historical
pins, and all research artifacts untouched. EDGE = NOT
ESTABLISHED. OOS = BLOCKED. LIVE = NO-GO.

============================================================
ADDENDUM - OOS TOP-UP ACQUISITION (public data only)
============================================================

Acquisition-only (answers "what fresh data genuinely exists";
never executes OOS): full post-Gate-A fetch + dedupe_merge
with the Phase-19 cache into NEW git-ignored
data/history/BTCUSDT_1m_oos_topup.json (provenance +
dataset identity via the Phase-19 construction).
Result: 11899 -> 29491 genuine post-boundary bars, 0
duplicates, gaps preserved, Phase-19 cache byte-untouched.
Economics observation fixture added (venue docs + MCP
corroboration: maker/taker PARTIAL, funding PARTIAL,
slippage/contract-value UNAVAILABLE; nothing provisioned).
Microstructure stays UNAVAILABLE (venue offers recent
trades only; history API is OHLC). Fills stay 0 (no
eligible hypotheses + frozen strategy yields none; nothing
simulated without a hypothesis). Readiness re-evaluated on
the top-up set: still BLOCKED (bars/fills/economics/
microstructure). New tests:
tests/test_oos_topup_acquisition.py (18). 9M, pins, and
research artifacts untouched. EDGE = NOT ESTABLISHED.
OOS = BLOCKED. LIVE = NO-GO.

============================================================
ADDENDUM - READINESS MONITOR (reuse-only handoff layer)
============================================================

Monitoring-only (no new gate math, no execution path):
run_monitor() reuses evaluate() then records a deterministic
ReadinessSnapshot (content_hash id; gaps from source
timestamps only: fresh gap 270509, fill gap 60 on current
caches) with classified blockers (DATA_TIME_BOUND,
NO_ELIGIBLE_HYPOTHESES, NO_FILLS, ECONOMICS_UNAVAILABLE,
MICROSTRUCTURE_UNAVAILABLE, REPOSITORY_FORENSIC_BLOCK)
and a terminal handoff (current: WAITING_FOR_DATA;
READY_FOR_OOS_EXECUTION only authorizes a separate task,
never executes). NO_NEW_SOURCE_DATA is normal; rows
without A-DIRECT provenance are refused as genuine. New:
core/research/readiness/monitor.py +
tests/test_readiness_monitor.py (21). 9M, pins, artifacts
untouched. EDGE = NOT ESTABLISHED. OOS = BLOCKED.
LIVE = NO-GO.

============================================================
END OF MANIFEST
============================================================

## LEVEL 4 RUNTIME R:R / EXIT POLICY AMENDMENT
- `core/risk/trading_policy.py`: global + exact-instrument runtime trading policy authority.
- Runtime bounds: inclusive 1:1 minimum through 1:20 maximum.
- Authenticated API: `GET/POST /risk-policy`, `POST /risk-policy/reset`.
- Browser dashboard exposes global/instrument policy controls.
- Trailing management is enabled by default at 1.0R activation / 0.5R distance and is overrideable per instrument.
- Explicit exit/book-profit and opposite-signal exit hooks are supported in the paper runtime; live trailing execution remains fail-closed pending venue contract evidence.
- Frozen research `MIN_RISK_REWARD=6.0` remains separate and unchanged.

============================================================
ADDENDUM - LEVEL 4 FOLLOW-UP / PAPER ECONOMICS CLOSURE
============================================================

`PaperTradingEngine` now consumes `core.risk.costs.paper_cost_profile()` for
actual fill commission/slippage. This closes the previously documented paper
runtime split-brain between readiness reporting and fill accounting. The
shared `TradeSimulator.open_trade()` remains the post-cost R:R choke. Runtime
trading policy remains inclusive 1:1 minimum through 1:20 maximum, with exact
instrument overrides and trailing management configurable through the
authenticated policy surface. Explicit fill-price slippage remains separate
from round-trip accounting slippage. A missing `.vscode/mcp.json` in the ZIP
snapshot was restored in the testnet-only server/env form; no credential
material is stored. Affected regression is 148/148 PASS; secondary
research/readiness/MCP suite is 119/119 PASS; compileall PASS. Historical
forensic digest pins are intentionally not re-pinned. Global venue rollover /
server-recovery evidence remains externally blocked; PRODUCTION_READY remains
FALSE.

## PHASE 24 — DELTA MCP PUBLIC OBSERVATION NORMALIZATION

Status: Active research integration. Normalizes public MCP observations for products, tickers, order books, trades, candles, mark price, funding, open interest, settlements, options, indices, and reference data. The adapter is intentionally downstream of capture and does not establish independent venue authenticity. Production execution does not consume MCP observations.

### Phase 27 — Delta MCP → 9J Discovery Context

Delta MCP public evidence normalized into 9I is now visible to the existing 9J discovery report as a deterministic research-context summary. The context is informational only: it does not invent hypotheses, alter candidate generation, bypass walk-forward/OOS gates, or certify venue authenticity. `venue_authentication` remains `UNVERIFIED` until independent external evidence is obtained.

============================================================
PHASE 28 — DELTA MCP → 9K REGIME/CONDITIONING CONTEXT
============================================================

`research/integrations/delta_mcp_regime_context.py` is a research-only
readback boundary for Phase 9K. It summarizes which Delta MCP public domains
are available for contextual conditioning evidence, but it never maps those
observations directly into 9K regime labels. Existing 9K detector labels,
minimum-sample gates, chronological walk-forward validation, multiple-testing
correction, and robustness semantics remain authoritative and unchanged.

The 9K engine adds deterministic context limitations only. Venue
authentication remains UNVERIFIED and the MCP context cannot bypass 9K, 9M,
OOS, or production-readiness gates.

### PHASE 30 — FRESH GENUINE OOS EVIDENCE ACCUMULATION

Phase 30 records a fresh deterministic replay of the existing direct Delta BTCUSDT 1m post-Gate-A dataset through the frozen OOS execution seam. Six chronological periods produced 21 orders and 3 completed trades (1 win, 2 losses), with no period meeting the 10-trade settling gate. This is evidence accumulation only; no 9L hypothesis was invented or promoted, the locked 9M sample gates remain unmet, and `production_ready` remains false. Artifact: `research/results/phase30_oos_evidence_accumulation.json`.

### PHASE 33 — DETERMINISTIC CURRENT OOS READINESS SNAPSHOT

Phase 33 adds a deterministic operator-readable snapshot over the existing
OOS acquisition cache. It reuses the established readiness monitor and quality
audit rather than creating a second gate system. The snapshot binds the exact
30,247-row direct Delta BTCUSDT 1m dataset and row-provenance identity, reports
30,247/300,000 fresh-bar readiness and 3/60 fill readiness, exposes 185 missing
1-minute intervals, and keeps all data-quality limitations visible. No new
hypothesis is selected, no OOS execution is started, and production readiness
remains false. Artifact:
`research/results/phase33_oos_readiness_snapshot.json`.


## PHASE 34 — DETERMINISTIC OOS ACQUISITION ANCHOR

- OOS acquisition now requires an explicit `--end-timestamp` anchor; the operator no longer derives its request span from wall-clock time.
- `HistoricalLoader.candles_paginated()` accepts an optional deterministic `end_timestamp` while preserving historical behavior for existing callers that omit it.
- No gap filling, interpolation, provenance weakening, or production execution is introduced.
- Current genuine OOS evidence remains unchanged: 30,247 fresh bars and 3 completed fills; 9M remains `OOS_BLOCKED`.
- Phase 34 is research-only; `is_production_ready` remains permanently `False`.
- Full repository certification remains unavailable in this ZIP snapshot because historical Phase-17 fixtures are absent and frozen historical identity/artifact-byte assertions remain unresolved.


## PHASE 35 — MULTI-SYMBOL OOS EVIDENCE COVERAGE

Phase 35 adds a deterministic research-only per-symbol coverage audit. Rows are attributed to a symbol only when explicit row-level symbol metadata exists; filenames are never used to synthesize symbol evidence. The current 30,247-row OOS candle cache contains 30,247 rows without explicit symbol fields, so cross-symbol coverage is UNAVAILABLE. No universal validation claim is made. Production readiness remains permanently FALSE.

## PHASE 36 — PROVENANCE-BOUND SYMBOL COVERAGE

Phase 36 extends the Phase-35 multi-symbol evidence audit without changing
its conservative semantics. Explicit row metadata remains authoritative when
present; when a provenance sidecar is supplied, symbol attribution is allowed
only if row timestamps are exactly covered by the bound provenance records.
Conflicting or incomplete provenance fails closed. The current 30,247-row OOS
cache is therefore attributable to BTCUSDT from row-level provenance, not from
its filename, but no additional symbol evidence exists and universal/cross-
symbol validation remains unavailable. Artifact:
`research/results/phase36_provenance_symbol_coverage.json`. Production
readiness remains permanently false.

### Phase 37 — Multi-symbol OOS acquisition

Research-only multi-symbol acquisition manifest added. Per-symbol row/provenance identities remain separate; cross-symbol timestamp overlap is permitted because timestamps are instrument-scoped. Current evidence remains BTCUSDT-only and therefore cross-symbol validation is unavailable.

### Phase 38 — Multi-symbol OOS aggregation

Phase 38 adds a deterministic cross-symbol evidence aggregation seam. Symbol namespaces remain independent, missing symbols remain unavailable, and no cross-symbol claim is emitted without the configured symbol evidence.

### Phase 39 — Frozen preregistration reload integrity

The frozen OOS preregistration artifact now has a deterministic fail-closed rehydration path. Persisted hypothesis records are reconstructed through the existing `HypothesisRecord` authority, the frozen preregistration identity is rechecked by the existing canonical content hash, and production readiness remains permanently false. No new research/discovery architecture was introduced.

## PHASE 43 — RESEARCH BOUNDARY + FROZEN 9L→9M HANDOFF

The 9L report now has a full-content deterministic identity and strict persisted reload. Supported 9L findings can be admitted only through an explicit `NineLSelection`, then converted into the existing immutable `FrozenPreregistration`. The 9M engine exposes `run_preregistered()` as the frozen execution seam and refuses dataset, protocol, identity, or hypothesis-order drift. A source-level import audit protects the research boundary from production runtime imports. No automatic hypothesis selection, promotion, order submission, ledger mutation, or production-readiness transition is possible.

### Phase 56 — deterministic OOS builder hardening
The Phase-17 OOS artifact builder was hardened so artifact construction cannot
silently acquire venue metadata over the network. Product metadata must already
exist as the declared snapshot input. Missing evidence blocks the build rather
than fabricating or replacing provenance. Production readiness remains false.

### Phase 57 — explicit product snapshot acquisition
The Phase-17 venue metadata acquisition boundary is now explicit. Network
access is isolated to a dedicated research-only operator; deterministic OOS
artifact construction remains offline. Missing or ambiguous BTCUSDT product
evidence fails closed and no production authority is created.

### Phase 58 — phase continuity / loss-prevention audit
The checkpoint includes a source-backed continuity manifest for phases 44-57.
Missing historical artifacts are explicitly marked rather than inferred.
`research/results/phase58_phase_continuity.json` is the authority for recovery
status; source and executable tests outrank narrative summaries.


### Phase 59 — phase-continuity restoration + recovery checkpoint

Restored source-backed Phase-47 journal persistence and Phase-48 deterministic 9A discovery capture using the existing ResearchRepository/Backtester/ResearchJournal architecture. Preserved Phase-49 as missing genuine evidence and created an honest Phase-55 recertification boundary artifact. Added `research/results/phase59_continuity.json` as the authoritative continuity manifest. Production readiness remains false.

## PHASE 60 — PHASE 44–57 CONTINUITY LOCK

Added a deterministic continuity-lock test and artifact covering the durable
9L/9M and OOS work from Phases 44–57. Phase 49 remains explicitly missing
because its original genuine artifact/data is unavailable; no reconstruction
is claimed. Production readiness remains FALSE.
