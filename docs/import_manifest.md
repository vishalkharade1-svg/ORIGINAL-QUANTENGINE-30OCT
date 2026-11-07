# ============================================================
# QuantEngine
# IMPORT MANIFEST
# ============================================================

Architecture Version : 1.0.4

Status : ACTIVE

Last Updated : 2026-08-30 (Phase 5A-D, 6A-B: canonical entry routing, isolated execution comparison, dynamic product discovery + market universe, STATUS 110; 
           Phase 6C: canonical setup identity + multi-symbol scanning, STATUS 111; Phase 6D: real-time multi-symbol subscriptions, STATUS 112; Phase 6E: real-time        
           closed-candle integration, paper mode, STATUS 113; Phase 7: breakout directional asymmetry research, STATUS 114; Phase 7E: real-data out-of-sample causal      
           validation, STATUS 115; Phase 8: portfolio risk & capital coordination, STATUS 116; Phase 8B: shared portfolio capital & allocation, STATUS 117; Phase 9A-9O: 
           research readback + experiment stack, STATUS 118-132; Phase 9P-a: 
           canonical multi-symbol RealTimeEngine wired into main.py via core/runtime/paper_main.py, STATUS 133; Phase 9P-b: account profit factor / expectancy reporting  
            from the canonical completed-trade ledger, STATUS 134; Phase 9P-c: canonical runtime analytics / account reporting attach-point, STATUS 135; Phase 9P-d: live liquidity / history provider plumbing feeding the canonical 6B eligibility cascade, STATUS 136; Phase 9P-e: provider-universe live smoke / verification harness, STATUS 137; Phase 9P-f: paper control & monitoring API, STATUS 138; Phase 9P-g: production PAPER entrypoint integration, STATUS 139; Phase 9P-h: lightweight desktop control client, STATUS 140; Phase 9P-i: integration & operational hardening / runbook, STATUS 141)

============================================================

PURPOSE

This document records every production module and the
modules it imports.

Before modifying ANY file this document MUST be updated.

No code change may be made without checking import impact.

============================================================
CONFIG
============================================================

config/settings.py

Imports

dotenv

os

pathlib

Imported By

Entire Project

============================================================
DATA
============================================================

data/websocket_client.py

Imports

json

websockets

config.settings

core.events.event_bus

core.events.event_types

core.events.candle_event

core.market_state

data.candle_builder

------------------------------------------------------------

data/candle_builder.py

Imports

collections

dataclasses

datetime

core.bars.bar

core.bars.bar_series

------------------------------------------------------------

data/historical_loader.py

Imports

time

httpx

core.common.logging_config

============================================================
EXCHANGES
============================================================

core/exchanges/base_contract.py

Imports

dataclasses

------------------------------------------------------------

core/exchanges/base_exchange.py

Imports

abc

------------------------------------------------------------

core/exchanges/contract_registry.py

Imports

None

------------------------------------------------------------

core/exchanges/exchange_registry.py

Imports

None

------------------------------------------------------------

core/exchanges/delta/delta_contract.py

Imports

core.exchanges.base_contract

------------------------------------------------------------

core/exchanges/delta/delta_products.py

Imports

core.exchanges.delta.delta_rest

------------------------------------------------------------

core/exchanges/delta/delta_rest.py

Imports

httpx

------------------------------------------------------------

core/exchanges/delta/delta_history.py

Imports

datetime

core.exchanges.delta.delta_rest

core.history.candle_mapper

------------------------------------------------------------

core/exchanges/delta/delta_mapper.py

Imports

core.exchanges.delta.delta_contract

------------------------------------------------------------

core/exchanges/delta/delta_contract_loader.py

Imports

core.exchanges.contract_registry

core.exchanges.delta.delta_products

core.exchanges.delta.delta_mapper

------------------------------------------------------------

core/exchanges/delta/delta_exchange.py

Imports

config.settings

core.exchanges.base_exchange

core.exchanges.delta.delta_auth

core.exchanges.delta.delta_products

------------------------------------------------------------

core/exchanges/delta/delta_auth.py

Imports

hashlib

hmac

json

time

urllib.parse

httpx

=====================================================================
EVENTS
=====================================================================

core/events/event.py

Imports

dataclasses

------------------------------------------------------------

core/events/candle_event.py

Imports

dataclasses

core.events.event

core.events.event_types

core.history.candle

------------------------------------------------------------

core/events/event_bus.py

Imports

core.events.event_dispatcher

------------------------------------------------------------

core/events/event_dispatcher.py

Imports

collections

------------------------------------------------------------

core/events/event_types.py

Imports

None

============================================================
PIPELINE
============================================================

core/pipeline/pipeline_context.py

Imports

collections

dataclasses

typing

core.market_state

core.risk.account_state

------------------------------------------------------------

core/pipeline/institutional_pipeline.py

Imports

core.breaker.breaker_engine

core.common.logging_config

core.displacement.displacement_scanner

core.events.event_types

core.execution.execution_engine

core.fvg.fvg_scanner

core.indicators.adx

core.indicators.atr

core.indicators.ema

core.indicators.indicator_engine

core.indicators.rsi

core.liquidity.liquidity_pool_engine

core.liquidity.liquidity_target_engine

core.market_structure.bos_engine

core.market_structure.choch_engine

core.market_structure.engine

core.market_structure.structure_engine

core.market_structure.swing_engine

core.mitigation.mitigation_engine

core.order_blocks.order_block_lifecycle_engine

core.order_blocks.order_block_scanner

core.pipeline.pipeline_debugger

core.pipeline.pipeline_statistics

core.regime.regime_engine

core.risk.risk_engine

core.setup.decision_engine

core.setup.trade_setup_builder

core.trend.trend_engine

============================================================
INDICATORS
============================================================

core/indicators/indicator_engine.py

Imports

core.common.base_engine

core.indicators.indicator_cache

core.common.logging_config

------------------------------------------------------------

core/indicators/indicator.py

Imports

abc

------------------------------------------------------------

core/indicators/ema.py

Imports

core.indicators.indicator

------------------------------------------------------------

core/indicators/atr.py

Imports

core.indicators.indicator

------------------------------------------------------------

core/indicators/adx.py

Imports

core.indicators.indicator

------------------------------------------------------------

core/indicators/rsi.py

Imports

core.indicators.indicator

============================================================
MARKET ANALYSIS
============================================================

core/trend/trend_engine.py

Imports

core.common.base_engine

core.trend.trend_state

core.trend.trend_score

core.common.logging_config

------------------------------------------------------------

core/market_structure/engine.py

Imports

core.common.base_engine

core.enums

core.market_structure.state

------------------------------------------------------------

core/market_structure/swing_engine.py

Imports

core.common.base_engine

core.market_structure.swing

core.market_structure.swing_registry

core.market_structure.swing_metrics

core.scoring.swing_score_engine

------------------------------------------------------------

core/liquidity/liquidity_pool_engine.py

Imports

core.common.base_engine

core.liquidity.liquidity_pool

core.liquidity.liquidity_ranker

------------------------------------------------------------

core/liquidity/liquidity_target_engine.py

Imports

core.common.base_engine

core.liquidity.liquidity_target

------------------------------------------------------------

core/displacement/displacement_scanner.py

Imports

core.common.base_engine

core.displacement.displacement

core.displacement.displacement_registry

core.displacement.displacement_score

core.common.logging_config

------------------------------------------------------------

core/fvg/fvg_scanner.py

Imports

core.common.base_engine

core.fvg.fair_value_gap

core.fvg.fvg_registry

core.fvg.fvg_score

------------------------------------------------------------

core/order_blocks/order_block_scanner.py

Imports

core.common.base_engine

core.order_blocks.order_block

core.order_blocks.order_block_registry

core.order_blocks.order_block_score

core.common.logging_config

============================================================
STRATEGY
============================================================

core/regime/regime_engine.py

Imports

core.common.base_engine

core.regime.regime_state

------------------------------------------------------------

core/setup/trade_setup_builder.py

Imports

core.common.base_engine

core.setup.setup_candidate

------------------------------------------------------------

core/setup/decision_engine.py

Imports

core.common.base_engine

core.setup.trade_setup_registry

core.setup.setup_rejection

============================================================
EXECUTION
============================================================

core/execution/execution_engine.py

Imports

core.common.base_engine

core.common.logging_config

------------------------------------------------------------

core/execution/order_executor.py

Imports

time

core.exchanges.delta.delta_exchange

============================================================
SIMULATION
============================================================

core/backtesting/trade_simulator.py

Imports

core.backtesting.trade

core.backtesting.trade_registry

------------------------------------------------------------

core/risk/risk_engine.py

Imports

config

core.common.base_engine

core.common.logging_config

core.risk.order_intent

core.risk.position_sizer

------------------------------------------------------------

core/risk/account.py

Imports

core.risk.account_state

------------------------------------------------------------

risk/portfolio_risk.py

Imports

None

============================================================
BACKTESTING
============================================================

backtesting/backtester.py

Imports

config

core.events.candle_event

core.risk.account

------------------------------------------------------------

backtesting/portfolio_backtester.py

Imports

backtesting.backtester

core.backtesting.trade_simulator

core.events.event_bus

------------------------------------------------------------

backtesting/logger.py

Imports

None

============================================================
PAPER TRADING  (STATUS 92)
============================================================

core/paper_trading/paper_trading_engine.py

PaperTradingEngine -- feed-driven paper trading that reuses
the canonical institutional pipeline end-to-end with no
exchange credentials. Drives the pipeline explicitly (pipeline
first), then fills the RiskEngine OrderIntent via the shared
TradeSimulator, manages SL/TP, and books accounted P&L --
the exact Backtester execution flow.

Imports

config

core.backtesting.trade_simulator

core.events.candle_event

core.events.event_types

core.risk.account

============================================================
LIVE TRADING  (STATUS 93)
============================================================

core/live/broker_engine.py

BrokerEngine -- live trading consumer. Drives the same
pipeline-first flow, routes the RiskEngine OrderIntent to the
real Delta exchange through a DeltaOrderExecutor, tracks the
open position from exchange positions, and books closed P&L
into the shared TradeRegistry + Account. dry_run=True (the
default) records would-be intents and manages a paper position
through the same TradeSimulator -- zero exchange writes.

Imports

config

core.backtesting.trade

core.backtesting.trade_registry

core.backtesting.trade_simulator

core.common.logging_config

core.events.candle_event

core.events.event_types

core.risk.account

============================================================
PERFORMANCE ANALYTICS  (STATUS 94)
============================================================

core/analytics/performance.py

PerformanceAnalytics / PerformanceReport -- the analytics layer
over the SHARED TradeRegistry + Account every execution mode
(Backtest, Paper, Live Broker) books into. Computes trade
statistics, profit factor, expectancy, payoff ratio, direction
breakdown, streaks, trade-based Sharpe/Sortino, the trade-based
equity curve, and peak-equity drawdown. The documented reader
of backtest_result/portfolio (see PIPELINE_CONTEXT_OWNERSHIP).

Imports

core.backtesting.trade_registry

============================================================
PORTFOLIO MANAGER  (STATUS 95)
============================================================

risk/portfolio_risk.py

PortfolioRiskManager -- the SHARED portfolio risk object
(extended in place, no duplicate class) wired by
backtesting/portfolio_backtester.py into every per-symbol
Backtester via its portfolio_gate / portfolio_release hooks.
Three layers of portfolio control, all default-off and fully
backward compatible:

max_portfolio_risk / max_positions  -- legacy dollar-risk pool
  + position count (unchanged semantics).

max_portfolio_allocation / max_per_symbol_allocation -- open
  notional (locked against OrderIntent.position_value) as a
  percentage of current equity, tracked per symbol so a close
  releases exactly its own exposure via Trade.symbol.

daily_loss_limit -- once realized PnL lags starting_balance by
  the limit, every order is gated; wins restore equity and
  re-enable trading.

Equity = starting_balance + realized_pnl (realized fed from the
closed Trade.pnl by the backtester release). reset() clears
every piece of state per run().

Supporting enrichment: core/backtesting/trade.py now carries
symbol (populated from OrderIntent.symbol by
core/backtesting/trade_simulator.py open_trade) so the release
hook can free the exact per-symbol exposure and equity.

Imports

None (stdlib only)

Portal wiring

Backtester.portfolio_gate(order) -> PortfolioBacktester._portfolio_gate
passes order.symbol / order.position_value / risk;
Backtester.portfolio_release(closed) -> _portfolio_release passes
Trade.symbol / Trade.pnl.

============================================================
PERFORMANCE DASHBOARD  (STATUS 96)
============================================================

core/dashboard/dashboard.py

PerformanceDashboard -- a pure DISPLAY layer over the SHARED
PerformanceReport the analytics layer produces (STATUS 94).
Reads only that report and the closed trade sequence; nothing
is recomputed and no new state object exists, so the console
block, the ASCII equity curve, the trades table and the CSV
export can never disagree with the metrics any mode prints.

render(report, label)          -- aligned stat block (adds the
  rows the analytics summary omits: peak equity, gross p/l,
  avg PnL %, returns std, W/L streaks).
render_equity_curve(report)    -- ASCII log-line chart of the
  trade-based equity curve with peak/trough scale and an exit-
  time timeline; "No closed trades" notice on an empty report.
render_trades(report, trades, limit) -- recent-trades table
  over the analytics closed-only view (open trades excluded).
export_csv(trades, path=None)  -- exit-ordered CSV of the
  closed trades (symbol, direction, entry, exit, entry/exit
  time, bars_held, pnl, pnl_percent, commission, slippage,
  result); returns the CSV text, or the written path.

Imports

core.analytics.performance

core.backtesting.trade_registry

============================================================
VALIDATION LAYER  (STATUS 97)
============================================================

core/validation/walk_forward.py

WalkForwardTester / WalkForwardFold / WalkForwardResult --
rolling out-of-sample evaluation over the canonical
Backtester. The caller's runner(bars, config) -> (account,
trades) replays any slice through the real flow; each fold
optionally picks the best `candidates` config on its train
window by an in-sample metric (net_profit / sharpe read off
the SHARED PerformanceAnalytics report) and validates it on
the immediately following never-seen test window. Fold ranges
advance by `step`; no engine state is shared across folds.

Imports

core.analytics.performance

------------------------------------------------------------

core/validation/monte_carlo.py

MonteCarloSimulator / MonteCarloResult -- bootstrap resampling
(WITH replacement) of a closed-trade PnL sequence from ANY
mode (TradeRegistry or sequence; open trades excluded).
Each simulation re-walks the equity curve from the starting
balance (Random(seed+index) -> fully deterministic under a
seed) and records final profit and peak-to-trough drawdown.
Result: mean / P25 / P50 / P95 / worst profit, mean & P95
drawdown (+% of balance), survival rate (never hit 0), the
raw sample list, and a console summary().

Imports

core.backtesting.trade_registry

------------------------------------------------------------

core/validation/optimizer.py

StrategyOptimizer / OptimizationRun -- cartesian grid sweep
over a strategy parameter space. For every combination it
invokes runner(bars, params) -> (account, trades) then ranks
by a PerformanceAnalytics metric (net_profit / sharpe /
profit_factor / win_rate); `best` is the top row. Run objects
expose net_profit, sharpe, total_trades, max_drawdown,
win_rate + the full metrics dict. Grids capped by max_combos.

Imports

core.analytics.performance

============================================================
POSITION MANAGER  (STATUS 98)
============================================================

core/risk/position_manager.py

PositionManager -- execution-layer hygiene over the SHARED
OrderIntent + SHARED Trade objects. Deliberately the INVERSE
of the archived legacy position_manager (which owned its own
Position + SL/TP state and was quarantined under the
No-duplicate-classes rule); the live manager keeps NO state
of its own and reads every position from exactly where the
architecture puts it (TradeSimulator.current_trade / registry).

Two responsibilities, both stateless / read-only:

1. Order refinement, applied by TradeSimulator.open_trade for
   EVERY mode (Backtest / Paper / Live Broker), so all book
   the same corrected quantity at the single choke point:
   round to QUANTITY_PRECISION decimals; cap notional at
   MAX_ALLOCATION_PER_TRADE (scaling quantity down) and
   optionally LEVERAGE * equity (manage_into); drop dust --
   any quantity below MIN_QUANTITY invalidates the order
   (quantity -> 0, no trade opens). manage()/audit() are pure:
   OrderIntents go through dataclasses.replace, non-dataclass
   order shapes (the paper _SlippageAdjustedOrder) through the
   pure _ManagedOrder attribute-adapter; the SetupCandidate
   fallback (no quantity/entry) passes through unchanged.
   audit() returns (corrected, reasons) for observability.
   Idempotent; the input is never mutated.

2. Position reading (display only -- SL/TP management stays in
   TradeSimulator.update): unrealized(trade, price) and
   snapshot(trade, price) give the open Trade's value /
   unrealized PnL / percent / WIN|LOSS|FLAT at a market price.

config additions (config/risk_settings.py): QUANTITY_PRECISION
= 8, MIN_QUANTITY = 1e-6; MAX_ALLOCATION_PER_TRADE / LEVERAGE
pre-existed and are now enforced at the choke point too.

Imports

config.risk_settings

core.risk.order_intent

TradeSimulator (core/backtesting/trade_simulator.py) now adds

core.risk.position_manager

=============================================================
EXECUTION LIFECYCLE  (STATUS 99)
============================================================

The Phase 4C fix for the duplicate "EXECUTION SIGNAL" replay
logs and the OVER-ORDERING / duplicate-fill defect. Root cause:
InstitutionalPipeline already registers one ExecutionEngine in
__init__; the layer scripting pipelines (tests/test_backtester.py
and 7 examples) appended a SECOND via register(), and because
register() deduplicated by object identity -- not name -- the
pipeline ran [DecisionEngine, ExecutionEngine, ExecutionEngine,
RiskEngine], so every accepted setup was order-emitted twice.
Deeper still, a SetupCandidate had NO identity: the same order
block + prices were re-created as a fresh object every bar and
re-ordered bar after bar, and the backtester filled whatever
context.execution_signal said, with no consume-once guard.

Enforced invariant: ONE SETUP ID == ONE PRIMARY ORDER == ONE
PRIMARY TRADE.

core/execution/order_registry.py  (NEW)

Persistent, cross-cycle source of truth (lives on PipelineContext
like AccountState; NOT cleared by reset_cycle, re-created on
reset()). States NEW -> PENDING -> FILLED | CANCELLED | REJECTED |
EXPIRED. create() mints order_id "[setup_id]-ORDER-N" and is
duplicate-proof (one primary order per setup_id); advance() ages
pending orders and EXPIRES any that wait beyond MAX_WAIT_BARS;
mark_filled() consumes a PENDING order exactly once and mints the
trade_id "[order_id]-TRADE-N" onto order + Trade. has_order_for_setup()
is the single dedupe oracle.

Imports

config.risk_settings

Identity chain

core/setup/trade_setup_builder.py now stamps setup_id on each
candidate: "[symbol]-[timeframe]-[direction]-OB-[index]-
[entry]-[stop]-[target]" (the OrderBlock index is stable across
bars, so re-scanning the same block+economies reuses the id).
core/setup/setup_candidate.py carries setup_id + lifecycle.
core/setup/decision_engine.py logs SETUP_ACCEPTED at most once
per setup_id per run and moves the setup to lifecycle ACCEPTED.

core/execution/execution_engine.py is now idempotent: it clears
context.execution_signal (no re-emission) the moment its selected
setup already has a registry order -- the earliest possible guard.

core/risk/risk_engine.py is the canonical ORDER + signal emit
point: it re-checks has_order_for_setup (belt + braces), stamps
setup_id onto the OrderIntent, then ORDER_CREATED and
EXECUTION_SIGNAL (both with setup_id + order_id) after the
registry.create() -- the user-required ordinal sequence. Setup
lifecycle -> ORDER_CREATED. The legacy free-text ORDER /
EXECUTION SIGNAL logs were replaced.

core/pipeline/institutional_pipeline.py register() now dedupes BY
NAME (one engine per stage), so a second register(ExecutionEngine())
is a no-op instead of a duplicate stage.

core/backtesting/trade_simulator.py carries setup_id/order_id onto
the open Trade and, at the single close choke point shared by
Backtest / Paper / Live, logs TRADE_CLOSED with the full identity
chain. core/backtesting/trade.py gained setup_id/order_id/trade_id.

backtesting/backtester.py:
  - consume-exactly-once: an order fills only while registry
    PENDING; FILLED/terminal orders can never fill again.
  - entry validation: fills only when the candle trades through
    the entry (candle.low <= entry <= candle.high, inclusive).
  - persistent limit-order model: a PENDING order fills on the
    FIRST candle that touches its entry, even a later one; a
    working order with no touch EXPIRES after MAX_WAIT_BARS
    (ORDER_EXPIRED log) and is permanently unfillable.
  - ORDER_FILLED logged with setup_id/order_id/trade_id.

core/paper_trading/paper_trading_engine.py and core/live/
broker_engine.py consume PENDING orders through the SAME registry
(mark_filled + ORDER_FILLED), so Paper and Live share the exact
Backtest lifecycle and cannot double-fill either.

Identity is carried onto the Trade (TradeSimulator.open_trade) and
completed by OrderRegistry.mark_filled (trade_id mint), so a booked
trade always answers setup_id / order_id / trade_id.

config additions (config/risk_settings.py): MAX_WAIT_BARS = 30
(default pending-order expiry horizon; OrderRegistry overrides it).

Removed duplicate ExecutionEngine registration + unused imports:
tests/test_backtester.py and examples/test_validation.py,
test_position_manager.py, test_portfolio_backtester.py,
test_performance_dashboard.py, test_performance_analytics.py,
test_paper_trading.py, test_live_broker.py.

New imports introduced:

core/execution/order_registry.py : config.risk_settings
backtesting/backtester.py         : core.execution.order_registry
core/paper_trading/paper_trading_engine.py
                                 : core.common.logging_config,
                                   core.execution.order_registry
core/live/broker_engine.py        : core.execution.order_registry
core/pipeline/pipeline_context.py : core.execution.order_registry
                                   (lazy, _new_order_registry)
core/setup/decision_engine.py     : core.common.logging_config
core/backtesting/trade_simulator.py
                                 : core.common.logging_config

New test surface: tests/test_execution_lifecycle.py (19 tests)
against core.execution.order_registry, the idempotent engines, the
name-dedupe and the backtester fill/expiry/identity contracts.

===========================================================
PENDING ORDER INTEGRITY  (STATUS 100)  -- Phase 4D
===========================================================

Bar-anchored pending-order lifecycle (fill / invalidation /
expiration integrity). Until now the pending-order expiry was
CALL-COUNT based, not BAR based: OrderRegistry.advance() bumped
wait_bars on the SAME candle that created the order (a brand new
order counted as already "old"), expiry ran BEFORE the candle's
fill check (an order whose entry was touched on its expiry candle
expired without the chance to fill), orders could fill on the
creation candle using that candle's own intrabar range (a same-
candle look-ahead: the signal exists only at the candle's close),
and there was NO invalidation state -- a structural stop breach
was indistinguishable from an expiration. Phase 4D replaces this
with explicit bar metadata and a documented per-candle ordering.

Per-order bar metadata (core/risk/order_intent.py):

    created_bar / created_timestamp   stamped by registry.create
    eligible_from_bar = created_bar + ENTRY_DELAY_BARS (default 1)
    expires_at_bar     = eligible_from_bar + MAX_WAIT_BARS
    filled_bar / terminal_bar / waited_bars
    min_price_since_creation / max_price_since_creation
        (Phase 4D fields -- SUPERSEDED by Phase 4E's lifetime
        excursion in core/risk/order_intent.py: see the
        ECONOMIC SETUP DEDUPLICATION / STATUS 101 section below)

core/execution/order_registry.py:
  - create(order, bar=None, timestamp=None): stamps the
    eligibility window once, at first registration.
  - advance(bar=None, timestamp=None): EXPIRES a PENDING order
    only when bar >= expires_at_bar (bar-anchored). Barless calls
    keep the legacy counter mode for scripted registry unit tests.
  - invalidate(order, reason, bar, price, level): PENDING ->
    INVALIDATED (new terminal state, distinct from EXPIRED -- a
    thesis break is NOT an expiration). Setup lifecycle inherits
    INVALIDATED.
  - New filter helpers expired() / invalidated().

backtesting/backtester.py per-candle order (Phase 4D STEP 4):
  1. update pending   -- roll min/max price since creation
  2. skip ineligible  -- bar < eligible_from_bar (no same-candle
                        look-ahead; legacy scripted orders without
                        an order_id stay same-candle by contract)
  3. invalidation     -- bullish order invalidates when
                        candle.low <= stop_loss (bearish:
                        candle.high >= stop_loss); on a candle that
                        BOTH breaks the stop and reaches the entry,
                        invalidation wins (conservative) -> ORDER_
                        INVALIDATED log with reason / price /
                        invalidation_level
  4. entry reached    -- low <= entry <= high (inclusive)
  5. fill             -- exactly once via mark_filled, at most one
                        per candle (single-position model) ->
                        ORDER_FILLED log now carries created_bar /
                        filled_bar / waited_bars / entry /
                        candle_low / candle_high (proving the fill)
  Expiry is the LAST step of the candle: advance(bar) runs AFTER
  the fill/invalidation checks, so the expiry candle is still the
  fill's last chance. ORDER_EXPIRED log now carries setup_id /
  order_id / created_bar / eligible_from_bar / expired_bar /
  waited_bars / max_wait_bars / entry / min_low_since_creation /
  max_high_since_creation / bars_pending /
  entry_distance_from_nearest_price (Phase 4E field set; the Phase
  4D min/max_price_since_creation fields are REMOVED).

core/execution/execution_engine.py (Phase 4D STEP 8): emits the
ranked batch of accepted setups (top MAX_PENDING_ORDERS by score,
tie-broken by registration order, then capped by the registry's
remaining pending slots, skipping every already-ordered setup) as
context.execution_signals; context.execution_signal remains the
best of the batch for legacy consumers.

core/risk/risk_engine.py (Phase 4D STEP 8): order-mints ONE order
per emitted signal, subject to (a) the one-setup == one-order
registry re-check, (b) the MAX_PENDING_ORDERS slot cap, and (c)
the MAX_TOTAL_EXPOSURE_PCT aggregate-notional ceiling against
current equity (ORDER_SKIPPED_EXPOSURE info log when capped;
accepted setups are never silently discarded -- they queue).
Produces context.orders (list) + context.order (first).

core/pipeline/pipeline_context.py declares execution_signals and
orders (slots=True) and clears them in reset_cycle() / reset().

config/risk_settings.py additions: ENTRY_DELAY_BARS = 1,
MAX_PENDING_ORDERS = 8, MAX_TOTAL_EXPOSURE_PCT = 25.0. The
MAX_WAIT_BARS doc now defines the bar-anchored window.
MAX_PENDING_ORDERS is an execution-CAPACITY default: 8 slots with
~2.5x-equity natural notional per order; MAX_TOTAL_EXPOSURE_PCT
must clear the full slot capacity to stay a runaway-pending
backstop rather than a per-order gate (the initial 10.0 default
silently gated accept-ready setups on the regression). MAX_WAIT
_BARS = 30 and all strategy thresholds are unchanged.

Paper / Live modes are unchanged in spirit: they fill on signal
with real-time semantics (no historical replay, hence no
eligibility delay) through the SAME registry.mark_filled path.

New test surface: tests/test_execution_lifecycle.py +14 tests
(test_new_order_cannot_expire_same_bar, test_order_becomes_
eligible_next_bar, test_order_waits_until_entry_is_touched,
test_order_fills_when_entry_is_inside_candle_range, test_order_
does_not_fill_when_entry_not_reached, test_order_expires_exactly_
at_expiry_bar, test_fill_prevents_later_expiration, test_terminal_
order_cannot_fill_after_expiry (bar-based), test_order_invalidates_
before_expiration, test_invalidation_precedes_fill_on_same_candle,
test_multiple_pending_orders_respect_limit, test_multiple_pending_
orders_can_both_sit_pending, test_created_order_bar_metadata_is_
correct, test_order_created_to_expired_log_chain). The pre-existing
entry-boundaries / expiry tests were updated to the new bar-anchored
semantics. Full suite after Phase 4D: 384 tests.

5000-bar regression (tests/test_backtester.py, live BTCUSDT 1m):
5000 bars processed; 127 orders created (80 accepted-setup
invalidations of 6; exposure gate 0 skips at the 25.0 backstop);
121 EXPIRED -- EVERY one a clean no-touch (the pending order's
excursion range never reached entry within the 30-bar window,
verified field by field on the Phase 4D min/max_price_since_creation
fields, superseded in Phase 4E by the lifetime min_low_since_creation /
max_high_since_creation) -- 6 INVALIDATED, 0 FILLED, 0 trades. The
0-fill outcome is
the HONEST result of applying the Phase 4C bar metadata retro-fit
to this window: Phase 4C's 8 fills were same-candle fills (the
signal's own candle traded through the entry); Phase 4D bans that
look-ahead, and on this falling window no entry was ever re-touched
inside a free-slot 30-bar window. The fill mechanism itself is
proven by the TestPendingOrderIntegrity suite (fills on synthetic
touch candles, exact bar metadata).

===========================================================
ECONOMIC SETUP DEDUPLICATION  (STATUS 101)  -- Phase 4E
===========================================================

Two defects surfaced in the STATUS 100 ledger:

  1. FROZEN EXCURSIONS: while a trade was OPEN the backtester's
     pending-order pass was skipped entirely (_execute_signal
     early-returned the moment current_trade was not None), so a
     working order's min/max_price_since_creation froze at its
     first-bar values and ORDER_EXPIRED could misreport the true
     window.
  2. DUPLICATE ECONOMICS: the live 6000-bar run minted SEPARATE
     pending orders for structurally-distinct order blocks with
     IDENTICAL trade economics (the OB-954/OB-956 pair and the
     OB-928..956 family -- entry 77616.00 / stop 77631.50 /
     target 77415.80 variants) -- MAX_PENDING_ORDERS slots spent
     on ONE market idea.

Fix 1 -- Phase 4E lifetime excursion (core/risk/order_intent.py;
min_price_since_creation / max_price_since_creation REMOVED):

    min_low_since_creation / max_high_since_creation -- lifetime
        low/high over ELIGIBLE bars only (the creation candle
        contributes NOTHING)
    bars_pending -- eligible bars spent, INCLUDING the expiry bar
        (the fill's last chance: MAX_WAIT_BARS=30 ->
        bars_pending=31)
    entry_distance_from_nearest_price -- 0.0 when min_low <= entry
        <= max_high, else min(|entry-min_low|, |entry-max_high|)

backtesting/backtester.py per-candle order (Phase 4E STEP 4):
  1. skip ineligible
  2. eligible-only excursion roll (bars_pending += 1; init then
     roll min_low/max_high on eligible candles)
  3. invalidation (a structural stop breach wins over an entry
     touch -- conservative)
  4. entry reached (low <= entry <= high, inclusive)
  5. fill -- exactly once via mark_filled, gated ONLY on the
     single-position model (at most one fill per candle). The
     pending pass itself runs EVERY candle, open position or not,
     and after a fill the loop CONTINUES so the remaining pending
     orders still roll excursions/invalidate on that candle. This
     is the anti-freeze regression fix.
  ORDER_EXPIRED now reports the full excursion window: setup_id /
  order_id / created_bar / eligible_from_bar / expired_bar /
  waited_bars / max_wait_bars / entry / min_low_since_creation /
  max_high_since_creation / bars_pending /
  entry_distance_from_nearest_price (also stamped on the order
  object). New ledger metrics on the backtester:
  pending_orders_average / pending_orders_max.

Fix 2 -- economic identity + dedup
(core/setup/economic_setup_registry.py, NEW):

core/setup/trade_setup_builder.py stamps structural_id (= setup_id)
and economic_fingerprint on every SetupCandidate
(core/setup/setup_candidate.py carries structural_id /
economic_fingerprint / is_economic_duplicate /
economic_canonical_id / observed_bar).

fingerprint_of() builds
[symbol]-[timeframe]-[direction]-E-[entry]-S-[stop]-T-[target],
every price snapped to the ECONOMIC_TICK_SIZE=0.5 grid, and is
idempotent on objects that already carry an economic_fingerprint.
SetupCandidate has no symbol/timeframe fields, so the builder
passes them explicitly; OrderIntent carries both, so runtime
derivation works.

EconomicSetupRegistry.observe(setups, order_registry, bar) runs on
EVERY candle as the ExecutionEngine chokepoint BEFORE the
pending-slot cap:
  1. drop structural setups already ordered (via order_registry)
  2. suppress any candidate whose economic fingerprint is already
     live as a PENDING order (active-idea dedup)
  3. collapse identical-fingerprint candidates within the candle to
     the single highest-ranked canonical
  4. cluster NEAR-identical zones when entry AND stop AND target
     are each within tolerance:
     tolerance = max(ECONOMIC_TICK_SIZE x ECONOMIC_CLUSTER_TICKS
     [0.5 x 8 = 4.0 at ~110], price x ECONOMIC_CLUSTER_PCT [0.1%],
     ATR x ECONOMIC_CLUSTER_ATR_FRACTION [0.0 default -- off]);
     NO hard-coded BTC point distances (user example: entry 77616
     vs 77620 on the same stop/target -> within tolerance ->
     clustered, by design)
  5. rank canonicals deterministically: (-score, -confidence,
     -liquidity_alignment, -rr, -observed_bar, structural_id
     ascending)
Duplicates are flagged is_economic_duplicate=True with
economic_canonical_id set (never random; a near-identical variant
cannot out-rank the canonical it was merged under -- the cluster
contracts to the BEST setup, not the first structural discovery).

core/execution/execution_engine.py (Phase 4E STEP 8): calls
economic_registry.observe(setups, order_registry, bar=current_index)
immediately after reading the decision batch and BEFORE the pending
slot cap -> the cap is applied AFTER clustering, so duplicate
variants can never consume capacity that independent ideas need.

core/risk/risk_engine.py: stamps structural_id + economic_fingerprint
onto the OrderIntent at mint time (OrderIntent carries both).

core/pipeline/pipeline_context.py: owns the persistent
economic_registry (created in __post_init__, re-created on reset(),
NOT cleared by reset_cycle() -- same class of session state as
order_registry).

config/risk_settings.py additions: ECONOMIC_TICK_SIZE = 0.5,
ECONOMIC_CLUSTER_TICKS = 8, ECONOMIC_CLUSTER_PCT = 0.001,
ECONOMIC_CLUSTER_ATR_FRACTION = 0.0. Strategy thresholds,
MAX_PENDING_ORDERS and MAX_WAIT_BARS are UNCHANGED (no tuning --
the objective is independence of opportunities, not more trades).

AST import census (Phase 4E):
  core/setup/trade_setup_builder.py      : core.setup.economic_setup_registry (fingerprint_of)
  core/pipeline/pipeline_context.py      : core.setup.economic_setup_registry (lazy, _new_economic_registry)
  tests/test_economic_setup_dedup.py     : core.setup.economic_setup_registry (EconomicSetupRegistry, fingerprint_of)
  core/execution/execution_engine.py     : duck-typed via context.economic_registry (no import)
  core/risk/risk_engine.py               : duck-typed via signal fields (no import)

New test surface:
  tests/test_execution_lifecycle.py +5 -- TestOrderExcursionTracking
  (tracks-minimum-low / maximum-high across multiple bars, each
  pending order has INDEPENDENT excursion data, expiration log uses
  the lifetime excursion, entry-touch is detected before
  expiration). Two legacy multi-pending tests were moved to a
  distinct world: the old near-identical world (110/100/130 vs
  109/100.5/130) CLUSTERS into one canonical by design under Phase
  4E (the canonical wins on reward/risk 2.47 > 2.0), so it can no
  longer demonstrate independent slots.
  tests/test_economic_setup_dedup.py 6 -- same-trade-economics-
  different-ob-ids -> one setup; same entry/stop/target -> ONE
  pending order end-to-end; nearby-entries cluster when the
  threshold allows; independent setups NEVER cluster; a cluster
  selects the HIGHEST-priority setup (score, not first discovery);
  the pending-order limit applies AFTER clustering.
  Full suite after Phase 4E: 395 tests (384 + 11 new).

5000-bar regression (tests/test_backtester.py, live BTCUSDT 1m):
5000 bars processed; 423 structural setups discovered collapsed to
73 distinct economic ideas (397 duplicates suppressed -- the
OB-968/OB-970 identical-economics pair now mints exactly ONE order,
closing the STATUS 100 OB-954/OB-956 repeat-ordering defect); 2
clusters formed; 83 orders created (vs 127 without dedup at
identical capacity) -- 0 FILLED / 78 EXPIRED (every one a clean
no-touch per the new lifetime excursion fields) / 5 INVALIDATED;
avg pending 0.5, max pending 7; 0 trades -- the same honest
no-look-ahead result as STATUS 100, now at full execution capacity
with per-independent-idea ordering. Note: ECONOMIC_CLUSTER_PCT is
the dominant tolerance term at BTC-scale prices (~0.1% of price at
77000 > 8 x 0.5 ticks); per spec, configurable, no hard-coded
points.

===========================================================
ENTRY FEASIBILITY / RETRACEMENT / MULTI-MODE ENTRY
(STATUS 102)  -- Phase 4F
===========================================================

Phase 4F layers a purely DIAGNOSTIC measurement + the multi-mode
entry architecture on the Phase 4E economic funnel. NO strategy
threshold changed, NO order expiration increased, NO market entry
mode enabled. New modules (all on the live import surface):

  core/setup/entry_feasibility.py     -- one quantity
      (|entry - creation price|) on four axes: absolute / percent
      of price / ATR_14 multiples / ticks; classify_entry_feasibility
      against configurable ATR-normalized thresholds; EntryFeasibility
      snapshot; create_entry_feasibility fallback (tick ->
      ECONOMIC_TICK_SIZE; atr 0 -> ATR axis 0 and classification
      degrades toward IMMEDIATE, matching no-indicator harnesses).
  core/setup/entry_tracker.py         -- EntryTrackingState +
      EntryTracker (track / advance / report) measuring what price
      ACTUALLY does AFTER the creating candle: retracement toward
      entry, touch (low <= entry <= high), bars until nearest
      approach / touch, target-direction continuation,
      distance_remaining_at_terminal, MISSED_CONTINUATION;
      FILLED / INVALIDATED freeze, EXPIRED snapshots then keeps
      rolling the full ENTRY_TRACKING_WINDOW_BARS window; report() at
      ALL / BULLISH / BEARISH. Keyed on structural_id, one record per
      first canonical appearance. Purely diagnostic (self-gates on
      ENABLE_ENTRY_DIAGNOSTICS; the no-leak test proves live order
      outcomes are byte-identical with it off).
  core/execution/entry_mode.py        -- PHASE 5C Canonical Entry
      Model Router. Mode constants re-imported from
      core.setup.entry_feasibility (one-way dependency, no cycle).
      select_entry_mode honors an explicit carried entry_mode on the
      setup, else routes configured_entry_mode(); AUTO and undeclared
      modes RAISE EntryModeRouterError -- the router NEVER silently
      substitutes a mode (no research/production mismatch);
      active_entry_modes() defensively collapses only empty/invalid
      config to the LIMIT_RETEST baseline; the backtester fill gate is
      mode-aware (non-active mode -> order stays parked, fills
      refused, excursions + invalidation still roll) and a MODE-LESS
      legacy order is anchored to the LIMIT_RETEST channel, never
      re-routed to the configured ENTRY_MODE.
  core/execution/entry_model.py       -- canonical EntryModel
      vocabulary + implementations (LimitRetest, MarketConfirmation,
      BreakoutContinuation; execution_type_for; default_entry_model
      returns the configured mode's model). re-exported through
      core/setup/entry_feasibility (single vocabulary); imports only
      config.risk_settings.
  core/validation/execution_comparison.py -- PHASE 5D: per-mode
      ISOLATED execution comparison (ExecutionComparisonMode):
      same market data / risk / fees / slippage executed once per
      mode in its own pipeline + simulator + backtester; funnel +
      executed-trade-ledger + PerformanceAnalytics metrics + fees /
      slippage per independent run -- research shadows are NEVER
      blended into a live ledger.

New field flow (no behavior change): SetupCandidate gains
entry_mode / observed_price / atr / entry_feasibility and
reentry_cooldown_suppressed (slots=True dataclass); OrderIntent
carries entry_mode + the feasibility class label; Trade carries
entry_mode; TradeSimulator.open_trade passes it through. The
EconomicSetupRegistry adds lifecycle ACTIVE / COOLDOWN states,
mark_terminal / sync_lifecycles (every candle), _in_cooldown and the
reentry_cooldown_suppressed counter: FILLED clears the fingerprint,
EXPIRED / INVALIDATED set a REENTRY_COOLDOWN_BARS window during
which same-fingerprint re-discoveries are suppressed instead of
re-minted. ExecutionEngine gains the entry_tracker.track() chokepoint
(post-economic-funnel, pre-slot-cap) and the per-direction pending
budget (pending_total_capacity / pending_direction_capacity helpers);
RiskEngine enforces the same per-direction cap. Backtester runs
sync_lifecycles + entry_tracker.advance() every candle after the
expiry pass and records pending_orders_max_bar /
pending_orders_max_directions for the max-pending explanation.

AST import census (Phase 4F): the three new modules resolve; the
entry-mode constants are imported from setup -> execution one-way;
entry_tracker imports only order status constants from
core.execution.order_registry (no cycle). Full suite after Phase 4F:
412 tests (395 + 17 new).

===========================================================
STRUCTURAL ZONE FRESHNESS / ENTRY ELIGIBILITY / CLUSTERING
(STATUS 103)  -- Phase 4G
===========================================================

Phase 4G gives every structural zone a measurable age + a derived
freshness state and separates STRUCTURAL VALIDITY from TRADE
ELIGIBILITY: a stale / too-far / mitigated / invalidated / too-thin
zone cannot mint a pending order, with an explicit
entry_rejection_reason traveling to the reports. The baseline config
was user-confirmed and USER-ORDERED TO STAY UNTUNED this phase (only
the ENTRY ELIGIBILITY REPORT decides later whether any threshold
moves). New modules (all on the live import surface):

  core/order_blocks/zone_freshness.py -- PURE, at-creation helpers
      (no bar after the creating candle is ever read): freshness
      states + rank (NEW/FRESH/ACTIVE/TESTED/MITIGATED/STALE/
      INVALIDATED); the entry-rejection-reason taxonomy + labels +
      conservative _REJECTION_PRIORITY; timeframe-aware
      max_order_block_age_bars; compute_zone_age (direct
      current - origin measurement, never a resettable counter --
      the scanners re-derive blocks from the window every candle);
      age_bucket; classify_freshness; effective_zone_tolerance /
      zones_overlap (the SAME Phase 4E tolerance formula, so
      clustering means the same thing structurally as economically);
      cluster_structural_zones (greedy, order-stable, stamps
      cluster_id / is_canonical / canonical_zone_id, returns
      (clusters, non_canonical_count)); evaluate_entry_eligibility
      -> (structurally_valid, trade_eligible, primary_reason,
      diagnostics). Blocking reasons: INVALIDATED_STRUCTURE /
      ALREADY_MITIGATED / STALE_ZONE / TOO_FAR_FROM_MARKET /
      INSUFFICIENT_RISK_WIDTH (all-paths, binds when risk <= 0 too);
      STALE_LIQUIDITY_CONTEXT / STALE_TARGET reserved (nothing emits
      them yet -- no zone-age liquidity data). Baseline config makes
      WEAK_DISPLACEMENT / TOO_MANY_TOUCHES diagnostic-only.
  core/setup/zone_eligibility.py      -- Session-state eligibility
      ledger (on PipelineContext exactly like the EntryTracker).
      observe() uses the FIRST-appearance-per-structural_id rule
      (identical to the Phase 4F tracker, so the report population
      is comparable); records the candidate's at-creation snapshot
      (age, freshness, distance, eligibility, reason) for EVERY
      canonical zone -- eligible OR rejected; note_structurally_
      suppressed() counts STEP-9 non-canonical zones per candle.
      report() emits ENTRY ELIGIBILITY + ORDER BLOCK FRESHNESS
      aggregates (ALL / BULLISH / BEARISH) with by_reason /
      by_freshness / by_age_bucket (0-5/6-15/16-30/31-60/61-120/120+)
      and the structural_suppressed total. Diagnostic only:
      nothing it stores is read by any engine.

New field flow: OrderBlock gains the Phase 4G snapshot fields
(origin_bar / created_bar / age_bars / age_time_seconds / freshness /
distance_from_current_price(+_atr) / mitigation_status /
last_tested_bar(+_timestamp) / cluster_id / is_canonical /
canonical_zone_id; entry / stop / touch_count are @property). The
OrderBlockScanner stamps age + freshness + distance on every emitted
block as measured from the current window (origin candle found by
backing up to it -- inherent origin, no look-ahead); the lifecycle
sets last_tested on each touch. SetupCandidate gains
structurally_valid / trade_eligible / entry_rejection_reason /
zone_diagnostics / zone_age_bars / zone_freshness / zone_distance(+_atr)
/ zone_cluster_id / zone_canonical_zone_id / zone_is_canonical.
TradeSetupBuilder runs cluster_structural_zones BEFORE candidate
generation (ENABLE_STRUCTURAL_CLUSTERING, user baseline True), builds
candidates only from canonical zones, stamps the eligibility snapshot
and calls zone_eligibility.observe(). DecisionEngine rejects
trade_eligible=False candidates outright (SETUP_REJECTED
reason=<reason>, deduped per (reason, fingerprint) in _logged_reject).
RiskEngine adds the defense-in-depth MIN_RISK_WIDTH_ATR gate (binds
on every order-minting path, even signals that bypassed the builder;
OrderIntent signals carry no ATR axis and pass through). The
regression report prints ORDER BLOCK FRESHNESS REPORT + ENTRY
ELIGIBILITY REPORT blocks in ALL / BULLISH / BEARISH.

Config baseline (config/risk_settings.py, STATUS 103 block):
MAX_ORDER_BLOCK_AGE_BARS = 500 (global; BY_TIMEFRAME map override-able),
FRESH_ORDER_BLOCK_AGE_BARS = 5, MAX_LIMIT_ENTRY_DISTANCE_ATR = 30.0,
MIN_RISK_WIDTH_ATR = 0.10, ENABLE_STRUCTURAL_CLUSTERING = True,
MIN_ORDER_BLOCK_DISPLACEMENT = 50.0 and MAX_ORDER_BLOCK_TOUCHES = 3
(diagnostic thresholds -- computed + reported, never blocking).

AST import census (Phase 4G): zone_freshness imports config only
(pure); decision_engine / risk_engine import REASON_* + labels from
zone_freshness one-way; zone_eligibility imports zone_freshness only;
pipeline_context lazy-imports ZoneEligibilityLog exactly like the
other session states (no cycle). Full suite after Phase 4G: 431 tests
(412 + 19 new), compileall clean. Regression 5000 bars reflects the
new funnel (see STATUS 103 for the before/after table).

==========================================================
ENTRY MODEL REACHABILITY & SHADOW COMPARISON
(STATUS 104)  -- Phase 4G extension
==========================================================

The Phase 4G extension answers whether the structural analysis is bad or
whether
the engine is trading a RETEST strategy in a market that CONTINUES
without retests, by shadow-measuring three entry models on EVERY
trade-eligible canonical setup over the same post-creation window.
Diagnostic only -- no threshold moved, LIMIT_RETEST remains the sole
executable mode (the report must be reviewed before MARKET_CONFIRMATION
may be enabled). New module (on the live import surface):

  core/setup/entry_shadow.py -- PURE diagnostic shadow comparison
      (reads candle history already in the pipeline; feeds nothing
      back to any engine). ShadowFill + EntryShadowState dataclasses;
      EntryShadow.observe() adds a state per trade-eligible canonical
      candidate (first-appearance-per-structural_id dedup, identical
      to zone_eligibility, so the population == the trade_eligible
      count by construction); advance()/_roll()/_settle() resolve
      each model's shadow lifecycle over the 60-bar window vs the real
      30-bar expiry (order context attached once from the registry;
      default horizon creation+1+MAX_WAIT_BARS for unminted states).
      Report prints ENTRY MODEL COMPARISON REPORT blocks
      (ALL/BULLISH/BEARISH): fills / bars-to-entry / entry distance
      in ATR / MAE-MFE / W-L-U / missed continuations per model, plus
      ATR-distance-vs-30-bar-expiry buckets and the correlation.
      Defines ENABLE_ENTRY_SHADOW + SHADOW_ENTRY_MODES gating (LIMIT
      always measured).

Wiring: PipelineContext owns the EntryShadow session state
(_new_entry_shadow factory + reset, lazy like every other session
state); TradeSetupBuilder calls shadow.observe() beside
elig_log.observe(); backtesting/backtester.py calls
entry_shadow.advance(candle, bar, order_registry) every candle beside
entry_tracker.advance; tests/test_backtester.py prints the report
blocks. Config (config/risk_settings.py, Phase 4G extension block):
ENABLE_ENTRY_SHADOW = True, SHADOW_ENTRY_MODES = ("MARKET_CONFIRMATION",
"BREAKOUT_CONTINUATION").

AST import census (Phase 4G extension): entry_shadow imports
config.risk_settings
and the three ENTRY_MODE_* constants from core.setup.entry_feasibility
only (pure, one-way -- the same pattern as entry_tracker); no engine
imports entry_shadow (setup -> pipeline session state, mirrors the
EntryTracker/ZoneEligibility pattern). Full suite after the Phase 4G
extension: 451
tests (431 + 20 new), compileall clean. Regression 5000 bars + verdict
in STATUS 104.

==========================================================
CAUSAL BREAKOUT CONTINUATION VALIDATION
(STATUS 105)  -- Phase 4H
==========================================================

Phase 4H re-runs the STATUS 104 BREAKOUT_CONTINUATION hypothesis under
STRICT causal execution rules (before it may ever become executable):
a setup frozen at creation, a trigger decided only from the trigger
candle's own close information, an entry at the OPEN of the next bar, and
deterministic intrabar SL/TP resolution -- reporting the performance
metrics AND a MARKET_CONFIRMATION rejection-stage diagnosis. Diagnostic
only -- no threshold moved, LIMIT_RETEST remains the sole executable
mode; BREAKOUT_CONTINUATION stays a shadow until the user reviews the
report. New module (on the live import surface):

  core/setup/causal_validation.py -- PURE diagnostic causal re-walk
      (reads the same candle history + setups the shadow does; feeds
      nothing back to any engine, produces no order). CausalValidator +
      CausalValidationState + format_causal_report. RULE 1 freeze at
      observe() (setup/candles can be mutated freely afterwards);
      RULE 2 trigger at the trigger candle's close (bull high > E and
      close > E / bear low < E and close < E; stop breach checked
      BEFORE the trigger); RULE 3 entry at the OPEN of trigger + 1
      (trigger on the last in-window bar = trigger without an entry);
      RULE 4 deterministic intrabar policies CONSERVATIVE / OPTIMISTIC /
      EXCLUDE, with the CONSERVATIVE outcome always recorded so all
      three render from one walk. self-gates on ENABLE_CAUSAL_VALIDATION.
      Reports (ALL/BULLISH/BEARISH): triggers, triggers without an
      executable next bar, fills, ambiguous trades, W/L/UNRESOLVED/
      EXCLUDED, win rate, profit factor, gross P/L, expectancy / average
      R, max drawdown (R and %), avg bars to entry, MAE/MFE in ATR, plus
      the MARKET_CONFIRMATION candidates / rejected_structure /
      rejected_trend / rejected_distance / rejected_volume /
      rejected_orderflow / triggered counters.

Wiring: PipelineContext owns the CausalValidator session state
(_new_causal_validator factory + field + reset, lazy like every other
session state); TradeSetupBuilder calls validation.observe() beside
shadow.observe(); backtesting/backtester.py calls
causal_validation.advance(candle, bar, order_registry) every candle beside
entry_shadow.advance; tests/test_backtester.py prints the PHASE 4H
CAUSAL BREAKOUT VALIDATION blocks. Config (config/risk_settings.py,
Phase 4H block): ENABLE_CAUSAL_VALIDATION = True, INTRABAR_POLICY =
"CONSERVATIVE", reusing ENTRY_TRACKING_WINDOW_BARS = 60.

AST import census (Phase 4H): causal_validation imports
config.risk_settings only (pure, one-way -- same pattern as
entry_shadow/entry_tracker); no engine imports causal_validation (setup ->
pipeline session state). Full suite after Phase 4H: 483 tests (451 + 32
new), compileall clean. Regression 5000 bars + verdict in STATUS 105.

==========================================================
INSTRUMENT DISCOVERY / REGISTRY  (STATUS 109)  -- Phase 6A
==========================================================

Phase 6A implements DYNAMIC PRODUCT DISCOVERY: the engine
catalogs EVERY Delta product (spot / perpetual / future /
options / unknown types) from /v2/products through an
injectable transport, normalizes it to a canonical
exchange-agnostic Instrument, and tracks lifecycle state in
a persistent registry -- a newly listed product is detected
by comparing the next discovery pass against what we ALREADY
know, never against a hardcoded symbol list. Eligibility
never trades a discovered product without passing its gates
(Phase 6B completes the liquidity/history layers).

  data/delta/product_client.py             -- ProductClient:
      fetch() (raw /v2/products "result"), fetch_cached() (TTL),
      clear_cache(). Transport is INJECTABLE (default DeltaREST);
      tests swap a FakeTransport, zero network.
  data/delta/product_normalizer.py         -- DeltaProductNormalizer:
      raw Delta product JSON -> canonical Instrument. Real-payload
      defenses: contract_type/product_type lowercase via
      product_type_from_delta() (SPOT / PERPETUAL / FUTURE /
      CALL_OPTION / PUT_OPTION / UNKNOWN); underlying_asset /
      quoting_asset are asset OBJECTS (symbol extracted);
      numeric fields coerced safely; is_delisted / is_disabled /
      is_unlisted / state -> trading_enabled (NOT a free-form
      string); options derive option_type from product_type;
      raw JSON preserved in metadata.
  data/delta/product_discovery.py          -- discover_products()
      (fetch + normalize) and refresh_instrument_registry()
      (discover -> registry.upsert -> mark_present -> save),
      returning {discovered, newly_listed, delisted,
      total_catalog}. DISCOVER EVERYTHING, no hardcoded universe.
  core/registry/product_types.py           -- canonical product type
      + lifecycle state vocabulary (NEWLY_LISTED / ACTIVE /
      ELIGIBLE / INELIGIBLE / DELISTED); only EXECUTABLE_STATES
      reach execution; product_type_from_delta map.
  core/registry/instrument.py              -- canonical Instrument
      dataclass (slots): instrument_id / symbol / exchange /
      product_type / underlying_asset / quote_asset / expiry_time /
      strike_price / option_type / tick_size / quantity_step /
      minimum_quantity / trading_enabled / state / metadata;
      round_price / round_quantity / valid / valid_precision /
      to_dict / from_dict.
  core/registry/instrument_registry.py     -- InstrumentRegistry
      (persistent JSON): FIRST sighting -> NEWLY_LISTED candidate;
      a repeat sighting with changed economics re-validates (back
      to NEWLY_LISTED); a DELISTED instrument that reappears is
      re-listed candidate; unchanged NEWLY_LISTED -> ACTIVE once
      sighted again; mark_present() confirms prior-pass sightings
      and DELISTs what vanished (graceful, never deleted);
      mark_eligible / mark_ineligible / by_state / executable() /
      newly_listed() / delisted() / discoverable() / to_dict /
      save / load. Repeat upserts PRESERVE the stored lifecycle
      state (an ELIGIBLE instrument is never silently wiped).
  core/registry/eligibility.py             -- InstrumentEligibility:
      GATE 1 identity, GATE 2 trading_enabled, GATE 3 canonical
      strategy product type, GATE 4 precision; liquidity gate is
      DENY-by-default when quote_volume_24h is None (never trade
      what we cannot measure); run_basic_gates() = gates 1-4 only.
      Optional/derivative types are DISCOVERED but never eligible
      until a supporting layer exists.

Imports

core.registry.instrument  : dataclasses, typing, core.registry.product_types

core.registry.product_types : (stdlib only)

core.registry.instrument_registry : pathlib, typing, core.registry.instrument,
                                    core.registry.product_types

core.registry.eligibility : core.registry.instrument,
                            core.registry.product_types

data.delta.product_client : time, core.exchanges.delta.delta_rest

data.delta.product_normalizer : core.registry.instrument,
                                core.registry.product_types

data.delta.product_discovery : data.delta.product_client,
                               data.delta.product_normalizer

==========================================================
MARKET UNIVERSE  (STATUS 110)  -- Phase 6B
==========================================================

Phase 6B builds the ELIGIBLE trading universe on the Phase 6A
registry. Discovery catalogs EVERYTHING; the universe is the
ELIGIBLE cut -- an instrument must pass the full gate cascade
(identity, trading_enabled, canonical strategy product type,
precision, measured liquidity, optional history/window gate)
and be CONFIRMED (never a first-sighting candidate). The
verdicts are written back to the persistent registry, so the
catalog always reflects the last eligibility decision.

  core/universe/universe_policy.py     -- UniversePolicy:
      min_quote_volume_24h (None removes the bound, never the
      data requirement) + min_history_bars (None = gate off;
      set e.g. 300 for the 1m lookback window). Frozen.
  core/universe/universe_manager.py    -- UniverseManager:
      cascade over registry.discoverable(); NEWLY_LISTED ->
      NOT_CONFIRMED (never eligible same pass); DELISTED can
      never re-enter; liquidity/history PROVIDERS INJECTABLE
      and duck-typed (quote_volume_24h(symbol) /
      history_bars(symbol, timeframe)); no data -> EMPTY
      universe, never an everything-goes catalog; mark_eligible /
      mark_ineligible + reason written back; executable_symbols()
      feeds Phase 6C scanning; refresh() = discovery +
      eligibility. NOTE: `registry if registry is not None`
      (an empty InstrumentRegistry is FALSY via __len__).
  core/universe/market_universe.py     -- MarketUniverse
      frozen snapshot: policy / instruments / timeframe /
      captured_at / reasons; symbols / get_by_symbol / contains /
      count / symbols_text. The object scanning executes over.
  core/universe/refresh_scheduler.py   -- RefreshScheduler:
      run_if_due() / force_refresh() on an interval with an
      injectable clock; interval <= 0 always due; a failed
      discovery pass is recorded and the loop continues
      (last_universe / last_summary / errors). Scheduler's
      refresh passes an injected client through to discovery.
  core/registry/eligibility.py         -- (extended) history
      gate: NO_HISTORY_DATA / INSUFFICIENT_HISTORY beside
      NO_LIQUIDITY_DATA / LOW_LIQUIDITY; NOT_CONFIRMED;
      evaluate envelope upgraded to instrument.valid.

Imports

core.registry.eligibility     : core.registry.instrument,
                                core.registry.product_types

core.universe.universe_policy : (stdlib only)

core.universe.market_universe : dataclasses, typing,
                                core.registry.instrument,
                                core.universe.universe_policy

core.universe.universe_manager: time, core.registry.eligibility,
                                core.registry.instrument_registry,
                                core.registry.product_types,
                                core.universe.market_universe,
                                core.universe.universe_policy,
                                data.delta.product_discovery (lazy)

core.universe.refresh_scheduler: time

============================================================
CANONICAL IDENTITY + MULTI-SYMBOL SCANNING (STATUS 111) -- Phase 6C
============================================================

Phase 6C turns the Phase 6B eligible universe into a scanning
surface: ONE isolated pipeline per instrument, a canonical setup
identity built ONCE at setup creation and carried verbatim through
the whole execution chain, and a deterministic aggregated result.
Per-symbol state can never leak: each scan builds a FRESH context /
world / EventBus / TradeSimulator / Backtester. Symbols come ONLY
from the eligible cut -- never a hardcoded list.

  core/identity/instrument_identity.py -- canonical setup identity
      {exchange}:{instrument_id}:{timeframe}:{direction}:{strategy}:
      {setup_id}. build_setup_identity() (validates non-empty
      segments + BULLISH/BEARISH, raises IdentityError) +
      split_setup_identity() (round trip, suffix VERBATIM).
      Built ONCE by TradeSetupBuilder, copied by RiskEngine onto
      OrderIntent and by TradeSimulator onto Trade -- never
      reconstructed downstream (legacy single-symbol paths keep
      canonical_id == "").
  core/scanning/symbol_pipeline.py   -- SymbolPipeline: one
      instrument, one isolated pipeline (fresh PipelineContext with
      MarketState.exchange + instrument_id, world via INJECTABLE
      factory defaulting to InstitutionalPipeline, EventBus,
      TradeSimulator, Backtester). data_source contract
      get_candles(symbol, timeframe, limit). Accumulates every
      candle's setups + the cumulative decision/order/trade
      registries into the per-symbol result. NO_DATA_SOURCE /
      NO_DATA -> SKIPPED.
  core/scanning/multi_symbol_scanner.py -- MultiSymbolScanner:
      consumes MarketUniverse.eligible_instruments() / registry
      executable() / any iterable; deterministic (exchange,
      instrument_id, symbol) ordering independent of insertion
      order; per-symbol failure isolation caught -> FAILED + error,
      neighbours continue; empty universe -> clean empty result.
  core/scanning/scan_result.py     -- ScanStatus (SUCCESS / SKIPPED /
      FAILED), SymbolScanResult (setups / decisions / orders /
      trades / pipeline) and MultiSymbolScanResult (counts, symbols,
      flat slices, for_symbol(), summary()).

Imports

core.scanning.scan_result    : dataclasses, enum, typing

core.scanning.symbol_pipeline: core.backtesting.trade_simulator,
                               backtesting.backtester,
                               core.events.event_bus,
                               core.events.event_types,
                               core.market_state,
                               core.pipeline.pipeline_context,
                               core.scanning.scan_result,
                               core.pipeline.institutional_pipeline (lazy)

core.scanning.multi_symbol_scanner: time, core.scanning.scan_result,
                                   core.scanning.symbol_pipeline

core.identity.instrument_identity : (stdlib only)

core.market_state            : (extended) exchange / instrument_id
                               fields (defaults "")

core.setup.trade_setup_builder: (extended) stamps candidate.canonical_id
                               via core.identity.instrument_identity

core.risk.order_intent       : (extended) canonical_id field (default "")

core.backtesting.trade       : (extended) canonical_id field (default "")

============================================================
PHASE 6D -- REAL-TIME MULTI-SYMBOL SUBSCRIPTIONS (STATUS 112)
============================================================

Live market data orchestration. One SubscriptionWorker per
eligible instrument over a SHARED multiplexed transport (Delta
subscribes many symbols on ONE websocket connection). Explicit
lifecycle states, per-symbol failure isolation, exponential
reconnect, and a closed-candle integrity gate. No strategy /
execution / portfolio allocation logic lives here.

  data/realtime/subscription_state.py -- SubscriptionStatus
      (STOPPED / CONNECTING / LIVE / RECONNECTING / STALE /
      FAILED -- no implicit booleans) + per-subscription
      SubscriptionState counters (received / delivered /
      duplicates / out_of_order / forming_skipped /
      reconnect_attempts) + assert_valid_transition.
  data/realtime/reconnect_policy.py -- ReconnectPolicy
      exponential backoff (base_delay * factor ** (attempt-1),
      capped at max_delay; deterministic, jitter opt-in) with
      optional max_attempts budget -> ReconnectExhausted.
  data/realtime/candle_router.py -- CandleRouter integrity
      gate per symbol: closed candles delivered at most once, in
      chronological order; FORMING candles (closed=False) never
      forwarded; bounded seen-timestamp memory survives a
      reconnect (replayed candle -> duplicate, older candle ->
      out-of-order). Counters remain observable.
  data/realtime/stream_health.py -- StreamHealth staleness
      detection (max_stale_seconds, injectable clock).
  data/realtime/stream_worker.py -- SubscriptionWorker: one
      logical subscription; event-driven, non-blocking state
      machine (STOPPED -> CONNECTING -> LIVE; LIVE -> RECONNECTING
      on stream down; RECONNECTING retried on clock-deadline via
      poll(); LIVE -> STALE by health; budget exhausted -> FAILED).
      Reconnect is per-route: a failing stream can never stall the
      others.
  data/realtime/subscription_manager.py -- MultiSymbolSubscriptionManager:
      consumes MarketUniverse.eligible_instruments() / iterable;
      sync() diff = future subscriptions - current -> ADD / REMOVE /
      KEEP (in place, no restart; FAILED workers re-added on the
      next pass); one shared transport per lifecycle; poll()
      isolates per-worker failures; stop_all() closes the connection.
  data/delta/delta_subscription_stream.py -- DeltaSubscriptionStream:
      production multiplexed transport; one websocket, one channels
      payload listing every desired symbol; per-symbol CandleBuilder
      rolls closed candles on bucket boundaries and emits throttled
      forming heartbeats; on_down() fanned to every route; websockets
      sync client imported lazily (offline tests use a fake).
  core/history/candle.py : (extended) closed: bool = True (FORMING
      vs CLOSED provenance) and symbol: str = "" (delivery scoping);
      both defaulted so the backtest candle shape is unchanged.

Imports

data.realtime.subscription_state : (stdlib only)

data.realtime.reconnect_policy : (stdlib only)

data.realtime.candle_router : collections, (canonical Candle duck)

data.realtime.stream_health : time

data.realtime.stream_worker : time, data.realtime.reconnect_policy,
                              data.realtime.candle_router,
                              data.realtime.stream_health,
                              data.realtime.subscription_state

data.realtime.subscription_manager : time, data.realtime.reconnect_policy,
                                     data.realtime.stream_worker,
                                     data.realtime.subscription_state,
                                     data.delta.delta_subscription_stream (lazy)

data.delta.delta_subscription_stream : json, threading,
                                       data.candle_builder (lazy),
                                       data.websocket_client.WS_URL shape,
                                       core.history.candle.Candle,
                                       websockets.sync.client (lazy)

core.history.candle : (extended) closed / symbol fields (defaults)

============================================================
OPTIMIZATION / AI / LIVE (QUARANTINED -- STATUS 84)
============================================================

The OptimizationEngine, AIEngine and the legacy BROKER engine
referenced by the legacy OPTIMIZATION / AI / LIVE sections
were part of the legacy tree moved to _archive/ (see _ARCHIVE
section below). They are NOT importable live. The canonical
replay path is Backtester / PortfolioBacktester, and the
canonical live path is core/live/BrokerEngine -- a DIFFERENT,
new engine (STATUS 93) with no relation to the archived legacy
broker stage.

============================================================
PHASE 6E -- REAL-TIME CLOSED-CANDLE INTEGRATION, PAPER MODE
(STATUS 113)
============================================================

NEW package: core/runtime/ -- the orchestration layer that
wires the 6B universe refresh and the 6D real-time closed-
candle delivery into the frozen 6C SymbolPipeline, running
continuously in PAPER mode. Combines existing blocks; adds
NO strategy, execution, or portfolio logic:

    execution_port.py    -- the ONE paper/live execution
       seam. ExecutionPort protocol (execute/fetch/cancel/
       balance/positions) + PaperExecutionAdapter (audits the
       would-be intent, reports the paper envelope, and raises
       PaperOnlyError on every live-only op so a mis-wired
       paper port can never place real orders). The future
       LiveDeltaExecutionAdapter will be the ONLY other
       implementation. canonical-isolating, not implemented
       here.
    pipeline_registry.py -- stable per-instrument pipeline
       ownership keyed by (exchange, instrument_id)
       (instrument_identity_key). reconcile() diffs the
       eligible cut -> ADD / RETAIN / RETIRE; RETIRED pipelines
       move to a readable snapshot. Pipelines are built via
       the injectable world_factory (production default =
       InstitutionalPipeline) and reset exactly once at ADD --
       a retained instrument NEVER rebuilds across refreshes.
    paper_runtime.py     -- PaperRuntime: the per-instrument
       continuous paper unit. Owns ONE frozen SymbolPipeline
       and drives it through the canonical core/live/
       BrokerEngine with dry_run=True (the SAME explicit
       per-candle flow the Backtester and BrokerEngine use:
       world on_candle -> RiskEngine OrderIntent -> paper fill
       via TradeSimulator -> SL/TP exits -> TradeRegistry =
       the PAPER_TRADE_REGISTRY ledger). The injected
       execution boundary is the PaperExecutionAdapter --
       the ONLY difference from a future live run. canonical_id
       (Phase 6C) flows setup -> order -> trade verbatim.
     realtime_engine.py   -- RealTimeEngine: the orchestrator.
        RefreshScheduler (6B) -> registry.reconcile + manager
        sync (6D) on every pulse; manager.poll() drains closed
        candles; delivery resolves symbol -> eligible instrument
        -> (exchange, instrument_id) identity key -> that
        runtime's process_closed_candle. Identity-key routing
        (never position/subscription order) keeps a BTC candle
        from ever mutating the ETH pipeline. start()/poll()/
        stop(); statuses() merges runtime + 6D subscription
        state; ledger()/all_trades() expose the paper trades.
     paper_main.py        -- PaperMainBridge (Phase 9P-a): the
        canonical PAPER-mode startup bridge for the CLI entry
        point (main.py). build_paper_engine() assembles the same
        RealTimeEngine -> PipelineRegistry -> PaperRuntime ->
        BrokerEngine (dry_run) stack, every collaborator
        injectable; ExplicitSymbolUniverseManager supplies the
        eligible cut from settings.SYMBOLS (UNIVERSE="explicit",
        the documented fallback until live liquidity/history
        providers exist) and exposes refresh_discovery (no-op) +
        build_universe (MarketUniverse snapshot) for the
        RefreshScheduler. tick() = one non-blocking poll step;
        run_paper_forever() = the blocking main.py loop. main.py
        PAPER path now drives this runtime instead of the legacy
        single-symbol PaperTradingEngine / websocket_client path.

core/runtime/ imports structural parts of the existing tree
(core.scanning.symbol_pipeline, core.live.broker_engine,
core.universe.refresh_scheduler, data.realtime.
subscription_manager, core.backtesting.trade_registry,
core.risk.account, config.risk_settings) plus its own five
modules -- all offline-testable with a scripted world +
FakeTransport + FakeClock. paper_main.py additionally imports
config.settings, core.registry.instrument/ product_types,
core.universe.market_universe/ universe_policy, config.
risk_settings and core.runtime.realtime_engine. No new external
deps (websockets still lazy in the 6D production stream only).

============================================================
PHASE 9P-b -- ACCOUNT PROFIT FACTOR / EXPECTANCY REPORTING
(STATUS 134)
============================================================

REPORTING / ANALYTICS layer, NOT a new accounting source and NOT a
second metric implementation. The canonical profit-factor / expectancy
calculation was already the analytics layer's performance.py
(PerformanceAnalytics / PerformanceReport -- the same report surface
the dashboard consumes). Phase 9P-b closed the actual gap: (1) made
the breakeven classification correct (pnl == 0 is NEITHER a win NOR a
loss; pre-9P-b it was misclassified as a win), and (2) removed the
dead account-level duplicates.

    core/analytics/performance.py   -- PerformanceReport gained a
       `breakeven` field (wins + losses + breakeven == total_trades).
       Winning trade = net P&L > 0; losing trade = net P&L < 0;
       breakeven = net P&L == 0. Breakevens are counted in `total`
       (so expectancy divides by ALL completed trades incl. breakeven)
       but excluded from win/loss counts, gross profit / gross loss,
       win/loss streaks and per-direction win rates. profit_factor =
       gross_profit / gross_loss (inf when gross profit > 0 and no
       gross loss; 0.0 when no gross profit, incl. all-breakeven;
       0.0 for the empty case per the project missing-value
       convention). expectancy = net_profit / total (mean completed-
       trade net P&L). Costs are honored implicitly: Trade.pnl is the
       net per-trade result (gross minus commission minus slippage, per
       trade_simulator). metrics() dict and summary() console block
       updated to surface breakeven.
    core/risk/account_state.py     -- removed the DEAD
       AccountState.profit_factor and AccountState.expectancy fields
       (never computed by Account.update_statistics(), never read
       anywhere). The account is a counter-only accumulation with no
       per-trade outcomes, so it cannot derive these metrics; the
       single canonical calculation lives in performance.py, and
       declaring duplicates here created a misleading second surface.

Canonical source of completed-trade outcomes: core.backtesting.
trade_registry (TradeRegistry.closed(), status == "CLOSED"); Trade.pnl
is the per-trade NET P&L. Open positions, rejected/expired/unfilled
orders and unrealized P&L are excluded by the status == "CLOSED"
filter. Research-layer expectancy/profit-factor references (Phase 9H/
9K/9L/9M researcher, Phase 9I readability, research_ml, phase7/S 7E
breakout asymmetry, Phase 9G research intelligence) are untouched:
those are RESEARCH-ONLY and are not account reporting.

Tests: tests/test_account_profit_factor_9pb.py (13 tests, stdlib-
only): task fixture [+100,+200,-50,-100,0] -> gross_profit 300,
gross_loss 150, profit_factor 2.0, total 5, wins 2, losses 2,
breakeven 1, net 150, expectancy 30; all-win -> inf; all-loss ->
0.0; breakeven-only -> 0.0 (neither win nor loss); empty -> 0.0;
negative expectancy preserved; breakeven-not-a-win regression; open
positions excluded; deterministic repeat; costs honored on net pnl;
reconcile with booked account; AccountState exposes NO duplicate
fields; metrics() dict includes breakeven. No new external deps.
Full canonical suite tests/ = 1383 passed (baseline 1370 + 13);
compileall clean.

============================================================
PHASE 9P-c -- CANONICAL RUNTIME ANALYTICS / ACCOUNT REPORTING
ATTACH-POINT (STATUS 135)
============================================================

RUNTIME / ANALYTICS layer, PURE delegation -- no second accounting
system, no second PF/expectancy implementation, and no restored
account-level duplicate surface. The canonical calculation remains
PerformanceAnalytics / PerformanceReport (the same object surface the
backtest / validation / dashboard consume). This milestone makes the
running PAPER runtime able to obtain its canonical performance report
deterministically.

    core/runtime/paper_runtime.py  -- added PaperRuntime.report()
       -> PerformanceAnalytics.analyze(runtime.account,
                                        runtime.ledger). The runtime
       already owned both canonical inputs (its Account + its
       TradeRegistry ledger), so this is the smallest architecture-
       compatible change. On-demand only (never in the candle path ->
       never blocks the event loop); deterministic for the same
       completed-trade state.
    core/runtime/realtime_engine.py-- added
       RealTimeEngine.performance(symbol=None): symbol given -> that
       active runtime's report (None for an unknown symbol, matching
       universe-routing semantics); symbol None -> aggregate
       PerformanceReport over ALL active runtimes' completed trades,
       with a shared starting balance (sum of per-runtime starting
       balances) so final equity reconciles across the whole PAPER
       book. Uses core.analytics.performance + core.backtesting.
       trade_registry + core.risk.account behind a lazy import.

Canonical data source (unchanged): core.backtesting.trade_registry
(TradeRegistry CLOSED trades, status == "CLOSED"); Trade.pnl = net
per-trade P&L. Data-source integrity: open positions, unrealized
P&L, and rejected / expired / unfilled / cancelled orders never reach
the ledger -- the BrokerEngine drops a failed route before booking,
and the analytics closed-only filter excludes everything open.
Breakeven trades remain NEITHER win NOR loss (9P-b classifiers).
Account / AccountState stay counter-only: profit_factor / expectancy
are NOT restored; they live solely on the PerformanceReport.

Tests: tests/test_runtime_report_9pc.py (12 tests, stdlib-only,
offline multi-symbol engine + direct PaperRuntime): runtime canonical
report identity; completed-trade-only; open excluded; rejected/
expired/unfilled never in ledger; breakeven neutral; PF + expectancy
identity with canonical analytics; report updates after close;
deterministic repeat; account state stays counter-only; per-symbol
isolation on BTC+ETH; aggregate over all symbols (shared starting
balance reconciles final equity); empty aggregate; deterministic
aggregate. No new external deps. Full canonical suite tests/ = 1395
passed (baseline 1383 + 12); compileall clean.

============================================================
PHASE 9P-d -- LIVE LIQUIDITY / HISTORY PROVIDER PLUMBING
(STATUS 136)
============================================================

Fills the ONE genuinely missing gap in the Phase 6B universe
architecture: real provider-backed eligibility data for the canonical
UniverseManager. UniverseManager already accepted injectable
`liquidity_provider` / `history_provider` (duck-typed:
quote_volume_24h(symbol)->float|None, history_bars(symbol,timeframe)
->int|None) but NO real provider existed -- the PAPER runtime fell
back to UNIVERSE="explicit" (settings.SYMBOLS). This phase adds ONLY
the actually-missing plumbing (no new universe architecture, no
second manager, no re-rewrite of MarketUniverse / UniverseManager /
SymbolPipeline / subscriptions): the providers FEED the existing
eligibility cascade.

    core/universe/liquidity_provider.py
        DeltaLiquidityProvider -- fetches the REAL Delta /v2/tickers
        payload once per refresh (one REST call, not per-symbol) and
        maps each symbol's `turnover_usd` (24h USD turnover) to the
        canonical quote_volume_24h input. Missing / empty /
        unparseable / zero turnover -> None -> the cascade DENIES
        (NO_LIQUIDITY_DATA); missing data is NEVER assumed liquid.
        Transport / fetch injectable for offline tests.

    core/universe/history_provider.py
        DeltaHistoryProvider -- reports the COUNT of bars available
        via the existing real DeltaHistory.candles() over a bounded
        lookback window (PROVIDER_HISTORY_LOOKBACK_DAYS, default 7).
        Returns None on failure so missing history DENIES
        (NO_HISTORY_DATA) -- never "assume sufficient history".
        History client injectable.

    config/settings.py
        MIN_QUOTE_VOLUME_24H / MIN_HISTORY_BARS (operator thresholds;
        an unconfigured liquidity threshold still REQUIRES a measured
        figure; invalid values fail fast), PROVIDER_HISTORY_LOOKBACK_
        DAYS, and the UNIVERSE="provider" selector.

    core/runtime/paper_main.py
        build_provider_universe_manager() assembles the CANONICAL
        UniverseManager + InstrumentRegistry + real providers;
        build_paper_engine(universe_mode=...) selects the provider
        path when UNIVERSE=="provider" while PRESERVING the explicit
        fallback (default). Providers run in the SAME synchronous
        cadence-based universe refresh path as the existing product
        discovery -- NOT in the real-time candle delivery path (no
        blocking HTTP added to the live event loop).

Tests: tests/test_provider_plumbing_9pd.py (28 tests, stdlib-only,
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
present for liquid symbols and empty for inactive; /v2/history/
candles returns 1440 1m bars for BTCUSDT over 1 day (2026-09-03). No
new external deps. Full canonical suite tests/ = 1423 passed (baseline
1395 + 28); compileall clean.

============================================================
PHASE 9P-e -- PROVIDER-UNIVERSE LIVE SMOKE / VERIFICATION HARNESS
(STATUS 137)
============================================================

Reproducible, read-only/PAPER-only live-exchange smoke harness for the
9P-d provider-universe path (real Delta data -> the CANONICAL 6B
eligible universe -> subscriptions -> PAPER runtime), with safe bounded
shutdown and a structured report. Reuses ONLY the canonical
UniverseManager / InstrumentRegistry / eligibility cascade /
SymbolPipeline / subscriptions / PaperRuntime / the single liquidity+
history provider architecture + build_paper_engine
(UNIVERSE="provider"); provider-selection is always `provider`, never
accidental `explicit`.

    core/runtime/provider_universe_smoke.py
        ProviderUniverseSmoke + ProviderUniverseSmokeReport + error
        category constants (NETWORK_UNAVAILABLE / API_ERROR /
        PARSE_ERROR / NO_INSTRUMENTS / NO_LIQUIDITY_DATA /
        NO_HISTORY_DATA / NO_ELIGIBLE_INSTRUMENTS /
        RUNTIME_INITIALIZATION_FAILURE) + classify_reason() + CLI:
        `python -m core.runtime.provider_universe_smoke [--timeframe X]
        [--polls N] [--interval S] [--passes N(default 2)]
        [--symbols A,B,...] [--min-volume F] [--min-bars I]`.
        Harness primes DeltaLiquidityProvider.refresh() before each
        build_universe() (quote_volume_24h reads the snapshot map),
        surfaces RefreshScheduler discovery errors into report.errors
        (NetworkUnavailable -> NETWORK, else API), distinguishes
        DATA_UNAVAILABLE from ELIGIBILITY_REJECTED, and defaults
        bounded/terminating (engine.stop() closes the transport + sets
        the stop event; the WS pump loop is daemon and breaks on stop
        -- no hanging WebSocket). Bounded discovery filters real
        /v2/products to --symbols in-memory (one REST call; history
        remains per-symbol). Fresh registry needs >= 2 passes to
        graduate NEWLY_LISTED -> ACTIVE via the Phase 6A confirmation
        state machine. Exits 0 success, 2 harness-error category, 3 on
        a genuinely empty eligible universe (NOT manufactured success).

Tests: tests/test_provider_universe_smoke_9pe.py (17 tests, stdlib-only,
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
paper_only=true, clean bounded exit; --min-volume 5000000 --min-bars
1000 -> 0 eligible, ALL LOW_LIQUIDITY from REAL turnover (thresholds
NOT weakened; DATA AVAILABLE distinct from ELIGIBILITY REJECTED);
--min-volume 100000 --min-bars 300 -> mixed cut BTCUSDT/ETHUSDT/SOLUSDT
ELIGIBLE vs DOGEUSDT LOW_LIQUIDITY. Runtime Safety: PAPER-only
(paper_only=true), LIVE_MODE-without-PAPER guard + bounded CLI; no
live orders; no weakening of eligibility. No new external deps
(post-run requires websockets + requests as already used). Full
canonical suite tests/ = 1440 passed (baseline 1423 + 17); compileall
clean; tracked .pyc restored.

============================================================
PHASE 9P-f -- PAPER CONTROL & MONITORING API
(STATUS 138)
============================================================

Read-only-first Control & Monitoring HTTP API + a safe PAPER-only
control seam over the canonical RealTimeEngine, enforcing
API -> Command/Query -> Existing Runtime (the engine stays the single
source of truth; the API adds no strategy/risk/order/live logic).
stdlib-only, no new dependency.

    core/runtime/lifecycle.py
        EngineLifecycle -- thin control manager owning a daemon
        control poll thread + RLock-serialized state model
        (STOPPED/STARTING/RUNNING/STOPPING/FAILED) + commands
        allowlist {start, stop, restart, emergency_stop}.
        emergency_stop is a highest-priority local PAPER shutdown,
        strictly idempotent (2nd call = zero duplicate shutdown work,
        no error, stays STOPPED); start failure -> FAILED
        (recoverable); bounded joins.

    core/monitoring/api_server.py
        stdlib ThreadingHTTPServer hard-bound to 127.0.0.1, bearer
        token constant-time hmac.compare_digest auth, fail-closed
        when tokenless. GET read endpoints /health /universe
        /subscriptions /runtimes /market /signals /positions /orders
        /account /risk /performance /errors (delegate to existing
        statuses()/performance()/portfolio.snapshot()/runtime.state()/
        subscriptions). POST /control with _assert_paper_capable
        (refuses LIVE-mode or any non-dry_run runtime). No GET mutates
        state; the API never calls poll() directly.

    core/monitoring/service.py + core/monitoring/__init__.py
        enabled()/config_token()/start_api() + fail-closed
        ControlApiConfigError.

    config/settings.py
        CONTROL_API_ENABLED / CONTROL_API_TOKEN / CONTROL_API_HOST /
        CONTROL_API_PORT / CONTROL_API_POLL_SECONDS.

Runtime Safety: PAPER-only (refuses non-dry_run), token + localhost,
fail-closed, no determinism/lifecycle change to engines, no
live/order path. No certificate/TLS code exists anywhere in the repo
and 9P-f does no outbound TLS (no verify=False/CERT_NONE workarounds
added).

Tests: tests/test_lifecycle_9pf.py (19), test_api_server_9pf.py (19),
test_monitoring_service_9pf.py (3) = 48 over the real
ThreadingHTTPServer bound to 127.0.0.1 on an ephemeral port. Full
canonical suite tests/ = 1488 passed (baseline 1440 + 48); compileall
clean; tracked .pyc restored. Commit: independent Phase 9P-f paper
control and monitoring API milestone (04739eb).

============================================================
PHASE 9P-g -- PRODUCTION PAPER ENTRYPOINT INTEGRATION
(STATUS 139)
============================================================

Narrow runtime-entrypoint integration wiring core/monitoring/service
into the production application: one coherent startup model,
main.py -> PAPER application -> (Control API | EngineLifecycle ->
RealTimeEngine -> PaperRuntime).

    core/runtime/lifecycle.py
        EngineLifecycle.wait([timeout]) blocking seam (returns the
        current state; releases when the lifecycle leaves a running
        state) via a _stopped_event wired into start() (cleared) /
        stop()/emergency_stop()/start-failure (set).

    core/monitoring/service.py
        _active_server duplicate-server guard (refuses a second start
        while one is running) + stop_api(server), and the production
        entrypoint helpers start_paper_service() -> (lifecycle,
        server), block_until_stopped() (waits then shuts down BOTH
        lifecycle and server), and run_paper_with_monitoring() (drives
        the engine via EngineLifecycle + gated API + block + clean
        shutdown).

    main.py
        The PAPER path now calls run_paper_with_monitoring(engine) in
        place of the blocking run_paper_forever(engine) (the explicit
        engine.refresh() was removed, since lifecycle.start() ->
        engine.start() -> refresh()). The API is enabled ONLY when
        explicitly CONTROL_API_ENABLED=true + token, so the disabled
        default preserves the pre-9P-g behaviour exactly;
        run_paper_forever is kept for direct-loop callers.

Runtime Safety: localhost + bearer token + PAPER-only preserved; no
live API, no mobile UI, no strategy/risk/order API; the API and the
PAPER runtime share the SAME authoritative engine; shutdown stops both
cleanly.

Tests: tests/test_paper_entrypoint_9pg.py (4) drives the real
acceptance path offline (real build_paper_engine with fakes + real
HTTP server -> GET /health /universe /performance -> POST
/control/stop -> the blocker drains and server+lifecycle+engine are
all stopped), plus the API-disabled-default case (lifecycle runs, NO
HTTP server); test_monitoring_service_9pf.py + test_lifecycle_9pf.py
grow 6 more (duplicate-server guard, start_paper_service +
block_until_stopped clean shutdown, wait() semantics). Full canonical
suite tests/ = 1498 passed (baseline 1488 + 10); compileall clean;
tracked .pyc restored. Commit: independent Phase 9P-g production PAPER
entrypoint integration milestone.

============================================================
PHASE 9P-h -- LIGHTWEIGHT DESKTOP CONTROL CLIENT
(STATUS 140)
============================================================

Thin, read-only-first Tkinter/ttk desktop control & monitoring
terminal over the existing Control API. The UI is a renderer/
controller only: it consumes GET reads and issues the four
allowlisted POST /control lifecycle commands -- it NEVER imports
engine internals, recomputes strategy/risk/position/order/
performance, constructs orders, or touches an exchange. stdlib-only,
zero new dependencies (requirements.txt unchanged; tkinter is
bundled with CPython). Launch: `python -m core.client.app` (or
`python -m core.client`).

    core/client/config.py       host/port/token/poll; defaults
                                127.0.0.1:8787; token from
                                QENGINE_CLIENT_TOKEN /
                                CONTROL_API_TOKEN env (never
                                hardcoded); as_dict() never exposes
                                the token.
    core/client/http_client.py  ApiClient GET/POST with bearer auth
                                via urllib, timeouts, typed errors
                                (Authentication/Connection/Timeout/
                                Server/BadResponse/ControlRejected);
                                ReconnectingClient tracks connected/
                                disconnected.
    core/client/poller.py       single daemon background worker; one
                                coordinated read cycle per interval
                                with a no-overlap guard; per-endpoint
                                error isolation; clean stop via Event;
                                results to a thread-safe queue.
    core/client/controller.py   pure display logic mapping CycleResult
                                snapshots to rows; the only write path
                                is ControlPath verbs start/stop/
                                restart/emergency_stop against the
                                real POST /control {"command": ...}
                                contract.
    core/client/app.py          DesktopClient: header connection/
                                engine status, Dashboard / Universe /
                                Market / Trading(Signals, Positions,
                                Orders, Account, Risk) / Performance /
                                Logs tabs, control bar with
                                confirmations (incl. a stronger
                                Emergency Stop confirmation), poll ->
                                queue -> root.after() drain (HTTP
                                never on the Tkinter thread),
                                DISCONNECTED -> CONNECTED auto-
                                reconnect with no engine restart.

Engine isolation: the client imports only stdlib + its own
core.client modules (grep-verified: no core.runtime/engine/strategy/
risk/execution/exchanges/pipeline, no TradeRegistry/BrokerEngine/
RealTimeEngine). No secrets in source; the token travels only in the
Authorization header, never logged/displayed/in URLs. No invented
endpoints (consumes exactly the 9P-f GETs + POST /control). Closing
the UI stops ONLY the poller -- it never stops the engine.

Tests: tests/test_client_9ph.py (25, stdlib-only, in-process fake
http.server Control API, no network): HTTP client GET/POST/bearer-
header/timeout/401/500/malformed-JSON/unreachable; ControlPath exact
/control + command body; ReconnectingClient connected/disconnected;
config defaults/custom/from_env/no-token-in-as_dict; poller results-
reach-queue / connection-failure-no-crash / clean stop; controller
dashboard/universe/empty-universe/performance-report/positions/
errors-"no-secret" rendering.

Offline runtime smoke verified (fake engine + REAL Control API +
REAL ApiClient/Poller): health RUNNING, universe BTCUSDT/ETHUSDT,
performance rows, POST /control stop -> lifecycle STOPPED +
engine.started False -- the client connects to the real 9P-f contract
end-to-end without network.

Full canonical suite tests/ = 1523 passed (baseline 1498 + 25);
full `compileall .` clean; tracked .pyc restored. Known limitations:
presentation-only (no charting/advanced analytics/order-entry/live/
credential management -- explicitly out of 9P-h scope); tkinter needs
a display (the logic is display-free and headlessly tested); single
universe view; no mobile/web client yet (future clients can later
consume the SAME API). Commit: independent Phase 9P-h lightweight
desktop control client milestone.

============================================================
PHASE 9P-i -- INTEGRATION & OPERATIONAL HARDENING / RUNBOOK
(STATUS 141)
============================================================

No-new-feature phase proving and documenting the complete existing
PAPER stack: fresh env -> engine -> Control API -> desktop client.

Client import-isolation verified as a COMMITTED regression test
(tests/test_client_isolation_9pi.py): a FRESH-interpreter subprocess
imports every core/client module and asserts the resulting core.*
import set is ONLY:

    core
    core.client.__init__ / __main__ / app / config / controller
    core.client.http_client / core.client.poller

-- never runtime/live/risk/execution/exchanges/pipeline/research/
backtesting/analytics/registry/universe/events/replay/history/
scanning/market_state etc., and no engine objects (TradeRegistry,
BrokerEngine, RealTimeEngine, PipelineContext, InstitutionalPipeline,
PipelineRegistry, PaperRuntime, PaperExecutionAdapter, DeltaOrder-
Executor, DeltaExchange).

core/client/app.py docstring invalid-escape fix (SyntaxWarning removed).

Full canonical suite tests/ = 1535 passed (1523 baseline + 12 new:
test_integration_9pi.py 10 + test_client_isolation_9pi.py 2). No new
runtime dependencies (requirements.txt unchanged). Core/monitoring/
runtime/config/data unchanged (audit-only, no defects requiring code
change).

============================================================
PHASE 7 -- BREAKOUT DIRECTIONAL ASYMMETRY RESEARCH
(STATUS 114)
============================================================


RESEARCH-ONLY. New namespace core/research/ + package
core/research/breakout_asymmetry/ whose purpose is to establish
WHY the same BREAKOUT_CONTINUATION architecture behaves differently
per direction (reported: bearish PF 3.05 / +0.2769R / MAE-DD
23.6%; bullish PF 0.92 / -0.0185R / MAE-DD 321.5%). It is
DELIBERATELY SEVERED from production: it consumes ONLY frozen
CausalValidationState records (core/setup/causal_validation.py)
and emits only evidence -- never a strategy change. Nothing in the
research package is imported by any engine; the boundary is
documented in core/research/__init__.py.

    features.py      -- 16-axis FeatureExtractor -> FeatureRow
       (direction, entry context, risk geometry -- risk ATR,
       entry distance ATR, stop ATR distance, reward:risk --
       zone age, score, MFE/MAE ATR windows, trigger rate,
       fill-path). Identical feature families for BOTH directions
       (protocol 7A).
    outcomes.py      -- OutcomeClassifier + OutcomeProfile with
       buckets STOP_HIT / TARGET_HIT / UNRESOLVED / EXCLUDED /
       NEVER_ENTERED, conservative WIN/LOSS, and MFE / MAE /
       payoff / PF / expectancy / win-rate / MAE-DD -- full
       outcome DECOMPOSITION, not just aggregates (7B).
    origins.py       -- OriginDecomposition + decompose_origins
       attributing the measured asymmetry to origin A market /
       B structure-generation / C setup-selection / D breakout-
       trigger / E stop-target geometry (MFE + MAE + RR as three
       metric entries) / F execution / G data-sample imbalance,
       each with present + asymmetry (7C).
    counterfactual.py-- CounterfactualStudy mirror study; 7D
       verdict EXECUTION-HELD-CONSTANT by construction, because
       both directions already share identical causal execution.
    report.py        -- AsymmetryReport with verify() / hypothesis()
       / summary() / dump(); load_dataset consuming a sequence of
       CausalValidationState / dicts / a JSON path.
    demo.py          -- builds a synthetic mirror dataset reproducing
       the reported shape and dumps results/phase7_report.json.
    results/         -- phase7_report.json output directory.

All offline, stdlib-only, synthetic causal data. Tests:
tests/test_breakout_asymmetry.py (18). The evidence (mirror
dataset) shows the asymmetry is dominated by setup / geometry
(origin E -- deep bullish MAE, unfavorable bullish reward:risk),
NOT execution (origin F held constant). A directional
BREAKOUT_CONTINUATION BULLISH/BEARISH policy (protocol 7E) is NOT
introduced in this phase -- it remains gated behind out-of-sample
validation on real (non-synthetic) causal data.

===========================================================
PHASE 7E -- REAL-DATA OUT-OF-SAMPLE CAUSAL VALIDATION
(STATUS 115)
===========================================================

RESEARCH-ONLY. Adds core/research/breakout_asymmetry/realdata.py +
results/phase7e_real_oos_report.json. The milestone that answers the
single question gating any directional policy: does the SYNTHETIC
directional hypothesis (bearish-strong / bullish-weak) survive on
UNSEEN real causal data? It is DELIBERATELY SEVERED and uses the
IMMUTABLE d3eb2c8 baseline: it consumes ONLY the FROZEN production
causal pipeline (PipelineContext + InstitutionalPipeline + EventBus +
TradeSimulator + Backtester.run() with ENTRY_MODE pinned to
BREAKOUT_CONTINUATION, then restored verbatim) and emits only evidence
-- no threshold, no strategy, no frozen code changes.

    fetch_and_cache_oos_candles() -- fetches ~10,000 real BTCUSDT
        1m bars live from Delta via HistoricalLoader, caches the
        pinned OOS window to the git-ignored
        data/history/BTCUSDT_1m_oos.json for reproducible offline
        re-runs, returns chronological Candle objects (7E.2).
    run_oos_causal_pipeline()     -- replays real candles through the
        identical frozen causal path and returns (states, backtester);
        restores ENTRY_MODE / ACTIVE_ENTRY_MODES verbatim (7E.3).
    _verdict()                    -- the 7E.9 A/B/C gate (GO / NO-GO /
        INCONCLUSIVE). It tests the SIGN of the directional profit
        signal (win-rate + expectancy), NOT a bare geometric
        |asymmetry|, so a real gap that is absent or REVERSED reads
        NO-GO (outcome B) rather than a spurious GO.
    run_7e() / main()             -- build the AsymmetryReport over
        the real states, render the verdict, dump
        results/phase7e_real_oos_report.json with provenance metadata.

report.py::verify() was reconciled to the FULL classified population
(692 triggers == 692 outcomes == 692 bucketed) with never_entered (18)
surfaced as a diagnostic (triggers-without-entry are part of the causal
population). Tests: tests/test_breakout_asymmetry_7e.py (8). REAL
RESULT (10,000 bars / 692 settled states: 268 BULLISH / 424 BEARISH):
both directions PROFITABLE, bullish slightly STRONGER (win 79.2% vs
74.5%, PF 1.32 vs 1.23, expectancy +0.067R vs +0.059R); the
bearish-strong / bullish-weak hypothesis is REJECTED (win-rate gap
-4.7pp below the 5.0pp floor, reversed sign) -> 7E VERDICT NO-GO
(outcome B). The 7E gate is NOT crossed -- NO directional
BREAKOUT_CONTINUATION BULLISH/BEARISH branch; baseline d3eb2c8
immutable; no production code modified.

============================================================
PHASE 8 -- PORTFOLIO RISK & CAPITAL COORDINATION (core layer)
(STATUS 116)
============================================================

The portfolio risk gate is promoted from a backtest-only adapter
to a FIRST-CLASS core/risk/portfolio.py::PortfolioRiskManager
that now governs BOTH regimes -- the backtest path
(PortfolioBacktester) AND the live/paper path
(RealTimeEngine/PaperRuntime/BrokerEngine) -- so one shared
portfolio policy coordinates aggregate exposure / concurrency /
directional / correlated / drawdown / risk-budget / capital
allocation across every symbol in BOTH regimes.

CARDINAL INVARIANT (carried forward verbatim): the portfolio
layer GATES (accept/decline) an otherwise-valid trade but NEVER
mutates the setup's entry / stop / target / direction / strategy
logic. Flow stays:

    SymbolPipeline -> Strategy decision -> RiskEngine ->
    OrderIntent -> Portfolio Risk Gate -> Execution

    core/risk/portfolio.py -- PortfolioRiskManager:
       order_allows(order)   PURE DECISION -- inspects the order +
          current portfolio state, returns True/False, sets
          last_reason on a False verdict; NEVER mutates the order,
          the setup, the strategy, or the ledger.
       register_open(order)  BOOKKEEPING -- books an opened trade
          into the ledger (risk / notional / direction / group).
       release_closed(trade) BOOKKEEPING -- releases a closed
          trade's exposure + folds realized PnL into equity /
          peak-equity / daily-loss.
       Legacy-compatible surface (can_open / register_trade /
          close_trade / current_risk / open_positions /
          open_by_symbol / equity / reset) is a drop-in SUPERSET
          of risk/portfolio_risk.py -- PortfolioBacktester's
          adapter works verbatim with NO change.
       Optional DISABLED-BY-DEFAULT caps: max_positions;
          max_portfolio_risk (ABSOLUTE aggregate-R budget matching
          the legacy manager, independent of equity);
          max_total_exposure_pct / max_directional_risk_pct /
          max_correlated_risk_pct / max_daily_loss_pct
          (equity-scaled %); max_per_symbol_notional (absolute
          currency); equity basis; correlation_groups
          (symbol -> group map).
       Properties: current_risk / current_notional /
          open_positions / direction_risk / correlated_risk /
          equity / realized_pnl / peak_equity / drawdown /
          drawdown_percent; snapshot(); reset().
       _dims() normalizes an OrderIntent / Trade-like object OR
          primitives (risk_amount fallback expected_loss).

    core/live/broker_engine.py -- BrokerEngine gained optional
       portfolio_gate(order) / portfolio_release(closed_trade)
       hooks mirroring the Backtester contract. The gate is
       consulted in _route() right after the OrderIntent resolves
       and BEFORE open_trade / execute; a False verdict returns
       WITHOUT routing (order/ledger untouched, logged
       PORTFOLIO_GATE_DECLINED). portfolio_release is called
       after a close in BOTH _book_closed (paper) AND
       _book_live_close (live).

    core/runtime/paper_runtime.py -- PaperRuntime threads the
       gate/release into its BrokerEngine.

    core/runtime/realtime_engine.py -- RealTimeEngine gained
       portfolio_manager=None (defaults to a default-NEUTRAL
       PortfolioRiskManager so live/paper behavior is unchanged
       unless caps are supplied). Every PaperRuntime shares the
       SAME _portfolio_gate / _portfolio_release closures bound to
       that manager; .portfolio exposes it for observability.

SOURCE CENSUS (this phase's live wiring edges, AST-verified):
    core/runtime/realtime_engine.py imports
        core.risk.portfolio (PortfolioRiskManager);
    BrokerEngine / PaperRuntime / PortfolioBacktester induce no
    new core.risk.portfolio import -- they consume the manager via
    the injected gate/release closures and the legacy duck-typed
    surface. risk/portfolio_risk.py (legacy) is unchanged and
    remains on the LIVE import surface; the core manager is its
    drop-in superset for new wiring.

Default neutrality: with no caps configured the gate always
allows, so a default run changes nothing. Tests:
tests/test_portfolio_risk_core.py (17). Full suite 675/675 OK,
compileall clean. Phase 7E NO-GO stands -- no directional policy
was introduced.

============================================================
PHASE 8B -- SHARED PORTFOLIO CAPITAL & ALLOCATION (core layer)
(STATUS 117)
============================================================

Infrastructure (NOT strategy optimization): lays the
reservation-based capital-lifecycle foundation on which the Phase
8 gate now draws. Adds three dedicated core modules:

    core/risk/capital.py -- SharedCapital: reservation-based
       equity envelope.
         equity           = basis + realized PnL
         reserved_capital = sum of live reservations
         available_capital= deployment_cap - reserved_capital
       can_reserve(amount) is a PURE DECISION (sets last_reason =
       insufficient_capital on decline, never mutates);
       reserve(rid, amount) / release(rid, pnl) / cancel(rid) are
       BOOKKEEPING -- cancel returns capital with NO realized PnL
       (the failed-execution-after-reservation path).

    core/risk/portfolio_state.py -- CapitalCandidate (pure data:
       symbol / direction / correlation_group / risk / capital;
       from_order() reads the canonical OrderIntent fields) +
       PortfolioState: the UNIFIED state owning the SharedCapital
       envelope, the risk budget (max_portfolio_risk, absolute R),
       equity-scaled total / directional / correlated % caps,
       absolute per-symbol capital, correlation_groups, and the
       RESERVATION LEDGER (rid -> {symbol, direction, group, risk,
       capital}). can_accept(candidate) is the PURE decision gate
       (risk_budget / insufficient_capital / total_exposure /
       per_symbol_capital / directional_limit / correlation_limit)
       with last_reason set on decline; reserve(candidate) ->
       rid; release(rid, pnl) / cancel(rid) manage the lifecycle.

    core/risk/allocator.py -- CapitalAllocator + AllocationResult:
       DELIBERATELY DETERMINISTIC (strict input order, NO ranking).
       Reproduces the canonical example: equity $10,000 /
       max_portfolio_risk 2R -> BTC ACCEPT 0.8R / ETH ACCEPT 0.7R /
       SOL REJECT-DEFER (0.8+0.7+0.9=2.4R > 2R, remaining 0.5R).
       Opportunity selection belongs to a later 8C / Confluence
       layer, NOT here.

WIRING (default-neutral, parity by construction): PortfolioBacktester
and RealTimeEngine each gained optional portfolio_state=None. When
provided, the per-symbol gate/release run through the SHARED state
lifecycle (can_accept + reserve on open; release on close folding PnL
into shared equity), so backtest AND paper/live consume the SAME
shared capital -- verified byte-identical (+10 PnL folds 10000 ->
10010 through both paths). When None (default) behavior is UNCHANGED.
Reservation ids are mapped symbol->rid (single-position-per-symbol),
held on the orchestrator and cleared on release / run reset. Phase 7E
NO-GO and the Phase 8 gate are UNCHANGED.

SOURCE CENSUS (live wiring edges):
    backtesting/portfolio_backtester.py + core/runtime/realtime_engine.py
        import core.risk.portfolio_state (CapitalCandidate) lazily
        in the state-path hooks;
    core/risk/portfolio_state.py imports core.risk.capital
        (SharedCapital, _fnum);
    core/risk/allocator.py imports core.risk.portfolio_state
        (CapitalCandidate, PortfolioState);
    the legacy risk/portfolio_risk.py and Phase 8 core/risk/portfolio.py
        remain unchanged and on the LIVE import surface.

Tests: tests/test_portfolio_capital_8b.py (20). Full suite 695/695
OK, compileall clean. The Confluence Engine (Phase 9) will be built
ON this foundation later -- Wyckoff/ML not yet, and no
BREAKOUT/rules/7E results modified.

============================================================
PHASE 9A -- RESEARCH JOURNAL + CAUSAL OPPORTUNITY LEDGER,
FOUNDATION (STATUS 118)
============================================================

Infrastructure-only layer (NOT AI/ML/strategy optimization). Adds a
durable, deterministic research record of every market OPPORTUNITY
LIFECYCLE (setup -> eligibility -> order -> fill/expiry/invalidation
-> trade -> close) as a pure OBSERVER of the frozen engine. The
journal NEVER alters a decision, order, setup, risk or portfolio
object; it reads the settled authoritative state (PipelineContext +
TradeRegistry) at the end of every bar and appends research facts.

The journal is a deterministic, append-safe observer:
  * explicit Provenance (BACKTEST / PAPER / LIVE) -- never inferred
    from filenames or runtime environment;
  * deterministic event ids (per-journal sequence + bar), NO random
    UUIDs -- identical candles yield an identical event stream;
  * append-safe stdlib storage (in-memory repository for this phase;
    serialisation helpers are stdlib-compatible for a future
    append-only JSON document store);
  * multi-symbol keyed by canonical identity, ordered by
    (exchange, instrument_id);
  * fail-safe recording -- a research error is swallowed + logged,
    never propagated into the trading path.

OBSERVED FACTS ONLY. Unfilled-order disclosure (min/max excursion,
entry_distance, bars_pending, entry_reached) and post-terminal
missed-continuation facts (was the target level reached after
expiry? what extremes did the market print? -- bounded window, no
hypothetical fill) are recorded. Counterfactual / simulation
outcomes (SimulatedTrade, CounterfactualOutcome, StrategyExperiment)
are SEPARATED and DEFERRED to later phases -- NOT represented here.

Part of the no-AI / no-ML standing rule: this layer is pure
fact-recording infrastructure. No Wyckoff, no sklearn/causal-ML, no
lookahead, no OOS contamination. Phase 7E NO-GO and 6C/6D/6E/7/8/8B
frozen layers are untouched (only OPTIONAL journal params added).

LIVE IMPORT SURFACE (new files):
    core/research/journal/research_enums.py       -- Provenance /
        SetupLifecycle / OrderLifecycle / Result / EntryReached /
        EventType (stable string contracts)
    core/research/journal/research_event.py       -- ResearchEvent
    core/research/journal/setup_record.py         -- observed setup
        facts incl. verbatim rejection reasons
    core/research/journal/order_record.py         -- observed order
        lifecycle + excursion facts
    core/research/journal/trade_record.py         -- observed trade
        outcome (R = pnl/risk_amount; MAE/MFE consumed from the
        authoritative CausalValidator where available)
    core/research/journal/opportunity_record.py   -- immutable
        unified lifecycle view
    core/research/journal/research_repository.py  -- append-safe
        storage + deterministic ordering
    core/research/journal/research_journal.py     -- per-bar
        observer/reconciler (fail-safe)
    core/research/journal/journal_query.py        -- read-only
        filters
    core/research/journal/journal_summary.py      -- counts +
        breakdowns (reuses WIN/LOSS/R/PnL language)

LIVE WIRING EDGES (all default-off, behaviour identical when None):
    backtesting/backtester.py
        run(candles, journal=None) -- observes at the settled end of
        each bar; finalize() once after the loop.
    backtesting/portfolio_backtester.py
        run(history, journal=None) -- shares one journal across
        every symbol (multi-symbol aggregation).
    core/runtime/paper_runtime.py
        __init__(..., journal=None) + process_closed_candle()
        observes the settled bar with provenance="PAPER" (fail-safe
        try/except).
    core/runtime/realtime_engine.py
        __init__(..., journal=None) -- passes the shared journal to
        every PaperRuntime; the narrowest LIVE attach point (a
        future live engine can call journal.on_bar_observed itself).
        Live trading is NOT enabled by this phase.

Wiring pattern: the journal is carried as an explicit optional
argument into the already-existing per-bar loop -- it is NOT a
fabricated engine hook and does NOT participate in the EventBus (the
Backtester uses publish / BrokerEngine calls on_candle directly, so
no typed trading events exist to subscribe to).

Tests: tests/test_research_journal_9a.py (19). Full suite 714/714
OK (695 + 19 new; zero existing-test changes), compileall clean.
This milestone is the foundation for the Causal Opportunity Ledger
queries; simulated/counterfactual analysis and any AI/ML are
explicitly deferred. No BREAKOUT/rules/7E results modified.

============================================================
PHASE 9B -- DETERMINISTIC PARAMETER EXPERIMENTATION +
COUNTERFACTUAL OPPORTUNITY REPLAY LAB (STATUS 119)
============================================================

Research / simulation ONLY (NOT production optimization, NOT AI/ML).
Adds the deterministic machinery that answers, for an explicitly
supplied configuration: "what would have happened at historical time T
under a different RR / expiry / entry-offset / entry-model / stop /
target geometry?". It consumes recorded OpportunityRecords + historical
candles; it NEVER feeds experimental decisions back into production.

COUNTERFACTUAL nature: every result carries explicit
COUNTERFACTUAL / SIMULATED provenance (provenance.py), distinct from
the 9A BACKTEST/PAPER/LIVE provenance. SimulatedTrade can never enter
the production TradeRegistry.

CAUSAL replay (opportunity_replay.py):
  * the decision bar is the LAST bar known at decision time; the
    experimental entry is derived from decision-time facts only;
  * the entry model may fill from decision+1 onward;
  * once filled, the trade is walked forward with the SAME
    stop-before-target exit ordering the production TradeSimulator uses;
  * MAE / MFE are tracked from the fill bar onward only;
  * decision-time ATR reuses core/indicators/atr (no lookahead).

BASELINE isolation: every experiment identifies baseline_id="baseline"
(the frozen production config) and never compares silently against a
newer configuration.

DETERMINISTIC experiments: identical candles + identical journal +
identical config yield identical results. experiment_id is a stable
sha1 hash of config params + baseline id (NO random UUIDs, no
timestamps, no object ids). ParameterGrid preserves caller insertion
order and never mutates base_config.

PRODUCTION isolation: the lab reads OpportunityRecords + candles only.
It does not modify production strategy, execution, risk, portfolio,
Phase 7/7E results, or live trading. No optimization thresholds are
tuned, no automatic parameter selection, no ML.

LIVE IMPORT SURFACE (new files under core/research/lab/):
    __init__.py            -- public API (14 exports)
    provenance.py          -- LabProvenance (COUNTERFACTUAL/SIMULATED)
    experiment_config.py   -- immutable frozen ExperimentConfig
    simulated_trade.py     -- first-class counterfactual trade record
    counterfactual.py      -- CounterfactualOutcome (one replay result)
    opportunity_replay.py  -- causal candle-by-candle replay engine
    entry_models.py        -- experimental LIMIT/BREAKOUT/MARKET entry
    exit_models.py         -- experimental stop/target geometry
    evidence.py            -- immutable EvidenceSnapshot (future AI/ML)
    metrics.py             -- deterministic metrics over simulated trades
    experiment_result.py   -- machine-readable ExperimentResult
    experiment_runner.py   -- batch replay + deterministic experiment_id
    parameter_grid.py      -- thin deterministic Cartesian sweep (9B)
    recovery.py            -- opportunity recovery classification

parameter_grid.py THIN ORCHESTRATION ONLY: it contains no trading /
entry / breakout / risk / PnL / indicator logic. It answers "what
happened under each explicitly specified configuration?" and does NOT
rank, optimize, or select configurations -- automatic optimization is
deferred to a later research/AI layer.

Tests: tests/test_parameter_grid.py (17). Full suite 731/731 OK
(714 + 17 new; zero existing-test changes -- the lab is additive, no
production edits). No BREAKOUT/rules/7E results modified.

============================================================
PHASE 9C -- COUNTERFACTUAL OPPORTUNITY SIMULATOR, STATUS 120
(2026-09-01; research ONLY, NOT production optimization)
============================================================

NEW core/research/counterfactual/ sub-package (7 modules; the first-class
models are REUSED from the frozen 9B lab, never duplicated):

  counterfactual_config.py -- immutable CounterfactualConfig wrapping
      the deterministic 9B ExperimentConfig. Explicit unknown-param
      rejection; unsupported entry model (FVG_RETRACE /
      DISPLACEMENT_RETEST, measured but not implemented as deciders) ->
      loud ValueError; outcome_bars (explicit outcome horizon; None ==
      end of series) validated. Deterministic identity reuses the 9B
      experiment_id_for hash (merged params + outcome horizon +
      baseline) -- NO random UUIDs. setup_view() builds a minimal
      setup-like view for the canonical deciders without mutating any
      production/journal object.
  opportunity_categories.py -- deterministic classification of an
      OpportunityRecord derived ONLY from authoritative 9A facts
      (terminal_outcome + verbatim rejection_reasons): FILLED /
      REJECTED / MISSED_CONTINUATION / INVALIDATED /
      ENTRY_NOT_REACHED / NON_EVALUABLE.
  opportunity_simulator.py -- OpportunitySimulator.simulate: the strict
      deterministic one-opportunity replay. Explicit is-not-None source
      extraction (a present 0.0 is NOT missing); direction validation;
      experimental geometry validation (finite, risk > 0, stop/target on
      the correct side; invalid -> deterministic NON_EVALUABLE, never
      RR=0); CANONICAL entry routing through the frozen production
      deciders core/execution/entry_model.get_entry_model (LIMIT_RETEST
      fills at the resting entry, MARKET_CONFIRMATION at the trigger
      close, BREAKOUT_CONTINUATION at the NEXT bar OPEN) -- entry
      semantics are NOT reimplemented (this closes the 9B gap where the
      lab reimplemented them); a mode with no canonical decider is
      NON_EVALUABLE + warning, never invented. Entry window is
      expiry-bounded; NO_EXECUTABLE_BAR (BREAKOUT trigger on the last
      bar) is DISTINCT from ENTRY_NOT_REACHED. Outcome walk runs within
      CounterfactualConfig.outcome_bars (default None == production
      TradeSimulator holding contract), INCLUDING the fill bar exactly
      as production's paper engine does (open_trade then update on the
      same candle); stop-before-target ordering mirrors
      TradeSimulator.update; R / PnL / MAE / MFE from the ACTUAL fill
      (risk = |fill - stop|; LOSS == -1R) matching the canonical
      _r_multiple contract; bars_in_trade counts the fill bar (prod
      bars_held parity).
  simulated_trade.py / counterfactual_outcome.py -- documented REUSE
      shims for frozen 9B SimulatedTrade / CounterfactualOutcome
      (provenance === COUNTERFACTUAL).
  counterfactual_runner.py -- CounterfactualRunner: run_config (one
      config over all opportunities), run_configs (dict keyed by
      deterministic experiment id, no overwrites), grid (native 9B
      ParameterGrid integration; every combination evaluated
      independently, deterministic order, deterministic unique ids,
      base config preserved, never blended).

IMMUTABILITY / ISOLATION: the simulator reads OpportunityRecords +
candles only. Every successful simulation materializes to a
COUNTERFACTUAL SimulatedTrade that NEVER enters TradeRegistry / Account
/ PortfolioState / SharedCapital / paper / live / production journal;
the source OpportunityRecord is byte/value unchanged after 1 and after
many simulations. NO lookahead, NO optimization selection, NO ML/AI --
recovery is measured only, never pushed to production. 7E/7/8/8B/6C-6E
frozen layers untouched.

Tests: tests/test_counterfactual_simulation.py (47). Full suite 778/778
OK (731 + 47 new; zero existing-test changes -- the package is additive,
no production edits). Deterministic-id + grid isolation + no-ledger-
mutation + no-lookahead + canonical-entry-parity + stop-before-target
parity + opportunity-recovery all proven by tests above. No
BREAKOUT/rules/7E results modified.

============================================================
PHASE 9D -- EXPERIMENT MATRIX + RESEARCH ANALYZER, STATUS 121
(2026-09-01; research ONLY, NOT production optimization)
============================================================

NEW core/research/analyzer/ sub-package (9 modules; composes the FROZEN
9B experiment-id / ParameterGrid / metrics machinery and the FROZEN 9C
CounterfactualConfig / CounterfactualRunner / opportunity categories --
nothing is duplicated):

  baseline.py -- read-only BaselineOutcome view of an OpportunityRecord.
      Maps the frozen 9A trade facts onto the SAME outcome surface the
      metric bundles read so baseline and experiment measure
      like-for-like. Filled records without a terminal result stay
      UNSETTLED; r taken from the authoritative journal r else
      pnl / risk_amount (None-guarded, never NaN); mae/mfe kept None
      when the journal omits them, never fabricated. Never mutates the
      source record.
  experiment_metrics.py -- metrics_for: reuses the frozen 9B lab.metrics
      formulas (WIN := pnl>=0, PF := gross profit / gross loss,
      expectancy := avg pnl, drawdown over an ordered equity curve) and
      augments total_R / avg_R / median_R, gross_profit_R /
      gross_loss_R, avg/median MAE and MFE, avg/median bars-to-entry.
      group_metrics / group_sizes by direction / exchange / instrument /
      timeframe / strategy / category / entry_model / experiment_id
      (sorted, deterministic). Zero denominators -> 0.0; PF inf-parity;
      never NaN.
  opportunity_analysis.py -- category distribution reusing ONLY the 9C
      classify_opportunity vocabulary (no invented classes); verbatim
      rejection-reason distribution; missed-continuation counts.
  recovery_analysis.py -- RecoveryReport: per-opportunity deterministic
      transition BASELINE-category -> EXPERIMENT-state composed from
      existing tokens (REJECTED -> WIN / LOSS / STILL_REJECTED,
      ENTRY_NOT_REACHED -> WIN / STILL_NOT_REACHED, MISSED_CONTINUATION
      -> WIN / STILL_MISSED, INVALIDATED / NON_EVALUABLE, FILLED ->
      BETTER_RESULT / WORSE_RESULT / SAME_RESULT / NOT_FILLED /
      UNSETTLED / NOW_SETTLED). Unfilled-opportunity recoveries are
      preserved by canonical id. COST of recovery: additional trades /
      wins / losses, incremental_R, incremental_pnl, recovery_rate,
      profitable_recovery_rate, rejected-reason recovery (verbatim
      reasons -> recovered/wins/losses buckets), missed-continuation
      ISOLATED from other recoveries. No invented vocabulary; malformed
      records warned and skipped.
  comparison.py -- ExperimentComparison: baseline-vs-experiment and
      experiment-vs-experiment deltas (incremental fills/wins/losses/
      unsettled, incremental_R, incremental_pnl, delta expectancy /
      win-rate / PF / MAE / MFE, sample counts). Inf-safe delta (never
      NaN); retains exact experiment_id + config provenance; NEVER
      ranks or recommends a production change.
  robustness.py -- deterministic lightweight assessment: insufficient /
      small sample, explicit no-statistical-significance claim,
      loss-expansion flag, directional-imbalance flag, in-sample-only ->
      OOS-required. No statistical procedure; no overfitting language; a
      result with 2 trades is never equated with a result with 200.
  experiment_matrix.py -- ExperimentMatrix: composes the FROZEN 9B
      ParameterGrid (caller insertion order, empty ranges -> zero
      combos, base config never mutated, unknown keys fail loudly)
      crossed with the 9C-only outcome_bars dimension into independent
      CounterfactualConfigs with deterministic 9C experiment ids.
      No shared state; never blended.
  research_report.py -- ResearchReport: deterministic BASELINE /
      EXPERIMENTS / RECOVERY / REJECTED_OPPORTUNITIES /
      ENTRY_MODEL_COMPARISON / DIRECTIONAL / METRICS / ROBUSTNESS /
      WARNINGS sections preserving exact config provenance; machine
      readable to_dict() + human render(); carries an explicit
      ANALYZER-NOT-OPTIMIZER statement (no promotion, OOS required).
  research_analyzer.py -- ResearchAnalyzer: orchestrates read-only
      analysis of records + (CounterfactualConfig, outcomes) bundles.
      ALWAYS computes a like-for-like per-experiment baseline restricted
      to the very opportunities that experiment evaluated so incremental
      fills / wins / losses / R are honest deltas, not population
      artefacts. Strict provenance guard: every experiment must carry
      its exact CounterfactualConfig or the analyzer fails loudly.
      Convenience analyze_results (9C dict) / run_and_analyze
      (matrix + 9C runner + analyzer). Simulation ALWAYS stays in 9C;
      the analyzer only reads already-causal produced facts (no
      re-simulation, no lookahead).

ISOLATION / BOUNDARIES: reads OpportunityRecords + 9C counterfactual
outcomes only, COUNTERFACTUAL provenance only. NEVER mutates
OpportunityRecord / CounterfactualConfig / CounterfactualOutcome /
Journal / TradeRegistry / Account / PortfolioState / SharedCapital. NO
production / journal / ledger / portfolio mutation; no AI / ML; no
optimizer; no automatic parameter selection or promotion; no ranking
("higher expectancy", "higher recovery" -- not "best"). No lookahead.
The analyzer reports evidence only; any future AI research layer
(9E/9F/9G) consumes exactly this structured evidence and still requires
human review + OOS validation before production consideration. Phase 7E
NO-GO and 6C/6D/6E/7/8/8B frozen layers untouched (fully additive; no
production edits).

FULL SUITE: 823/823 OK (778 baseline + 45 new 9D; zero existing-test
changes). compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E results modified.

============================================================
PHASE 9O -- RESEARCH UX: RECOMMENDATION READBACK, STATUS 132
(2026-09-02; autonomous, deterministic, research-only explanation layer
that consumes the frozen 9N RecommendationReport and turns it into a
human-usable readback of WHY each recommendation exists, what evidence
supports it, what failed, what remains uncertain, and exactly why it is
still research-only -- consuming ONLY the frozen 9N report and never
re-running OOS / conditional ML / regime; it never selects a strategy,
never emits an order, never touches a ledger, never changes a parameter)
============================================================

NEW core/research/readback/ sub-package (3 modules + __init__; imports
ONLY the core.research.* research surface -- never core.execution|trading|
ledger|account|portfolio|risk|market_data|setup|pipeline; no AI-SDK /
scipy / random / uuid / datetime; numpy-free; consumes ONLY the frozen
9N report -- it never re-simulates, never re-derives, never optimizes,
and never modifies strategy parameters).

  constants.py       -- closed RESEARCH_VERDICTS SEVEN_E_BLOCKED /
      NO_EVIDENCE / INCONCLUSIVE / REJECTED / REQUIRES_MORE_OOS /
      CONDITIONAL / PROMISING / VALIDATED_RESEARCH_FINDING (the MAXIMUM
      possible statement, with NO TRADABLE member by construction);
      PRODUCTION_STATUS always RESEARCH_ONLY; closed UNCERTAINTY_ROSTER
      + NEGATIVE_EVIDENCE_ROSTER; NEVER_EMITTED TRADABLE_STRATEGY /
      TRADABLE-GO / PRODUCTION_READY; EXPLANATION_ASPECTS; frozen review
      protocol (REVIEW_CONSUMES 9N, REVIEW_MODIFIES_NOTHING).
  types.py           -- frozen ReadbackEntry (research_verdict /
      evidence_status / title / claim / rationale / per-aspect evidence
      dict / closed uncertainty tags / production_status) + frozen
      ReadbackReport (deterministic O+10hex report_id from a canonical
      payload EXCLUDING report_id, stable under reordered entries;
      is_tradable property always False; to_dict / to_json / render /
      emission_check()).
  explain.py         -- verdict_for_9n_status: total injective 9N -> 9O
      verdict mapping (top 9N tier ROBUST_RESEARCH_FINDING ->
      VALIDATED_RESEARCH_FINDING, never TRADABLE_STRATEGY);
      explain_entry / explain_report: 1:1 recommendation -> ReadbackEntry
      pairing joined on the shared (hypothesis_id, oos_report_id) key
      both carry; build_readback constructor/validator normalizes +
      sorts, validates verdicts + uncertainty tags, forces production
      status RESEARCH_ONLY and rejects any tradable claim.
  __init__.py        -- public research-only surface (16 exports).

The central boundary of this phase: VALIDATED_RESEARCH_FINDING is
allowed (a research artifact); TRADABLE_STRATEGY is IMPOSSIBLE at this
boundary by construction -- the closed verdict vocabulary has no such
member and emission_check() verifies NEVER_EMITTED tokens are absent
from the ACTUAL serialized body.

Recording: none -- a 9O readback persists NOTHING, never lands a strategy,
never changes a parameter, and never lands a trade or a ledger row;
results are ephemeral research objects only.
Phase 7E NO-GO and 6C/6D/6E/7/8/8B and 9A-9N frozen layers untouched
(fully additive; no production edits).

Proof: tests/test_researcher_9o.py 48/48 OK (closed verdict vocabulary
with no tradable member + entry/report reject any tradable verdict,
PRODUCTION_STATUS enforced, total injective 9N->9O verdict mapping over
the full 9N alphabet, 1:1 entries == recommendations + joined evidence
from the frozen finding, aspect coverage OOS/regime/discovery/
counterfactual/baseline/supporting-metrics/negative, closed uncertainty
+ negative-evidence tags, deterministic report id + rerun + reordered-
build equal + full equality, frozen report/entry + is_tradable False +
production_status immutable, NEVER_EMITTED tokens absent from the
serialized body, no production imports/import-boundary + no
random-uuid-datetime-scipy-sklearn, canonical e2e report_id O881c3a9a39
over the frozen 9N Ne4c9dc7886, validated-vs-tradable boundary render
and emission_check, empty report honest).

Isolation: no shared mutable state, no registry, no .env, no network;
a 9O readback exists only in-process and dies with the process; the
strongest possible statement is a VALIDATED_RESEARCH_FINDING, never a
TRADABLE_STRATEGY, and production_status is always RESEARCH_ONLY.

FULL SUITE: 1355/1355 OK (1307 prior + 48 new 9O; zero existing-test
changes). compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E results modified.

============================================================
PHASE 9N -- RESEARCH RECOMMENDATION & EVIDENCE READBACK, STATUS 131
(2026-09-02; autonomous, deterministic, research-only readback layer
that consumes the frozen 9M OOS / 9L conditional-ML / 9K regime reports
and turns them into actionable, human-readable research
recommendations: for every consumed discovery it re-states WHAT was
discovered, WHY it might have worked, WHERE it worked, WHERE it failed,
HOW robust it is, and WHAT should be investigated -- ALWAYS as an
INVESTIGATE_FURTHER directive; never a strategy-change, never a
deployment, never production consideration)
============================================================

NEW core/research/recommendation/ sub-package (7 modules; imports ONLY
the core.research.* research surface -- never core.execution|trading|
ledger|account|portfolio|risk|market_data|setup|pipeline; no AI-SDK /
scipy / random / uuid / datetime; numpy-free; consumes frozen FROZEN
reports -- it never re-simulates, never re-derives, never optimizes, and
never modifies strategy parameters).

  constants.py      -- closed conservative vocabulary: 7E_BLOCKED /
      NO_EVIDENCE / INCONCLUSIVE / REJECTED / REQUIRES_MORE_OOS /
      CONDITIONAL / PROMISING / ROBUST_RESEARCH_FINDING; locked
      INVESTIGATE_FURTHER directive + explanatory text; the five
      READBACK_QUESTIONS; closed WHY/WHERE narrative rosters; frozen
      review protocol (REVIEW_PROTOCOL_FROZEN, REVIEW_CONSUMES 9M/9L/9K,
      REVIEW_MODIFIES_NOTHING).
  ladder.py         -- deterministic TOTAL mapping of the frozen 9M
      final_status + conditional + robustness to the 9N vocabulary:
      7E NO-GO always 7E_BLOCKED (never reviewed); UNAVAILABLE ->
      NO_EVIDENCE; INCONCLUSIVE -> INCONCLUSIVE; REJECTED -> REJECTED;
      OOS_PARTIAL -> REQUIRES_MORE_OOS; a regime-scoped (conditional)
      claim is NEVER promoted into a universal PROMISING /
      ROBUST_RESEARCH_FINDING tier; ROBUST_RESEARCH_FINDING requires
      unconditional + HIGH robustness (LOW/med caps at PROMISING).
  evidence.py       -- build_finding: recommendation -> OOS readback
      (per-period verdicts, survival, sign-consistency, familywise,
      robustness) -> hypothesis readback (id/origin/statement/symbol/
      direction/regime-cell/params) -> optional 9L recovery/entry/
      calibration readback + 9K walk-forward/finding readback ->
      deterministic narrative answers (closed rosters) -> limitations;
      every REJECTED period and every limitation retained (nothing
      hidden); to_recommendation flattens one finding into exactly one
      Recommendation 1:1, preserving the OOS report id at the earliest
      point so recommendation.evidence_ids carries the frozen evidence
      reference (derived from the typed finding.oos.oos_report_id, not
      a parallel field).
  engine.py         -- RecommendationEngine.run(oos_report, ml_report,
      regime_report, hypothesis_ids) -> frozen RecommendationReport;
      reads the FROZEN 9M OosReport (object or dict) + optional frozen
      9L/9K reports; unknown gate keys raise loudly; empty report is
      honest; builds recommendations = tuple(to_recommendation(f) for f
      in findings) and asserts len(recommendations) == len(findings).
  types.py          -- frozen containers: OosReadback /
      HypothesisReadback / AncillaryReadback / ReadbackAnswers /
      RecommendationFinding (locked directive enforced in __post_init__)
      / Recommendation / EvidenceSummary / RecommendationStatistics /
      ReviewOverview; LIMITATIONS closed roster; scalar-safe to_dict;
      deterministic recommendation_id via short_id("N", ...), no uuid/
      random/datetime.
  report.py         -- frozen RecommendationReport + build_report;
      deterministic N+10hex report_id derived from the canonical payload
      EXCLUDING report_id (no self-reference), stable under reordered
      recommendations; production_ready field permanently False
      (construction with True raises ValueError; assignment raises
      FrozenInstanceError); is_production_ready property returns False;
      emission_check() returns a dict {clean, production_ready,
      is_production_ready, has_production_directive, tokens_absent,
      statuses_research_only, immutable, seven_e_blocked_preserved,
      never_emitted, present, reasons} that scans the ACTUAL serialized
      body; NEVER_EMITTED promotion tokens never serialized into the
      report body.
  __init__.py       -- public research-only surface (26 exports).

Recording: none -- a 9N run persists NOTHING, never lands a strategy,
never changes a parameter, and never lands a trade or a ledger row;
results are ephemeral research objects only.
Phase 7E NO-GO and 6C/6D/6E/7/8/8B and 9A-9M frozen layers untouched
(fully additive; no production edits).

Proof: tests/test_researcher_9n.py 77/77 OK (closed vocabulary + locked
directive, ladder unit coverage over the FULL 9M ladder incl. 7E always-
blocked and conditional-never-universal and LOW-robustness blocks the
top rung, evidence-chain retention + deterministic finding ids + frozen
containers + 1:1 to_recommendation preserving the OOS report id in
recommendation.evidence_ids, engine reading a REAL frozen 9M report
(object and dict) + hypothesis filter + empty honest + unknown gate
ValueError + 1:1 and statistics.n_recommendations ==
len(recommendations), production guard: construction with
production_ready=True raises ValueError, assignment raises
FrozenInstanceError, is_production_ready property False, promotion
tokens absent from the serialized body, no production imports/import-
boundary + no random-uuid-datetime-scipy-sklearn, deterministic report
id equal across repeat build + reordered recommendations, canonical e2e
report_id Ne4c9dc7886 + finding N7ff6711cff mapping the 6/6 walk-forward
clean long recovery to ROBUST_RESEARCH_FINDING, wf-false -> PROMISING,
conditional -> CONDITIONAL, 7E -> BLOCKED).

Isolation: no shared mutable state, no registry, no .env, no network;
a 9N report exists only in-process and dies with the process; the
directive is always INVESTIGATE_FURTHER.

FULL SUITE: 1307/1307 OK (1230 baseline + 77 new 9N; zero existing-test
changes). compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E results modified.

============================================================
PHASE 29 -- 9L DISCOVERY PROVENANCE BINDING

`core/research/oos/intake.py` adds fail-closed provenance validation for consumed 9L hypotheses without constructing hypotheses from findings. `HypothesisRecord.evidence` is validated and serialized. Strict `OosValidationEngine.run(..., require_discovery_provenance=True)` requires a matching frozen 9L report binding before execution. Token format: `9L:<report_id>:<surface>:<finding_key>`. Historical no-evidence fixture identities remain stable. Research-only; production readiness remains false.

PHASE 9M -- MULTI-PERIOD OUT-OF-SAMPLE VALIDATION, STATUS 130
(2026-09-02; autonomous, deterministic, research-only multi-period OOS
replay layer over the frozen 9K/9L discoveries: chronological partition
of the trailing 50% into 6 unseen OOS periods -> per-period replay of
the fixed candidate grid against the genuine 9C baseline counterfactual
-> survival / sign-consistency / economic gates -> GLOBAL Sidak
familywise correction -> per-symbol / per-direction / per-regime
sub-evals -> robustness -> limitations; never a trade directive, never
auto-promotion)
============================================================

NEW core/research/oos/ sub-package (9 modules; imports ONLY the
core.research.* research surface -- never core.execution|trading|
ledger|account|portfolio|risk|market_data|setup|pipeline; no AI-SDK /
scipy / random / uuid / datetime; numpy-free; decision/fill-time
windows only -- no lookahead).

  constants.py      -- closed vocabulary: per-period VALIDATED/PROMISING/
      INCONCLUSIVE/REJECTED/UNAVAILABLE and finding ladder BLOCKED ->
      UNAVAILABLE -> INCONCLUSIVE -> REJECTED -> OOS_PARTIAL ->
      OOS_PROMISING -> OOS_ROBUST -> VALIDATED_RESEARCH_ONLY (the top
      rung requires explicit walk-forward declaration); locked defaults
      OOS_PERIODS 6 / DISCOVERY_FRACTION 0.5 / MIN_OOS_TRADES-
      PER_PERIOD 10 / MIN_OOS_OPPORTUNITIES_PER_PERIOD 30 /
      MIN_TOTAL_OOS_TRADES 60 / MIN_SURVIVING_PERIODS 5 /
      REQUIRED_SIGN_CONSISTENT_PERIODS 5 / PURGE_BARS 0 / EMBARGO_BARS 0
      / SPLIT_PROTOCOL_FROZEN; SEVEN_E_NO_GO; CANDIDATE_ALTERNATIVES =
      the 3 frozen 9L entry models (LIMIT_RETEST / MARKET_CONFIRMATION /
      BREAKOUT_CONTINUATION).
  period.py         -- partition: (display_fraction, discovery_fraction,
      oos_fraction, oos_periods) = (864/432/432/6 boundaries 72) over the
      chronological frozen window; outcome_leakage NOT_REQUIRED /
      PROTECTED / UNAVAILABLE (PROTECTED when discovery horizon +
      outcome bars reach into the OOS era -- the honest leak flag).
  oos_types.py      -- frozen containers: HypothesisOosResult /
      OosSummary / OosPeriodEvidence; economic_statistics + survival_
      ratio math; scalar-safe to_dict across regime/symbols/directions.
  validator.py      -- evaluate_pool -> evaluate_period: replay every
      CANDIDATE_ALTERNATIVES via 9C against the genuine BREAKOUT_
      CONTINUATION baseline counterfactual, n_candidate_filled counts
      FILLS (not fill-rate), win rate / expectancy / R-MAE / loss-rate
      deltas vs baseline, economic_acceptable, sign_consistent.
  aggregator.py     -- summarize_periods + final_status ladder (reject>1
      REJECTED, insufficient availability with positive majority
      OOS_PARTIAL, 5 settled incl. unavail OOS_PROMISING, no settled
      evidence INCONCLUSIVE/UNAVAILABLE, recovery-status surgery applied
      on every summary); multiple_testing Sidak familywise corrected_
      alpha; per_period_summary.
  robustness.py     -- classify LOW/MEDIUM/HIGH with passes/reasons; n_
      settled trades across periods; per-symbol / per-direction (LONG ->
      BULLISH, SHORT -> BEARISH) / per-regime evidence separated -- NEVER
      merged; robustness LOW blocks the top rung.
  engine.py         -- OosValidationEngine.run(opportunities, candles,
      config, hypotheses) -> frozen OosReport; totals-gate via guards.
      required_min_n over the TOTAL family (never per-finding), leak
      guard PROTECTED, BLOCKED when seven_e, unknown gate keys raise
      loudly; survival ratio + sign-consistent periods in the aggregate.
  report.py         -- frozen OosReport + build_report; deterministic
      M+10hex report_id; is_production_ready ALWAYS False and enforced
      via ValueError; emission_check returns (False, reason); NEVER_
      EMITTED promotion tokens never serialized into the report body.
  __init__.py       -- public research-only surface (29 exports).

Recording: none -- a 9M run persists NOTHING and never lands a trade
or a ledger row; results are ephemeral research objects only.
Phase 7E NO-GO and 6C/6D/6E/7/8/8B frozen layers untouched (fully
additive; no production edits).

Proof: tests/test_researcher_9m.py 37/37 OK (protocol surface closed
vocabulary + ladder exact, Sidak familywise exact math incl. family-2
corrected_alpha 0.025320565519103666, partition math 864/432/432/6 +
boundaries 72, aggregator ladder REJECTED/OOS_PARTIAL/OOS_PROMISING/
INCONCLUSIVE/OOS_ROBUST via final_status units, recovery unit 40 R ->
n_recovered 40 capture_gain 1.0 INCONCLUSIVE, canonical e2e report_id
Me686dca76c wf-true / M8be132b4e4 wf-false: 6/6 VALIDATED + HIGH
robustness + familywise true + leak PROTECTED + survival_ratio 1.0,
7E BLOCKED, SHORT UNAVAILABLE, bounds INCONCLUSIVE via min_oos-trades
override 500, byte-identical determinism rerun + no-lookahead future-bar
mutability rerun + no random-uuid-datetime-scipy-sklearn-snapshot +
no production imports/import-boundary + promotion tokens absent from
report body).

Isolation: no shared mutable state, no registry, no .env, no network;
a 9M report exists only in-process and dies with the process.

FULL SUITE: 1230/1230 OK (1193 baseline + 37 new 9M; zero existing-test
changes). compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E results modified.

============================================================
PHASE 9L -- ADVANCED ML + REGIME / OPPORTUNITY DISCOVERY, STATUS 129
(2026-09-02; autonomous, deterministic, research-only conditional-ML
evidence layer fusing the frozen 9G stats/ML machinery with the frozen
9K regime framework: context build -> fixed bounded alternative grid ->
temporal TRAIN|VALIDATION|OOS -> recovery probability -> conditional
entry-model selection -> regime feature interactions -> transition
detection -> symbol segmentation -> OOS confidence/calibration ->
GLOBAL Sidak/Holm multiple-testing -> robustness -> economic
significance -> minimum sample -> limitations; deliberately NOT an
auto-ML optimizer -- exactly 3 fixed alternatives, never 100k combos;
never a trade directive, never auto-promotion)
============================================================

NEW core/research/conditional_ml/ sub-package (13 modules; imports ONLY
the core.research.* research surface -- never core.execution|trading|
ledger|account|portfolio|risk|market_data|setup|pipeline; no AI-SDK /
scipy / random / uuid / datetime; numpy-free pure-math probability
layer; decision-time windows only -- no lookahead).

  types.py         -- CANDIDATE_ALTERNATIVES = EXACTLY the 3 supported
      entry models (LIMIT_RETEST / MARKET_CONFIRMATION /
      BREAKOUT_CONTINUATION) -- a fixed research grid; frozen evidence
      containers: OpportunityContext (regime at decision + fill, 9F
      decision-time features, baseline entry state), RecoveryFinding
      (alternative/regime/n/recovered/p_recovery/expected_r/
      expected_drawdown/loss_probability/adverse p50-p90/regime
      dependency h/min_n_gate/status/finding_id), AlternativeEvidence,
      EntrySelection, InteractionFinding (regime/features/n_train/
      n_oos/effect_d_train+oos/expectancies/pooled/p_value/status),
      TransitionFinding, SymbolBehaviour, CalibrationBin,
      CalibrationSummary; INTERACTION_FEATURES (fixed bounded roster),
      MAX_INTERACTION_TESTS=100, EFFECT_D_MIN, ECE_MAX_CALIBRATED.
  guards.py        -- anti-overfitting gates: required_min_n grows with
      total hypotheses (log2), familywise_alpha Sidak over the TOTAL
      enumerated family, holm_survives (Holm-Bonferroni step-down),
      z_prop_win / z_mean_diff two-sided TAIL p-values via pure
      math.erf (never inverted -- strong evidence -> small p).
  probabilities.py -- fixed-form additive-logit OutcomeModel
      (Laplace-smoothed token logit / expected-R shifts, clipped and
      clamped); trained ONCE on TRAIN, evaluated on VALIDATION/OOS; no
      hyper-parameter search.
  contexts.py      -- opportunity -> OpportunityContext at decision
      time (detect_regime at decision AND counterfactual fill bar,
      decision_bar rule, 9F feature snapshot, entry state).
  recovery.py      -- recovery probability for MISSED/REJECTED
      baselines: each fixed alternative replayed by 9C; recovery =
      alternative filled AND settled WIN (non-fill counts as failed
      recovery -- no fabrication); RECOVERY_SUPPORTED only when the
      raised min-n gate AND positive expected R.
  entries.py       -- conditional ENTRY-MODEL selection per (regime,
      direction) cell: every fixed alternative with its own trained
      model, OOS sample >= raised gate, OOS expectancy >= baseline +
      economic margin, survives the GLOBAL familywise correction;
      otherwise ENTRY_SELECTION_INCONCLUSIVE with every alternative
      row RETAINED.
  interactions.py  -- regime-conditional feature interactions over the
      bounded roster (size-2/3 ONLY, same-feature combos structurally
      excluded, HARD cap 100 reported when reached); SUPPORTED only
      when the effect carries TRAIN->OOS with the same sign,
      |Cohen's d| >= EFFECT_D_MIN and the min-n gate passes.
  transitions.py   -- generated-regime -> filled-regime table for
      every factually filled baseline; stable (generated==filled)
      buckets are always STABLE; CHANGED only for a material
      expectancy delta vs the stable reference (never hidden).
  symbols.py       -- symbol x primary-regime cells with justified
      flag (n >= raised gate AND expectancy >= global + margin); every
      cell retained.
  calibration.py   -- confidence/calibration per probability surface
      over OOS ONLY: equal-width bins all retained (a gap is a
      finding), ECE, Brier, calibration slope; CALIBRATED only when
      OOS >= gate and ECE within the closed bound.
  engine.py        -- ConditionalMlEngine.run(opportunities, candles,
      config) -> frozen ConditionalMlReport: builds contexts, replays
      the fixed 3-alternative grid via 9C CounterfactualRunner
      (baseline measured as BREAKOUT_CONTINUATION), chronological
      temporal_split, enumeration of the TOTAL hypothesis family, runs
      every surface, then the GLOBAL multiple-testing guard (Sidak
      across the whole family + Holm within interactions) and injects
      frozen-safe survival/justified flags via dataclasses.replace;
      robustness (pipeline order, chronological split, fixed grid,
      combinatorial cap) + limitations list of every surface.
  report.py        -- frozen ConditionalMlReport (deterministic L+10hex
      report_id, is_production_ready ALWAYS False enforced via
      ValueError in __post_init__, emission_check proves NEVER_EMITTED
      promotion tokens absent from the body).

Recording: none -- a 9L run persists NOTHING and never lands a
strategy; results are in-memory research evidence keyed by report_id.

Boundaries (proven by tests): no production-internal import at any
line and every third-party import is pure stdlib; no AI-SDK / scipy /
random / uuid / datetime; no lookahead (two divergent futures yield
byte-identical reports when they differ only AFTER every decision/fill
bar -- decision-time only); no auto-promotion (never-emitted tokens
absent from the report body); no feature fabrication (order-flow /
footprint stay UNAVAILABLE on OHLCV-only fixtures); no unbounded idea
search (fixed grid + cap 100); 9A-9K frozen layers consumed read-only
and 9J/9K (STATUS 127/128) untouched; Strategy / production / risk /
execution / portfolio / live-or-paper / 6C-6E / 7 / 8 / 8B untouched.

FULL SUITE: 1193/1193 OK (1154 + 39 new 9L tests; zero existing-test
changes). compileall clean; pure-math environment; tracked .pyc
restored before commit. No BREAKOUT/rules/7E/production results
modified.

============================================================
PHASE 9K -- REGIME / CONDITIONAL OPPORTUNITY DISCOVERY, STATUS 128
(2026-09-02; autonomous, deterministic, research-only "under-which-
market-conditions" engine over the frozen 9A-9J layers: regime
segmentation -> conditional cells -> walk-forward validation ->
multiple-testing guard -> feature splits -> report; never a trade
directive, never auto-promotion)
============================================================

NEW core/research/regime/ sub-package (10 modules; imports ONLY the
core.research.* research surface -- never core.execution|trading|
ledger|account|portfolio|risk|market_data|setup|pipeline; no AI-SDK /
random / uuid / datetime; decision-time windows END at the decision
bar -- no lookahead):

  regime_types.py  -- closed vocabulary labels per dimension (TREND/
      RANGE, BULLISH/BEARISH/NEUTRAL, HIGH/NORMAL/LOW, EXPANSION/
      NEUTRAL/CONTRACTION, STRONG/NORMAL/ABSENT, SWEEPED/NORMAL,
      PRESENT/ABSENT, Wyckoff phases) + frozen evidence containers:
      MarketRegime (available() data-gated, UNAVAILABLE=None never
      fabricated), RegimeObservation (result/r/direction/symbol/
      regime), ConditionalCell (expectancy + wins/win_rate/
      delta_expectancy + recovered vs baseline), ConditionalFinding
      (is_production_directive raises ValueError; deterministic K+10hex
      finding_id), FeatureSplit (win_rate/avg_r/effect_h vs overall),
      WalkForwardWindow / WalkForwardSummary; REGIME_DIMENSIONS +
      PRIMARY_REGIME_DIMENSIONS; deterministic short_id/stable_json.
  indicators.py    -- pure decision-time regime indicators reusing the
      frozen core.research.features.indicators (atr/sma/rolling_
      volatility): trend_vs_range (normalised SMA slope + span/ATR),
      direction_structure (pivot HH+HL vs LH+LL), volatility_regime
      (recent-vs-older vol ratio thresholds 1.3/0.7), atr_regime
      (ratio thresholds 1.2/0.8), displacement_strength (real-body
      impulse), liquidity (stop-side sweep + reclaim), fvg (shadow
      gap), order_block (consolidation break), wyckoff_phase
      (simplified markup/distribution/etc). Every indicator is
      data-gated: too-short/no-evidence windows return UNAVAILABLE.
  detector.py      -- detect_regime(candles, decision_bar, lookback,
      atr_period, stop_level, direction) -> MarketRegime over the
      bounded window ENDING AT the decision bar; regime_dimensions /
      primary_regime_dimensions / dimension_vocabulary / validate_
      dimension (closed, loud).
  segmenter.py     -- 9A OpportunityRecords -> RegimeObservation via
      the frozen 9C classify_opportunity + decision-time regime;
      decision_bar (filled_bar first, setup bar fallback, None when
      absent -> empty honest regime), stop_level/direction/observed_
      result/observed_r, in_cell / cell_labels / regime_coverage /
      by_category.
  conditional.py   -- per candidate over strict 9B vocabulary
      (_validate_candidate via the frozen validate_overrides -- an
      unknown axis or unsupported entry model FAILS LOUDLY),
      build_config = frozen base + scalar overrides (same 9C identity
      scheme), conditional_discovery: candidate vs frozen baseline
      INSIDE every (dimension x label) cell (expectancy, recoveries,
      delta_expectancy, split breadth) + global edge + finding
      statuses CONDITIONAL / CONDITIONAL_WEAK / INCONCLUSIVE /
      NOT_SUPPORTED; EVERY cell and finding retained (no hiding of
      negative results); feature_splits: OBSERVED-ONLY 9F values
      joined by observation_id, win-rate/avg-R/effect size, min-sample
      gated, nothing synthesized.
  walkforward.py   -- temporal_windows: chronological expanding-train
      / trailing-test folds (no shuffle, no leakage); validate_
      conditional: a material finding survives when a majority (2/3)
      of ADEQUATE windows (within-cell validation_n >= min_validation_
      n) show positive candidate expectancy AND positive delta vs the
      frozen baseline; thin windows counted with honest notes.
  multiple_testing.py -- anti-overfitting guard: hypotheses = distinct
      (config_id x dimension) tested; corrected_alpha = Sidak family-
      wise control; required_min_n = min_cell_n + ceil(log2(1 + H));
      every finding retained and flagged "possible lucky combination /
      insufficient after correction" when it fails the raised sample
      requirement -- never hidden.
  engine.py        -- OpportunityDiscoveryEngine.run(records,
      base_config, candidates, symbol, dataset, dimensions) ->
      RegimeReport; pipeline segment -> conditional -> walk-forward
      (material findings only) -> feature splits -> multiple-testing
      -> robustness (per-finding coverage across directions/symbols)
      -> limitations; availability()/emission_check; next_research =
      9M multi-period OOS, 9L advanced ML + regime, 9N recommendation
      layer.
  report.py        -- frozen RegimeReport (deterministic K+10hex
      report_id, is_production_ready ALWAYS False and enforced via
      ValueError in __post_init__, emission_check proves NEVER_EMITTED
      promotion tokens absent from the serialized report).

Recording: none -- a 9K run persists NOTHING and never lands a
strategy; results are in-memory research evidence keyed by report_id.

Boundaries (proven by tests): no production-internal import at any
line; no order/ledger/placement tokens; no random/uuid/datetime; no
lookahead (two divergent futures indistinguishable up to the decision
bar yield byte-identical regimes); no auto-promotion (never-emitted
tokens absent from every report blob; ConditionalFinding cannot carry
is_production_directive); no footprint/volume fabrication (stays
UNAVAILABLE); 9A-9I frozen layers consumed read-only and 9J (STATUS
127) untouched; Strategy / production / risk / execution / portfolio /
live-or-paper / 6C-6E / 7 / 8 / 8B untouched.

FULL SUITE: 1154/1154 OK (1063 + 91 new 9K tests; zero existing-test
changes). compileall clean; numpy-only environment; tracked .pyc
restored before commit. No BREAKOUT/rules/7E/production results
modified.

============================================================
PHASE 9J -- STRATEGY DISCOVERY / EXPERIMENT ENGINE, STATUS 127
(2026-09-02; autonomous, deterministic, research-only discovery over the
frozen 9A-9I layers: gaps -> hypotheses -> scheduled experiments -> closed
gate ladder -> observed confluence -> report; never auto-promotion)
============================================================

NEW core/research/discovery/ sub-package (7 modules; imports ONLY the
core.research.* research surface -- never core.execution|risk|portfolio|
engine|trade|account|strategy; no AI-SDK / random / uuid / datetime):

  discovery_types.py -- frozen DiscoveryHypothesis (kind/question/
      statement/why/expected_outcome/overrides/direction/symbol/evidence/
      seven_e_no_go/injected + deterministic sha1 hypothesis id H+10hex),
      DiscoveryFinding / DiscoveryExperiment (status, gate_reasons,
      per-experiment recovery, params as the full CounterfactualConfig
      to_dict()), StrategyDiscoveryReport (frozen), closed experiment
      status vocabulary REJECTED/INCONCLUSIVE/PROMISING/REQUIRES_OOS/
      VALIDATED/BLOCKED, NEVER_EMITTED = AUTOMATICALLY_DEPLOY +
      PRODUCTION_READY + PRODUCTION_DIRECTIVE, stable_json.
  candidate_space.py -- validate_overrides: accepts ONLY the supported
      9B ExperimentConfig axes (entry_offset_atr/entry_model/expiry/
      confirmation_mode/stop_mode/risk_reward); an unsupported parameter
      axis or a known-but-unsupported entry model FAILS LOUDLY (raises
      with the supported vocabulary in the message -- never silently
      invented); expiry must be a positive int; vocabulary() returns the
      closed supported set with never_invented_axes=True.
  gaps.py        -- detect_gaps: deterministic gap audit grouped by
      dataset source + category (FILLED / ENTRY_NOT_REACHED / EMPTY /
      REJECTED...) with bars, counts, settled and directions;
      generate_hypotheses: recovery-first, evidence-gated candidates
      RECOVERY_RR / RECOVERY_STOP / RECOVERY_ENTRY_OFFSET /
      RECOVERY_ENTRY_MODEL / RECOVERY_EXPIRY / RECOVERY_CONFIRMATION
      that are always executable (real overrides) and carry their
      evidence; deterministic sha1 ids.
  scheduler.py   -- deterministic ordering; explicit budget that counts
      only GENERATED experiments -- INJECTED experiments are NEVER
      suppressed; research-memory dedup reported as skipped ("previously
      studied in research memory"); invalid candidates (e.g. rr 0)
      skipped loudly and never executed.
  discovery_runner.py -- StrategyDiscoveryEngine.run(records, base,
      symbol, extra_hypotheses, dataset, memory): for each scheduled
      hypothesis drives the FROZEN 9C CounterfactualRunner -> 9D
      ResearchAnalyzer -> 9E ResearchIntelligence -> 9F Statistical
      Baseline + chronological OOS fold -> DiscoveryGates; counts
      recovered opportunities (recovery_count + per_category + added_R);
      experiments run entirely in-memory -- persist NOTHING and never
      land a strategy; emitted report has deterministic report_id,
      emission_check and ALWAYS-False is_production_ready /
      is_production_directive (frozen dataclass, never settable).
  robustness_filter.py -- the closed Discovery gate ladder: 1 BLOCKED
      (7E NO-GO) -> 2 INCONCLUSIVE (settled<10) -> 3 REJECTED (no
      advantage) -> 4 REJECTED (loss-expansion) -> 5 REJECTED (directional
      contradiction, min 5) -> 6 PROMISING (economic not acceptable) ->
      7 REQUIRES_OOS -> 8 REJECTED (OOS evidence did not confirm) ->
      9 PROMISING (settled<30) -> 10 VALIDATED (research-only, never
      production-ready). OOS can never be bypassed.
  baseline_comparator.py -- economic_assessment in-sample vs OOS:
      capture_gain / expectancy_delta / loss_rate_delta / max_drawdown_
      delta / loss_expansion; acceptable = not loss_expansion AND
      capture_gain>=0 AND expectancy_delta>=0 AND loss_rate_delta<=0 AND
      max_drawdown_delta<=0; avg-MAE risk_delta is REPORT-ONLY
      (recovery-first earlier entries inherently raise avg MAE so it must
      not block VALIDATED); verdict token CAPTURE_TRADE_OFF: ... or
      RECOVERY_CAPTURES_VALUE_WITHOUT_WORSE_ECONOMICS.
  confluence_discovery.py -- OBSERVED-ONLY 9F feature associations vs
      recovered REJECTED observations (feature_availability + per-feature
      association with recovered count, status
      OBSERVED_ASSOCIATIONS_ONLY, notes state nothing fabricated).

Recording: a report writes one 9J_DISCOVERY_COMPLETE memory row per
non-injected experiment; INJECTED experiments are never recorded or
suppressed; a second run skips generated hypotheses with "previously
studied in research memory" and still executes injected ones. Ranking:
EVERY experiment retained (rejected/blocked/inconclusive included),
deterministic id-keyed sort, non-increasing scores, complete no-hiding.

Boundaries (proven by tests): no production-internal import at any line;
no order/ledger/placement tokens; no random/uuid/datetime; no lookahead;
no auto-promotion (NEVER_EMITTED tokens absent from every report blob);
experiments persist nothing; 7E NO-GO preserved (BLOCKED); 9A-9I frozen
layers consumed read-only; Strategy / production / risk / execution /
portfolio / live-or-paper / 6C-6E / 7 / 8 / 8B untouched.

FULL SUITE: 1063/1063 OK (1012 + 51 new 9J tests; zero existing-test
changes). compileall clean; numpy-only environment; tracked .pyc restored
before commit. No BREAKOUT/rules/7E/production results modified.

============================================================
PHASE 9I -- UNIFIED RESEARCH DATASET / KNOWLEDGE LAYER, STATUS 126
(2026-09-01; research-only knowledge/data layer that unifies every frozen
9A-9H surface into one queryable research dataset; pure data + queries,
never a trade directive, never auto-promotion)
============================================================

NEW core/research/dataset/ sub-package (4 modules; imports ONLY the
core.research.* research surface -- never core.execution|risk|portfolio|
engine|trade|account|strategy; no AI-SDK / random / uuid / datetime):

  row.py       -- ResearchRow (frozen): stable deterministic sha1 row_id
      (I+10hex, never UUID/timestamp), DatasetSource closed vocabulary
      JOURNAL / COUNTERFACTUAL / ANALYSIS / INTELLIGENCE / FEATURE / ML /
      RESEARCH, observation_id join key back to the opportunity/experiment/
      recommendation id, identity fields for grouping (instrument /
      direction / timeframe / strategy / category / result), two evidence
      bags (kv: descriptive parameters / features; measured: quantitative
      outcomes), to_dict / row_from_dict round-trip; SOURCES constant.
  collectors.py-- read-only builders that normalize each 9A-9H artifact
      into ResearchRow lists: collect_journal (9A OpportunityRecords:
      category via the frozen classify_opportunity, observed trade
      outcome + setup economics), collect_counterfactual (9B/9C
      CounterfactualOutcomes: experiment-level params + replayed result),
      collect_analysis (9D ResearchReport: per-experiment metrics +
      comparison deltas + a baseline row), collect_intelligence (9E
      IntelligenceReport: per-recommendation evidence strength / status /
      changed params / recovery deltas), collect_features (9F
      FeatureSnapshots: every decision-time feature value as a flat kv),
      collect_ml (9G MlResearchReport: per-target AUC validation/OOS +
      interaction rows), collect_researcher (9H InvestigationReport:
      investigation / hypothesis / recommendation rows). Inputs never
      mutated.
  dataset.py  -- ResearchDataset append-only container: dedup by row_id,
      deterministic JSON persistence (atomic tmp+os.replace), corrupt file
      -> fresh empty dataset, filtered source access, row_count / empty /
      observation_ids.
  queries.py   -- the knowledge/queries layer: entry_pipeline_breakdown
      (structurally_valid_setups / entered / not_entered / entry_rate /
      settled / win_rate / by_category / rejected_by_reason -> answers
      "1,000 valid, why only 200 entered"), recovery_candidates (join
      JOURNAL observations against COUNTERFACTUAL rows to find which
      missed/rejected opportunities could have been profitable under an
      alternative 9B/9C config -- recovered R/PnL/MAE/MFE, the recovering
      alternative_config, captured-vs-missed economics, all with
      research_only disclaimer; never promotes a config), unify_by_
      observation (cross-source join for one observation_id, so the full
      evidence chain of a setup is inspectable), aggregate (generic
      group-by / count / sum / mean / win_rate, insertion-order
      deterministic), answer_context (compact 9I evidence dict for the 9H
      researcher).

This layer is the dataset/evidence foundation for 9J+ autonomous strategy
experimentation. It answers the original goal: it measures WHY structurally
valid setups were missed and WHICH alternative entries/offsets/expiry/RR/
confirmation could capture them profitably -- without optimizing for
maximum profit and without destroying robustness/risk constraints; every
number cites the frozen 9C-9G evidence.

Boundaries (proven by tests): no production-internal import at any line;
no order/ledger/placement tokens; no auto-promotion; no random/uuid/
datetime; read-only inputs; deterministic ids. All layer 9A-9H surfaces
consumed read-only; nothing in Strategy / production / risk / execution /
portfolio / live-or-paper / 6C-6E / 7 / 8 / 8B touched.

FULL SUITE: 1012/1012 OK (993 + 19 new 9I tests; zero existing-test
changes). compileall clean; numpy-only environment; tracked .pyc restored
before commit. No BREAKOUT/rules/7E/production results modified.

============================================================
PHASE 9H -- AUTONOMOUS AI RESEARCHER CORE, STATUS 125
(2026-09-01; provider-neutral, research-only autonomous researcher that
observes the 9A-9G evidence, forms hypotheses ONLY from the supported 9B/9C
vocabulary, runs experiments through the frozen 9C-9G machinery, keeps a
persistent Research Memory, and returns ranked, evidence-cited conclusions.
It NEVER places orders, never mutates records, never looks ahead, and never
auto-promotes. External AI providers are OPTIONAL -- the deterministic
NullProvider gives full behaviour with zero AI.)
============================================================

NEW core/research/researcher/ sub-package (8 modules; imports ONLY the
core.research.* research surface -- never core.execution|risk|portfolio|
engine|trade|account|strategy; no top-level AI-SDK imports):

  types.py -- EvidenceContext / Hypothesis / ExperimentResult /
      ResearchRecommendation / InvestigationReport + closed experiment
      vocabulary + STANDING_LIMITATION + deterministic sha1 ids.
  providers.py -- AIProvider ABC; always-available deterministic
      NullProvider with evidence-gated rule drafts (never conjectures;
      vacuous evidence -> no drafts). Guarded OpenAI / Anthropic /
      OpenRouter / Ollama stubs found lazily via importlib.util.find_spec
      at call-time; absent SDK -> PROVIDER_UNAVAILABLE (engine still runs).
  memory.py -- ResearchMemory: sha1 question-fingerprint, record / recall /
      dedup / next_suggestion, optional atomic JSON persistence; corrupt
      file degrades to fresh memory.
  planner.py -- ResearchPlanner: validates propositions against the closed
      9B/9C vocabulary; unsupported params / entry models / expiry fail
      loudly (ValueError) rather than silently diverge; deterministic
      hypothesis ids H+10hex; memory dedup with notes; deterministic sort.
  experiments.py -- ExperimentExecutor / ExperimentRun: drives the FROZEN
      9C CounterfactualRunner.candles.grid(records, base_config, **overrides)
      -> 9D ResearchAnalyzer.analyze -> 9E ResearchIntelligence.analyze,
      plus the 9F StatisticalBaseline, 9F temporal_split chronological OOS
      fold, and the guarded 9F FeatureAnalyzer. Per-bundle ExperimentResult
      with exhaustive metrics / comparison / robustness / opportunity
      categories / statistical / oos / features.
  evaluate.py -- EvidenceEvaluator ladder VALIDATED(3.0) / HYPOTHESIS(2.5) /
      OBSERVATION(1.0) / INSUFFICIENT_EVIDENCE(0.5) / REJECTED(0.0) with
      MIN_VALIDATION_SETTLED=30 and MIN_OOS_SETTLED=5; a 9E robustness gate
      that can never be bypassed (OOS-negative or OOS-too-small or
      robustness-flagged downgrades VALIDATED); conclusions always cite
      evidence or return INSUFFICIENT_EVIDENCE -- never guessed. sha1
      recommendation ids R+10hex; failed experiments retained.
  researcher.py -- build_context + AutonomousResearcher.investigate returns
      an InvestigationReport with the full evidence chain DATASET ->
      HYPOTHESIS -> EXPERIMENT -> RECOMMENDATION -> LIMITATION;
      OBSERVATION/INSUFFICIENT fallback when no hypothesis survives;
      production_ready=False everywhere; DEFAULT_BASE_CONFIG; records never
      mutated.
  __init__.py -- public surface (AutonomousResearcher, build_context, the
      providers, planner / executor / evaluator / memory, value types).

Boundaries (proven by tests): no production-internal import at any line; no
top-level AI-SDK import; no order/ledger/placement tokens; no lookahead; no
auto-promotion; the 7E NO-GO stays untouched. All layer 9A-9G surfaces are
consumed read-only; nothing in Strategy / production / risk / execution /
portfolio / live-or-paper / 6C-6E / 7 / 8 / 8B touched.

FULL SUITE: 993/993 OK (956 + 37 new 9H tests; zero existing-test changes).
compileall clean; numpy-only environment (sklearn/scipy/AI-SDKs ABSENT -- the
provider-neutrality + guarded-degradation contract is exercised by the suite
itself); tracked .pyc restored before commit. No BREAKOUT/rules/7E/production
results modified.

============================================================
PHASE 9G -- ML / STATISTICAL RESEARCH LAYER, STATUS 124
(2026-09-01; DISCOVERS statistical relationships; does NOT decide what gets
traded; dependency-isolated -- sklearn never required)
============================================================

NEW core/research/ml/ sub-package (6 modules; consumes the 9F decision-time
FeatureSnapshots + 9C/9D outcomes into deterministic, chronologically-split
statistical / simple-ML / feature-interaction / opportunity-recovery research
-- the evidence foundation the later 9H autonomous AI researcher consumes):

  split.py -- deterministic chronological temporal_split (TRAIN |
      VALIDATION | OOS with NO random shuffle and NO temporal leakage) and
      expanding-window walk_forward; folds ordered by decision_bar /
      timestamp / list order; train strictly ends before test.
  statistics.py -- 9G.1 StatisticalBaseline (n / wins / losses /
      unsettled_rate / win_rate / loss_rate / entry_reached_rate / avg_R /
      expectancy / avg_MAE / avg_MFE / deterministic R-distribution bins);
      effect_size_h / effect_size_d; conditional_statistics P(WIN | value),
      P(ENTRY_REACHED | value), P(POSITIVE_R | value) with effect-size-vs-
      overall; honest None on a zero denominator -- never fabricated.
  models.py -- 9G.2 encode_target for the closed targets ENTRY_REACHED /
      WIN / POSITIVE_R / EXPECTED_R / RECOVERY_SUCCESS (available-mask
      excludes unsettled -- never fabricated); NumpyLogisticRegression
      (deterministic fixed-iteration L2 GD) and NumpyDecisionTree
      (deterministic greedy info-gain) -- ALWAYS available, pure numpy;
      SimpleModel 'numpy' or 'sklearn' backend; sklearn (logistic / tree /
      random-forest) probed lazily inside a guarded try/except -> degrades to
      ML_BACKEND_UNAVAILABLE when sklearn is NOT installed; pure-numpy
      rank-sum AUC (ties get mean rank; None on single-class target).
  interaction.py -- 9G.3 interaction_analysis ASSOCIATION tables ONLY over
      feature-value combos actually observed (Wyckoff + FVG + OB + Fibonacci
      + volatility + liquidity_sweep -> ENTRY_REACHED% / WIN% / avg R /
      avg MAE / avg MFE / n / sufficient_sample); absent/partial combos not
      reported; tiny samples honestly flagged, rates None not fabricated.
  analyzer.py -- MlAnalyzer -> immutable MlResearchReport: chronological
      split + walk-forward + 9G.1 baseline/conditional + 9G.2 ML fit on
      TRAIN scored on VALIDATION/OOS AUC + 9G.3 interaction + FIRST-CLASS
      opportunity-recovery research (rejected / ENTRY_NOT_REACHED /
      MISSED_CONTINUATION -> feature snapshot -> recovery_rate + expected
      R/MAE/MFE + proposed alternative entry/RR/expiry/model); to_dict()
      carries association_not_causation + no_trade_directive + backend;
      render() deterministic with the association-only reminder.
  __init__.py -- 9G public surface.

DEPENDENCY ISOLATION (contract): the production/paper engine and the whole
product install, compile, test and run with sklearn/scipy ABSENT (confirmed
in this environment: sklearn and scipy are NOT installed). Every statistical
baseline is pure math/numpy; the simple-ML backends are pure-numpy and
deterministic; sklearn is an OPTIONAL guarded backend that degrades to
ML_BACKEND_UNAVAILABLE -- the research stack is never a production dependency
and no production module imports core.research.ml.

ISOLATION / BOUNDARIES: research-only, deterministic, immutable inputs; NO
temporal leakage (chronological splitting, no shuffle, features only from
candles < decision_bar per 9F); NO simulation (9C owns it); NO production
internals imported (execution/risk/portfolio/engine/trade/account/strategy);
NO deep-AI (torch/tensorflow/keras/xgboost/lgbm/mlx etc.); NO auto-promotion;
no trade directive ever emitted (association_not_causation). The 7E NO-GO
stays untouched. Strategy / production / risk / execution / portfolio /
live-or-paper / 6C-6E / 7 / 8 / 8B / 9A-9F frozen layers untouched (fully
additive; no production edits).

FULL SUITE: 956/956 OK (911 + 45 new 9G; zero existing-test changes).
compileall clean; numpy-only environment; tracked .pyc restored before
commit. No BREAKOUT/rules/7E/production results modified.

============================================================
PHASE 9F -- CONFLUENCE / FEATURE EVIDENCE, STATUS 123
(2026-09-01; deterministic, research-only evidence layer for the later
9G ML / AI research)
============================================================

NEW core/research/features/ sub-package (7 modules; records a decision-time,
NO-LOOKAHEAD feature snapshot per opportunity and joins it to the frozen 9C
CounterfactualOutcomes / 9D metrics into read-only correlation tables;
consumes the frozen 9E ConfluenceFeature / ConfluenceAnalysis surface):

  causal_window.py -- deterministic, immutable CausalWindow / CandlePoint +
      extract_causal_window(candles, decision_bar, lookback): a bounded
      history of bars STRICTLY index < decision_bar (the decision bar itself
      is never a feature source); missing volume tolerated as None and NEVER
      fabricated; invalid/non-price OHLC rows dropped; never mutates inputs.
  indicators.py -- pure, data-gated deterministic indicators: ATR / SMA /
      EMA / rolling_volatility / bollinger_position / OBV. Each returns
      UNAVAILABLE (None) when the bounded series is too short or misaligned;
      OBV returns the accumulated total only over an aligned equal-length
      close/volume series (an earlier placeholder was removed).
  confluence_features.py -- 13 deterministic producers: wyckoff_phase,
      market_structure, atr_regime, bollinger_position, sma_slope,
      obv_trend, liquidity_sweep (direction-correct stop-side sweep +
      reclaim), fvg_present (directional fair-value gap),
      displacement_strength, order_block, fibonacci_zone (the 0.382/0.5/
      0.618 swing band the ENTRY sits in), and volume_profile / footprint_flow
      which return UNAVAILABLE because NO order-flow / volume-profile data
      stream exists (they are NEVER synthesized). All producers are optional
      and data-gated: too-short / absent data -> UNAVAILABLE, never fabricated.
  feature_snapshot.py -- immutable FeatureSnapshot preserving the
      opportunity's OWN decision-time entry / stop / target / atr + direction
      / instrument / timeframe / decision_bar / WindowSize + the deterministic
      feature map + available_feature_count().
  dependency_analysis.py -- build_dependency -> DependencyAnalysis of
      per-feature, per-VALUE buckets: entry_reached_rate, rejected->recovered
      rate (via supplied recoveries / outcome recovered), missed-continuation
      count (via category), WIN/LOSS win_rate, avg_R, avg_MAE, avg_MFE, and
      direction / symbol segmentation. Buckets with ZERO outcome evidence
      report n but NEVER fabricate win_rate / R / rates (None). Deterministic
      value + table ordering. CORRELATION OF EVIDENCE only (never causation,
      never ML).
  feature_analyzer.py -- FeatureAnalyzer orchestrator: snapshot(record,
      candles) + analyze(...) -> immutable FeatureEvidenceReport carrying the
      snapshots, a ConfluenceAnalysis fed into the FROZEN 9E
      name/value/sample/outcomes/experiment_id rows, and the
      DependencyAnalysis; when NO feature can be derived the analysis reports
      CONFLUENCE_DATA_UNAVAILABLE (never claims confluence that does not
      exist); render() deterministic.
  __init__.py -- 9F public surface (CausalWindow / CandlePoint /
      extract_causal_window / FeatureSnapshot / ALL_PRODUCERS /
      DependencyAnalysis / FeatureDependency / build_dependency /
      FeatureAnalyzer / FeatureEvidenceReport / indicators).

ISOLATION / BOUNDARIES: research-only, deterministic, immutable inputs; NO
lookahead (bars strictly before the decision bar); NO simulation (9C owns it);
NO production imports (execution/risk/portfolio/engine/trade/account/strategy
are never imported); NO AI / ML / LLM; NO auto-promotion; NEVER fabricates an
unavailable feature value; footprint/volume-profile produce UNAVAILABLE until
order-flow data exists. The 7E NO-GO stays untouched: a snapshot is EVIDENCE,
never a direction/size/action production rule. Strategy / production / risk /
execution / portfolio / live-or-paper / 6C-6E / 7 / 8 / 8B / 9A-9E frozen
layers untouched (fully additive; no production edits).

FULL SUITE: 911/911 OK (866 + 45 new 9F; zero existing-test changes).
compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E/production results modified.

============================================================
PHASE 9E -- RESEARCH INTELLIGENCE / RECOMMENDATION ENGINE, STATUS 122
(2026-09-01; deterministic, research ONLY, NOT production optimization)
============================================================

NEW core/research/intelligence/ sub-package (11 modules; consumes the
frozen 9D ResearchReport / ExperimentAnalysis / RecoveryReport /
comparison / robustness and the 9C CounterfactualConfig / outcomes and
the 9B metrics -- nothing is re-implemented, nothing is resimulated):

  recommendation_types.py -- the closed plain-string vocabulary:
      RECOMMENDATION_STATUSES in {OBSERVATION, HYPOTHESIS, PROMISING,
      INCONCLUSIVE, REJECTED, REQUIRES_OOS, BLOCKED} (research labels,
      NEVER production approval); RECOMMENDATION_CATEGORIES in {ENTRY_
      RECOVERY, ENTRY_NOT_REACHED, MISSED_CONTINUATION, RR_ANALYSIS,
      EXPIRY_ANALYSIS, ENTRY_OFFSET_ANALYSIS, STOP_TARGET_ANALYSIS,
      DIRECTIONAL_ANALYSIS, SYMBOL_ANALYSIS, CONFLUENCE_ANALYSIS,
      GENERAL}; evidence grades INSUFFICIENT_SAMPLE / SMALL_SAMPLE /
      LIMITED / MODERATE / STRONG; the 9D robustness terms ROBUST /
      NON_ROBUST / OOS_REQUIRED / LOSS_EXPANSION / DIRECTIONAL_IMBALANCE /
      NO_CLEAR_ADVANTAGE; RECOVERABLE_BASELINE_CATEGORIES.
  recommendation.py -- immutable Recommendation with a deterministic
      recommendation_id = sha1(category + sorted candidate ids +
      parameters_changed fingerprint) -- same evidence reproduces the
      same id, NO random UUIDs. Carries baseline/candidate metrics,
      recovery facts, deltas, robustness_status, sample_size, warnings,
      recommendation_status.
  evidence.py -- EvidencePackage per candidate: exact experiment_id +
      config provenance + baseline/candidate metrics + like-for-like
      comparison + recovery + robustness + sample_size with a
      deterministic NON-statistical evidence_strength grade by settled
      count (never "significant").
  opportunity_recovery.py -- OpportunityRecoveryInsight: per-category
      recovery from the 9D recovery-transitions (REJECTED /
      ENTRY_NOT_REACHED / MISSED_CONTINUATION -> WIN / LOSS / STILL_*),
      count-weighted, distinguishing a recovered WIN (success) from a
      recovered LOSS (costs R, never a success); recovery_rate and
      successful_recovery_rate.
  parameter_insights.py -- per-parameter comparison of experiments that
      vary along ONE config parameter (rr / expiry / entry_offset /
      entry_offset_atr / entry_model / stop_mode / target_mode /
      outcome_bars) reported as MOVES not "best"; deterministic
      numeric-then-string value ordering; only params with >1 distinct
      value are reported.
  directional_analysis.py -- per-direction (BULLISH/BEARISH) and
      per-symbol decomposition of 9D group metrics; directional-imbalance
      flag propagated; symbol_breakdown flags broad-vs-symbol-specific
      advantage and is honest ("no symbol breakdown ...") when no
      outcomes are supplied -- never fabricated.
  confluence_analysis.py -- infrastructure for FUTURE feature/confluence
      evidence (Wyckoff / footprint / Fibonacci / flow / volume /
      liquidity / market-structure / FVG / order-block / displacement /
      smart-money). Works correctly with ZERO confluence data: reports
      CONFLUENCE_DATA_UNAVAILABLE and no fabricated feature rows; passes
      through supplied decision-time features read-only.
  robustness_gate.py -- deterministic robustness STATUS classifier
      folding 9D findings + recovery cost + directional balance:
      INSUFFICIENT_SAMPLE / LOSS_EXPANSION / OOS_REQUIRED / NON_ROBUST /
      ROBUST / INCONCLUSIVE. Never claims significance; never
      blocks/enables production.
  hypothesis.py -- deterministic Hypothesis objects (traceable,
      id-stable, one per recommendation plus directional-imbalance / OOS
      caveats) -- the structured input a future AI interpreter consumes.
  research_intelligence.py -- ResearchIntelligence orchestrator over a
      9D report + optional outcomes_by_experiment + confluence -> an
      immutable IntelligenceReport (recommendations sorted by id,
      EvidencePackage list, confluence, insights recovery/parameter/
      directional/symbol, hypotheses, deterministic LEAD as first of
      PROMISING / REQUIRES_OOS / HYPOTHESIS; to_dict() ships a standing
      NON-PRODUCTION reminder; render() deterministic).

RECOMMENDATION STATUS is a research label, not an approval: BLOCKED when
no usable experiment bundles; OBSERVATION when the candidate matches the
baseline band; HYPOTHESIS for a small-sample / recovery-only advantage;
PROMISING when the candidate beats baseline + material recovery + no
loss-expansion + robust; INCONCLUSIVE when no comparison is available;
REQUIRES_OOS whenever an in-sample advantage still needs OOS validation;
REJECTED when the candidate LOSES to baseline on filled/R/expectancy/
win-rate/PF.

ISOLATION / BOUNDARIES: reads a 9D report (+ read-only 9C outcomes and
supplied confluence) only. NEVER mutates the source report / outcomes /
configs / Journal / TradeRegistry / Account / PortfolioState /
SharedCapital. NO simulation (9C owns it), NO optimization, NO auto-
promotion, NO ranking-as-'best', NO AI / ML / LLM (the layer only
packages evidence for a future interpreter), NO lookahead, confluence is
NEVER fabricated. Confluence / directional / symbol evidence is NEVER a
production rule; Phase 7E NO-GO and 6C/6D/6E/7/8/8B/9A-9D frozen layers
untouched (fully additive; no production edits).

FULL SUITE: 866/866 OK (823 + 43 new 9E; zero existing-test changes).
compileall clean; tracked .pyc restored before commit. No
BREAKOUT/rules/7E/production results modified.

============================================================
_ARCHIVE (QUARANTINE) -- STATUS 84, 2026-08-28
============================================================

The legacy top-level packages engine/ indicators/ signals/
strategy/ smartmoney/ analysis/ analytics/ execution/ and
risk/risk_manager.py are NOT part of the live product. An
import census showed they are referenced only by the legacy
examples/ scripts (also quarantined). They were moved to
_archive/ (off the import path) to satisfy the
NO-duplicate-classes rule without deleting anything.

LIVE import surface: core/ data/ config/ backtesting/
risk/portfolio_risk.py main.py examples/(14 canonical
replay/backtest/paper/live scripts).

============================================================
RULES
============================================================

Before modifying ANY file:

1. Locate the file here.

2. Identify every dependency.

3. Identify every importing module.

4. Update tests.

5. Update Manifest.

============================================================
ADDENDUM — STAGE 1–3 (closure fad7329 baseline)
============================================================

core/risk/costs.py (NEW)

Imports

config (risk_settings, lazily inside functions)

math, dataclasses

Imported By

core/risk/risk_engine.py (from_settings as _production_costs)
tests/test_hardening_stage123.py, tests/test_stage123_operational.py

core/live/reconciler.py (NEW)

Imports

core.common.logging_config

json, math, os, tempfile

Imported By

core/live/broker_engine.py (optional reconciler=)
main.py (LIVE branch, explicit wiring)
tests/test_hardening_stage123.py, tests/test_stage123_operational.py

core/risk/risk_engine.py — Stage 1–3 delta

Additional imports: core.risk.costs, (Stage 4) os (stdlib)

core/live/broker_engine.py — Stage 1–3 delta

Additional imports: core.live.reconciler, core.execution.live_safety_gate (already)

============================================================
ADDENDUM — STAGE 4 (paper certification)
============================================================

config/risk_settings.py — additions (paper-only, env-overridable;
production defaults untouched)

PAPER_COMMISSION_PER_TRADE (QE_PAPER_COMMISSION_PER_TRADE, 0.0)
PAPER_COMMISSION_RATE (QE_PAPER_COMMISSION_RATE, 0.0)
PAPER_SLIPPAGE_BPS (QE_PAPER_SLIPPAGE_BPS, 0.0)
PAPER_COST_PROFILE_NAME (QE_PAPER_COST_PROFILE_NAME)
PAPER_COST_VENUE_REALISTIC (QE_PAPER_COST_VENUE_REALISTIC, false)
KILL_SWITCH_ENV_VAR = "QE_KILL_SWITCH"

Additional imports: os (stdlib, _os alias)

core/risk/costs.py — additions

paper_cost_profile(overrides=None), paper_profile_name(),
paper_venue_realistic() — all read the paper-only settings above;
never production defaults, never research ladders.

core/risk/risk_engine.py — additions

kill_switch_active(account): reads AccountState.kill_switch /
trading_enabled + KILL_SWITCH_ENV_VAR; enforced at the top of
analyze() (mandatory for every order). Additional import: os.

No other production import edges added in Stage 4. No research,
strategy, threshold, or production-default change.

============================================================
PHASE 12 ADDENDUM -- import edges
============================================================

New module:
core/execution/order_ack.py -- imports: none (stdlib only).
No production module imports it except
core/live/broker_engine.py (ack classification on the live
route + fetch watch).

Changed import edges (all additive, stdlib or existing):
- core/live/broker_engine.py += core.execution.order_ack
  (ACKNOWLEDGED/FILLED/PARTIAL/REJECTED/CANCELLED/EXPIRED/
  UNKNOWN, classify_ack, classify_exception),
  core.execution.order_executor.order_seq_value (journal),
  core.risk.risk_engine.kill_switch_active (route seam).
  No cycle: risk_engine never imports broker_engine.
- core/execution/order_executor.py -= time (wall-clock id
  removed); deterministic counter has no imports.
- core/setup/trade_setup_builder.py +=
  core.backtesting.accounting.directional_geometry_ok.
- core/risk/risk_engine.py +=
  core.backtesting.accounting (directional_geometry_ok,
  order_rr) + core.risk.account.roll_state_pnl_windows.
  No cycle: accounting is a leaf math module.
- backtesting/backtester.py +=
  core.backtesting.accounting (directional_geometry_ok,
  order_rr) + core.risk.risk_engine.kill_switch_active.
  No cycle: risk_engine never imports backtester.
- core/paper_trading/paper_trading_engine.py +=
  core.risk.risk_engine.kill_switch_active (same reason).
- core/risk/account.py: datetime imported LOCALLY inside
  roll_state_pnl_windows (no module-level dependency
  change); new roll_state_pnl_windows() consumed by
  risk_engine.
- data/delta/delta_subscription_stream.py: no new imports
  (Candle/normalize already imported).

Production <-> research boundary unchanged: no production
module imports research; research additions: none (Phase
12 adds no research code). No strategy, threshold, or
production-default change.

============================================================
PHASE 13 ADDENDUM (recertification; strategy frozen)
============================================================
- backtesting/backtester.py: execution-time directional
  geometry gate before RR revalidation
  (ORDER_SKIPPED_INVERTED_FILL); gap-through-target fills
  refused, gap-through-stop invalidates first (unchanged
  ordering). No threshold/strategy change.
- core/paper_trading/paper_trading_engine.py: legacy
  execution_signal fallback gated (kill + geometry + RR),
  consistent with the backtester legacy branch.
- tests/test_lookahead_13.py (NEW): 3 boundaries x 3
  divergent futures, byte-identical pre-T artifacts.
- No production import-edge changes beyond the above
  (accounting helpers reused; no new prod modules). No
  research code added. 11G verdicts and OOS gate untouched.

============================================================
PHASE 14 ADDENDUM (forensics; strategy frozen)
============================================================
- tests/test_edge_forensics_14.py (NEW, 22 tests): funnel
  terminal-exclusivity, phantom-win classification, single
  quantity multiplication, funding absence, VERIFIED/
  ASSUMED/UNAVAILABLE cost scenarios, LONG/SHORT gap
  boundaries (open==stop / open==target), OOS boundary
  integrity (6175-bar gate + verdict intact), frozen-gate
  pins (MIN_RISK_REWARD == 6.0), safe-default posture.
- research/results/phase14_executable_edge_forensics.json
  (NEW artifact): deterministic (byte-identical regen)
  forensic record incl. all 25 Gate-A orders, erosion
  distributions, cost scenarios, gate matrix; includes a
  bar-mapping correction to Phase-13 §5 numbers (entry bar
  = trigger_bar list index; stamps agree exactly).
- No production import-edge changes (test-only additions).
  No research code added. 11G verdicts and OOS gate untouched.

============================================================
PHASE 15 ADDENDUM (readiness; strategy frozen)
============================================================
- tests/test_researcher_15.py (NEW, 33 tests): baseline
  reproduction, dataset hashing/classification, instrument
  semantics, fee/funding/microstructure semantics,
  venue classification, temporal splitting, OOS isolation,
  sample-size gates (frozen 9M constants), actual-fill RR,
  gaps, regime/symbol/directional conditioning,
  multiple-testing preservation, lookahead causality,
  deterministic serialization, worker scope, production
  posture, frozen records.
- research/results/phase15_evidence_readiness.json (NEW
  artifact): deterministic (byte-identical regen) evidence-
  readiness record; periods/hypotheses empty by evidence
  (no fabrication); is_production_ready False.
- No production import-edge changes (zero modified
  production files). No research code added or modified.
  11G verdicts, OOS gate, and Phase-14 artifact untouched.

============================================================
PHASE 16 ADDENDUM (readiness regression; strategy frozen)
============================================================
- core/research/readiness/ (NEW, research-only, pure
  deterministic, no production imports): __init__.py +
  sample_math.py (expected_orders/expected_fills/
  required_bars/oos_span_bars/sample_ladder) +
  scenarios.py (scenario_structural VERIFIED-zero-cost /
  scenario_conservative_fees + slippage + combined ASSUMED /
  scenario_funding UNAVAILABLE-never-zero).
- tests/test_readiness_16.py (NEW, 36 tests): all 25
  mandated areas pinned as regression (baseline
  reproduction, dataset hash/classification, instrument,
  fee/funding/microstructure, cost scenarios, venue,
  temporal split, OOS isolation, sample gates + math,
  actual-fill RR, gaps, regime/symbol/directional,
  multiple-testing, lookahead, serialization, worker
  scope, production posture, frozen records).
- No production import-edge changes (zero modified
  production files). Phase-14/15 artifacts untouched.
  11G verdicts and OOS gate untouched.

============================================================
PHASE 17 ADDENDUM (acquisition + feasibility; strategy frozen)
============================================================
- core/research/acquisition/ (NEW, research-only, pure
  deterministic, no strategy/execution imports):
  __init__.py + provenance.py (ProvenanceManifest frozen
  canonical fields, manifest_id via frozen 11G
  content_hash, fetched_at EXCLUDED, closed
  COMPLETE/PARTIAL/EMPTY/BLOCKED) + quality.py
  (audit_quality over venue-verbatim rows, flat/
  zero-volume COUNTED never classified) +
  feasibility.py (recalculate_requirements/
  budget_periods over frozen Phase-16 sample_math,
  OOS_FEASIBLE/OOS_BLOCKED only).
- scripts/fetch_phase17_fresh.py (NEW, operator-run
  read-only acquisition via HistoricalLoader) +
  scripts/build_phase17_artifact.py (NEW, deterministic
  artifact builder; reads committed baselines + git-ignored
  fresh cache).
- tests/test_oos_feasibility_17.py (NEW, 27 tests, 9
  classes): identity/provenance/quality/sample/fresh-
  discipline/contamination/determinism/posture/frozen-
  boundaries.
- research/results/phase17_oos_feasibility.json (NEW
  artifact): deterministic (byte-stable regen) feasibility
  record; OOS_BLOCKED; is_production_ready False.
- No production import-edge changes (zero modified
  production files). Phase-14/15/16 artifacts untouched.
  11G verdicts, 7E REJECTED, and OOS gate untouched.

============================================================
PHASE 18 ADDENDUM (genuine OOS validation; strategy frozen)
============================================================
- core/research/oos_validation/ (NEW, research-only,
  deterministic): __init__.py + periods.py
  (validate_freshness/split_bars, stdlib-only) +
  execution.py (run_frozen_oos over frozen Backtester +
  InstitutionalPipeline defaults; no live imports) +
  report.py (classify_period/aggregate_results/
  decide_final over frozen 9M constants, stdlib-only).
- scripts/build_phase18_artifact.py (NEW, deterministic
  artifact builder; reads committed Gate-A/P14/P17 +
  git-ignored fresh cache; 6 per-period + 1 global frozen
  runs).
- tests/test_oos_validation_18.py (NEW, 30 tests):
  identity/boundary/periods/sample-RR/semantics/
  economics/consistency/honesty/lookahead/determinism/
  posture/frozen-boundaries.
- research/results/phase18_oos_validation.json (NEW
  artifact): deterministic (byte-stable regen) genuine
  OOS record; OOS_BLOCKED (0 fills); is_production_ready
  False.
- No production import-edge changes (zero modified
  production files). Phase-14/15/17 artifacts untouched.
  11G verdicts, 7E REJECTED, and OOS gate untouched.

============================================================
PHASE 19 ADDENDUM (OOS data extension; strategy frozen)
============================================================
- core/research/extension/ (NEW, research-only,
  deterministic, stdlib-only): __init__.py +
  extension.py (dedupe_merge/extension_stats/
  estimate_extension; no gap-fill, no synthetic).
- scripts/fetch_phase19_extension.py (NEW, operator-run
  read-only acquisition via HistoricalLoader; Tier A
  direct only) + scripts/build_phase19_artifact.py (NEW,
  deterministic builder; 6 per-period + 1 global frozen
  runs over merged span).
- tests/test_oos_data_extension_19.py (NEW, 25 tests
  covering 29 areas): baseline/boundary/dataset/quality/
  provenance/funnel/sample/periods/causality/posture/
  determinism.
- research/results/phase19_oos_data_extension.json (NEW
  artifact): deterministic (byte-stable regen) extension
  record; OOS_BLOCKED (0 fills/11899 bars);
  is_production_ready False.
- No production import-edge changes (zero modified
  production files). Phase-14/15/17/18 artifacts
  untouched. 11G verdicts, 7E REJECTED, and OOS gate
  untouched.

============================================================
OOS EXECUTION READINESS ADDENDUM (preregistration + readiness
gates; strategy frozen, 9M untouched)
============================================================
- core/research/readiness/preregistration.py (NEW, research-only,
  frozen dataclass, no production imports): FrozenPreregistration
  + PreregistrationError. Reuses HypothesisRecord identity
  (core.research.oos.oos_types), 9M protocol numbers
  (core.research.oos.constants), and the frozen 11G content_hash
  identity authority. Refuses seven_e_no_go hypotheses and
  is_production_ready=True; altered copies fail verify_identity().
- core/research/readiness/oos_execution_readiness.py (NEW,
  research-only, pure deterministic, no production imports):
  GateVerdict + OOSExecutionReadinessReport + evaluate() +
  observe_dataset() + required_per_period_bars() (25000.0) +
  required_fresh_bars() (300000.0). Reuses validate_freshness
  (frozen boundary), sample_math arithmetic at measured Gate-A
  rates (0.005 orders/bar, 0.08 fill rate), and the 11G-Q 6175
  contiguous-bar gate. Missing evidence stays UNAVAILABLE/
  BLOCKED (never passes); final READINESS_VERIFIED requires
  every gate VERIFIED. Readiness never executes OOS.
- core/research/readiness/__init__.py (EXTENDED, additive
  re-exports only): FrozenPreregistration, PreregistrationError,
  GateVerdict, OOSExecutionReadinessReport, ReadinessError,
  evaluate, observe_dataset, required_fresh_bars,
  required_per_period_bars.
- tests/test_oos_execution_readiness.py (NEW, 28 tests,
  stdlib-only, offline): preregistration immutability (10),
  documented arithmetic (1), readiness fixtures A-H (10),
  lookahead/determinism (3), production isolation (2),
  real-data BLOCKED evaluation (1) + empty-set BLOCKED (1).
- No production import-edge changes (zero modified production
  files). 9M implementation, 9M tests, historical pins, and all
  research artifacts untouched. Real-data verdict on current
  caches: OOS_EXECUTION_READINESS = BLOCKED.

============================================================
OOS TOP-UP ACQUISITION ADDENDUM (public data only; strategy
frozen, protocol untouched, no execution)
============================================================
- scripts/fetch_oos_topup.py (NEW, operator-run, read-only):
  full post-Gate-A BTCUSDT 1m fetch via HistoricalLoader.
  candles_paginated + dedupe_merge with the Phase-19 cache
  into NEW git-ignored data/history/BTCUSDT_1m_oos_topup.json
  (+ .provenance.json with venue/method/merge/identity
  authorities). Phase-17/19 caches and all research artifacts
  never overwritten. Dataset identity reuses the Phase-19
  dataset_hash construction. No credentials, no orders.
- data/fixtures/delta/delta_venue_economics_observation_
  20260925.json (NEW observation fixture): venue fee docs +
  MCP product corroboration (maker 0.0002 / taker 0.0005
  PARTIAL with tier/symbology/GST limitations; funding
  mechanism PARTIAL; contract value + slippage UNAVAILABLE).
  Docs provenance with URLs + date; nothing provisioned into
  costs.py.
- tests/test_oos_topup_acquisition.py (NEW, 18 tests,
  stdlib-only, offline, no network): acquisition fixtures
  A-H, lookahead A-D (mutation/metadata/reorder/duplicate
  accounting), fill + economics integrity, top-up cache
  provenance + Phase-19 untouched, real top-up readiness
  still BLOCKED, AST-verified production isolation of the
  fetch script and readiness modules.
- No production import-edge changes. 9M, pins, and research
  artifacts untouched. Top-up result: 11899 -> 29491 genuine
  post-boundary bars (identity 75e8338f...); readiness still
  BLOCKED (bars/fills/economics/microstructure).

============================================================
READINESS MONITOR ADDENDUM (reuse-only layer; no new engine,
no execution path)
============================================================
- core/research/readiness/monitor.py (NEW, research-only,
  deterministic, no production/wall-clock imports):
  Blocker (9 closed classes) + classify_blockers() +
  derive_handoff() (WAITING_FOR_DATA / ... / READY_FOR_
  PREREGISTRATION / READY_FOR_OOS_EXECUTION terminal) +
  source_status() (CURRENT / NO_NEW_SOURCE_DATA from source
  timestamps only) + ReadinessSnapshot (frozen, content_hash
  id, arithmetic gaps, no datetime/time/random/uuid) +
  run_monitor() (evaluate -> snapshot -> blockers -> handoff
  -> stop; unprovenanced rows get OPERATOR_PREREQUISITE;
  overall downgraded when provenance is not A-DIRECT).
  Reuses evaluate/observe_dataset/preregistration/content_hash.
- core/research/readiness/__init__.py (EXTENDED, additive
  re-exports): Blocker, MonitorError, ReadinessSnapshot,
  classify_blockers, derive_handoff, run_monitor,
  source_status.
- tests/test_readiness_monitor.py (NEW, 21 tests, stdlib-only,
  offline): snapshot determinism + ordering, blocker classes,
  handoff states (incl. READY terminal never executes),
  source condition, lookahead A-F, AST-verified isolation,
  real-data snapshot (BLOCKED / WAITING_FOR_DATA, gap 270509).
- Real snapshot: overall BLOCKED, handoff WAITING_FOR_DATA.
  9M, pins, artifacts untouched.

============================================================
UPSTREAM HYPOTHESIS AUDIT ADDENDUM (bounded forensic audit;
no discovery/execution; 9M untouched)
============================================================
- Verdict: 0 real hypotheses is genuine (MIXED_CAUSE: no
  eligible persisted findings + upstream never executed on
  real data outside fixture tests; research caches are
  gitignored/ephemeral). Persisted evidence: 11F 8 x
  RESEARCH_ONLY; 11G-T/U hypotheses_executed = 0; phase-18/19
  0 fills; 11F family n_survive = 0; 9J/9K/9L run fixture-only
  in tests (no script/pipeline runs them on real data).
- Adapter determination: DiscoveryFinding lacks params,
  baseline, symbol, direction, regime, walk-forward and
  family fields, so a mechanical DiscoveryFinding ->
  HypothesisRecord edge would invent research semantics;
  the absent edge is an INTENTIONAL research boundary, not
  missing plumbing (no adapter implemented, none required).
- tests/test_upstream_hypothesis_audit.py (NEW, 14 tests,
  stdlib-only, offline): no finding-to-record edge in core
  (only input coercion), persisted zero counts, fixture/real
  namespace separation, TREND/LONG conditionality, 7E
  refusal, Sidak preserved, determinism.
- No production/research code modified. Pins, dirt, .env,
  thresholds, and OOS readiness untouched.

============================================================
END
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
LEVEL 4 FOLLOW-UP — PAPER ECONOMICS AUTHORITY CLOSURE
============================================================
- `core/paper_trading/paper_trading_engine.py` now consumes the canonical
  `paper_cost_profile()` at actual paper-fill time. The paper readiness profile
  and paper fill economics therefore share one authority.
- Explicit `fill_slippage_bps` remains an additional fill-price model and is
  not silently substituted for round-trip accounting slippage.
- Post-cost R:R continues through the shared `TradeSimulator.open_trade()`
  choke and the runtime trading policy remains inclusive 1:1..1:20.
- Regression: 148/148 affected tests PASS; compileall PASS.
- `.vscode/mcp.json` restored as a testnet-only Delta MCP server declaration;
  no credentials or production environment values are stored.
- Historical forensic digest pins remain untouched. Production readiness FALSE.

## PHASE 24 — DELTA MCP PUBLIC OBSERVATION NORMALIZATION

`research/integrations/delta_mcp_observations.py` is a research-only adapter for deterministic normalization of already-received public Delta MCP responses. It is not imported by production execution modules and has no network or trading authority. It preserves unavailable fields as UNAVAILABLE/PARTIAL and assigns deterministic SHA-256 observation identities. `tests/test_delta_mcp_observations_24.py` provides the import/test boundary.

### Phase 27 research-only import

`research/integrations/delta_mcp_discovery_context.py` is research-only. It consumes `core.research.dataset` rows and has no production imports, network access, credential access, account access, or execution authority.

PHASE 28 NOTE
- `core/research/regime/engine.py` may read `research.integrations.delta_mcp_regime_context` only for deterministic research-context limitations. The MCP context has no production execution, account, trading, credential, or network authority and does not alter regime calculations.

### Phase 32 — strict OOS acquisition accumulator

`core/research/acquisition/accumulator.py` is research-only and pure. It validates post-boundary rows, exact provenance coverage, deterministic batch identity, and fail-closed conflicting duplicate timestamps. `scripts/fetch_oos_topup.py` consumes it for future operator-run top-ups. No production imports are introduced.

### Phase 30 — OOS evidence accumulation

`tests/test_phase30_oos_evidence.py` validates the deterministic Phase-30 evidence artifact, strict post-discovery boundary, six-period ordering/non-overlap, and research-only isolation of `scripts/build_phase30_oos_evidence.py`. The script imports only the existing research OOS execution seam; it does not import live, broker, paper-trading, strategy, or execution modules and contains no order-submission path.

### Phase 33 — deterministic current OOS readiness snapshot

`core/research/readiness/monitor.py` and the existing OOS readiness evaluator
remain the sole readiness authorities. `scripts/build_phase33_oos_readiness_snapshot.py`
binds the current direct-venue OOS cache, acquisition provenance, execution
sample count, and existing readiness gates into
`research/results/phase33_oos_readiness_snapshot.json`.

No new gate math, execution path, hypothesis selection, or production import
was introduced. The snapshot is research-only, deterministic, and permanently
`is_production_ready=false`.


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

`core/research/readiness/symbol_coverage.py` now optionally uses the existing
Phase-20 row-level provenance sidecar as the authoritative symbol source when
its timestamp set exactly covers the dataset. Filename/envelope inference is
never used. Phase 36 adds `scripts/build_phase36_provenance_symbol_coverage.py`
and `tests/test_phase36_provenance_symbol_coverage.py` plus artifact tests.
The current dataset resolves to one provenance-bound symbol (BTCUSDT); this
improves attribution but does not establish cross-symbol robustness or OOS
validation. Production readiness remains false.

### Phase 37 — Multi-symbol OOS acquisition

`core.research.acquisition.multi_symbol` validates independently acquired symbol batches and produces a deterministic manifest without collapsing instrument namespaces. Current snapshot contains only provenance-bound BTCUSDT evidence; no universal cross-symbol claim is emitted.

### Phase 38 — Multi-symbol OOS aggregation

`core/research/readiness/symbol_aggregation.py` provides deterministic research-only aggregation of independently evaluated symbol evidence. It preserves per-symbol status and distinguishes missing/unavailable evidence from rejected evidence; it does not promote universal validation.

### Phase 39

`core/research/readiness/preregistration.py` now provides the sanctioned deterministic persisted-artifact reload path via `FrozenPreregistration.from_dict()`. The reload path reconstructs only the frozen schema, refuses malformed/tampered content, and preserves the existing content-hash identity authority. It is research-only and never creates or selects hypotheses.

## PHASE 43 — RESEARCH IMPORT BOUNDARY

- `core/research/oos/selection.py` and `core/research/readiness/selection_preregistration.py` are research-only handoff seams.
- `core/research/oos/engine.py::run_preregistered` consumes only an already verified frozen preregistration and invokes the existing research OOS engine.
- `tests/test_phase43_research_import_boundary.py` scans actual Python import statements and dynamic production-module strings for forbidden production runtime dependencies.
- No production execution, order, ledger, live, or paper runtime import was added.

### Phase 56 — deterministic OOS builder hardening
- `scripts/build_phase17_artifact.py` is research-only and deterministic given its declared inputs.
- No network imports or URL acquisition are permitted in the artifact builder.
- `data/history/BTCUSDT_product_phase17.json` is a required pre-existing input.
- Missing product evidence fails closed as `MISSING_PRODUCT_SNAPSHOT`.
- Standalone CLI repository-path bootstrap is explicit.

### Phase 57 — explicit product snapshot acquisition
- `scripts/acquire_phase17_product_snapshot.py` is the sole Phase-17 product snapshot acquisition operator.
- It reuses `core.exchanges.delta.delta_products.DeltaProducts`.
- It requires caller-supplied `--observed-label` and has no wall-clock/UUID dependency.
- It is public, credential-free, read-only, and writes the snapshot atomically.
- `scripts/build_phase17_artifact.py` remains offline and deterministic given the snapshot.

### Phase 58 — phase continuity / loss-prevention audit
Phase continuity metadata is research-only and lives in
`research/results/phase58_phase_continuity.json`.


### Phase 59 — phase-continuity restoration + recovery checkpoint

Restored source-backed Phase-47 journal persistence and Phase-48 deterministic 9A discovery capture using the existing ResearchRepository/Backtester/ResearchJournal architecture. Preserved Phase-49 as missing genuine evidence and created an honest Phase-55 recertification boundary artifact. Added `research/results/phase59_continuity.json` as the authoritative continuity manifest. Production readiness remains false.

## PHASE 60 — PHASE 44–57 CONTINUITY LOCK

Research-only continuity coverage verifies the source/test seams for Phases
44–57, with Phase 49 explicitly marked as a missing genuine artifact rather
than synthesized evidence. No production imports or authority are added.
