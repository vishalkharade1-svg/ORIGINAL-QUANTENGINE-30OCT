"""
====================================================

QuantEngine

RealTime Engine

Phase 6E -- Real-time integration (paper mode only).

The 6E orchestrator wires the already-built 6B universe
refresh and the 6D real-time delivery into the frozen 6C
SymbolPipeline, coordinated (never duplicated) across the
existing components:

    RefreshScheduler (reuses 6B UniverseManager/Discovery)
          -> eligible instrument cut
              -> PipelineRegistry.reconcile  (ADD/RETAIN/RETIRE)
              -> MultiSymbolSubscriptionManager.sync (6D)
          -> manager.poll  (closed candles only)
              -> _on_closed_candle
                  -> symbol -> instrument record
                  -> (exchange, instrument_id) identity key
                  -> PaperRuntime.process_closed_candle
                      (BrokerEngine dry-run / TradeSimulator /
                       TradeRegistry ledger)

Routing is bound to the canonical instrument identity --
(exchange, instrument_id) -- exactly as 6C defined it: a
candle reaches ONLY the pipeline owning that identity,
never by subscription or position order, so BTC candles can
never mutate the ETH pipeline.

Stable pipeline ownership: a retained instrument keeps the
SAME SymbolPipeline object (with its continuous structural
window) across refreshes; a retired instrument moves to the
registry snapshot (ledger still readable) and drops its
subscription; a new instrument gets a brand-new pipeline.
No rebuild on refresh.

Paper-only by construction: every runtime runs the Broker
Engine with dry_run=True and a PaperExecutionAdapter
executor. Zero exchange writes. The TradeRegistry ledger of
each runtime is the PAPER_TRADE_REGISTRY.
====================================================
"""

from config import risk_settings
from core.exchanges.paper_data_gate_policy import validate_paper_data_gate_config

from data.realtime.subscription_manager import (
    MultiSymbolSubscriptionManager,
)

from core.runtime.paper_runtime import PaperRuntime
from core.runtime.pipeline_registry import (
    PipelineRegistry,
    instrument_identity_key,
)
from core.universe.refresh_scheduler import RefreshScheduler

from core.common.logging_config import get_logger

log = get_logger(__name__)


class RealTimeEngine:

    def __init__(
        self,
        universe_manager,
        refresh_scheduler=None,
        subscription_manager=None,
        world_factory=None,
        timeframe="1m",
        strategy="",
        data_source=None,
        transport_factory=None,
        clock=None,
        refresh_interval_seconds=60,
        starting_balance=None,
        portfolio_manager=None,
        portfolio_state=None,
        journal=None,
        market_data_max_age_seconds=None,
        market_data_now_provider=None,
        market_data_gate_required=False,
    ):

        # Phase 208: one canonical orchestrator owns the optional paper
        # market-data quality gate. None preserves the legacy path; an
        # explicit finite non-negative threshold enables fail-closed checks.
        self.market_data_max_age_seconds = validate_paper_data_gate_config(
            market_data_max_age_seconds,
            required=market_data_gate_required,
            now_provider=market_data_now_provider,
        )
        self.market_data_gate_required = market_data_gate_required
        self.market_data_now_provider = market_data_now_provider

        self.universe_manager = universe_manager

        self.clock = clock

        self.timeframe = timeframe

        self.starting_balance = (
            starting_balance
            if starting_balance is not None
            else risk_settings.STARTING_BALANCE
        )

        # Phase 8 shared portfolio risk manager. Defaults to a
        # default-NEUTRAL manager (no caps configured) so live/paper
        # behaviour is unchanged unless one is supplied. When given,
        # every PaperRuntime shares the SAME portfolio policy ->
        # aggregate exposure / concurrency / directional /
        # correlated / drawdown caps are enforced across ALL
        # symbols, for both backtest and live/paper, from one gate.
        if portfolio_manager is None:

            from core.risk.portfolio import PortfolioRiskManager

            portfolio_manager = PortfolioRiskManager()

        self.portfolio_manager = portfolio_manager

        # Phase 9A research journal. Optional observer; when
        # supplied it is shared across every PaperRuntime so the
        # journal aggregates ALL symbols (multi-symbol keyed by
        # canonical identity). A future live integration can attach
        # the same journal; live trading itself is NOT enabled by
        # this phase.
        self.journal = journal

        # Phase 8B: optional unified portfolio state (shared capital +
        # risk budget + reservation lifecycle). When provided it takes
        # precedence over the manager for the per-runtime gate/release
        # hooks, so live/paper runs through the SAME allocator lifecycle
        # (reserve on accept, release on close) as the backtest path --
        # parity by construction. None (default) leaves behaviour
        # unchanged.
        self.portfolio_state = portfolio_state

        # symbol -> reservation_id held while that symbol's position is
        # open (single-position-per-symbol keying), for the state path.
        self._reservation_by_symbol = {}

        self.registry = PipelineRegistry(
            world_factory=world_factory,
            timeframe=timeframe,
            strategy=strategy,
            data_source=data_source,
        )

        self.refresh_scheduler = (
            refresh_scheduler
            if refresh_scheduler is not None
            else RefreshScheduler(
                manager=universe_manager,
                interval_seconds=refresh_interval_seconds,
                clock=clock,
            )
        )

        self.subscriptions = (
            subscription_manager
            if subscription_manager is not None
            else MultiSymbolSubscriptionManager(
                clock=clock,
                transport_factory=transport_factory,
                candles_callback=self._on_closed_candle,
            )
        )

        # identity key -> PaperRuntime
        self.runtimes = {}

        # symbol -> instrument record of the latest eligible
        # cut (the router's only lookup; the route target is
        # the instrument identity, never the symbol).
        self._instruments = {}

        # route accounting / observability
        self.routed = 0

        self.unrouted = 0

        # Phase 11C: per-symbol downstream failures are
        # isolated (one symbol's strategy/risk exception can
        # never starve the other runtimes) and counted.
        self.route_errors = 0

        self.last_route_error = ""

        self.reconcile_errors = 0

        self.started = False

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    def start(self):

        self.started = True

        self.refresh()

    # --------------------------------------------------

    def stop(self):

        self.subscriptions.stop_all()

        self.started = False

    # --------------------------------------------------
    # Feed clock
    # --------------------------------------------------

    def poll(self, client=None, normalizer=None):
        """One non-blocking scheduling tick: refresh the
        universe if due, then drain the live subscription
        streams (both steps clock-driven; neither blocks).
        Channel kwargs straight through to the 6B discovery
        (the 6D manager and the registry need none).

        Phase 10: If refresh_scheduler is an AsyncRefreshScheduler,
        the refresh runs in background and this poll never blocks.
        A completed background refresh is picked up via cached universe.
        """

        universe = None
        # Check if scheduler is async wrapper
        if hasattr(self.refresh_scheduler, 'get_cached_universe'):
            # Async path: run_if_due starts background refresh if due, returns None immediately
            self.refresh_scheduler.run_if_due(
                timeframe=self.timeframe,
                client=client,
                normalizer=normalizer,
            )
            # Check if a previously backgrounded refresh has completed and produced a new universe
            # We detect new universe by comparing last_universe to our last seen
            # For now, we check if scheduler has a new last_universe that we haven't reconciled
            # Use the async wrapper's cached universe if it's newer than our last _instruments
            cached = self.refresh_scheduler.get_cached_universe()
            # Only reconcile if cached is not None and different from current instruments
            # We use a simple heuristic: if cached is not None and we haven't seen it before, reconcile
            # To avoid reconciling same universe repeatedly, track last reconciled id
            if cached is not None:
                # Check if this cached universe is new (not yet reconciled)
                # We can use id(cached) or captured_at
                last_id = getattr(self, '_last_reconciled_id', None)
                cached_id = id(cached)
                if cached_id != last_id:
                    universe = cached
                    self._last_reconciled_id = cached_id
        else:
            universe = self.refresh_scheduler.run_if_due(
                timeframe=self.timeframe,
                client=client,
                normalizer=normalizer,
            )

        if universe is not None:

            try:

                self._reconcile(universe)

            except Exception as error:

                self.reconcile_errors += 1
                self.last_route_error = str(error)[:200]

                log.error(
                    "RECONCILE_ERROR error=%s", error,
                )

        try:

            self.subscriptions.poll()

        except Exception as error:

            self.reconcile_errors += 1
            self.last_route_error = str(error)[:200]

            log.error(
                "SUBSCRIPTION_POLL_ERROR error=%s", error,
            )

    # --------------------------------------------------

    def refresh(self, client=None, normalizer=None):
        """Force a universe refresh + reconcile now."""

        universe = self.refresh_scheduler.force_refresh(
            timeframe=self.timeframe,
            client=client,
            normalizer=normalizer,
        )

        if universe is None:

            return None

        self._reconcile(universe)

        return universe

    # --------------------------------------------------
    # Reconcile (universe -> registry + subscriptions)
    # --------------------------------------------------

    def _reconcile(self, universe):

        instruments = list(universe.eligible_instruments())

        self._instruments = {
            getattr(i, "symbol", "") or "": i
            for i in instruments
        }

        diff = self.registry.reconcile(instruments)

        # ---- retire absent instruments first ----

        for key in diff["retired"]:

            runtime = self.runtimes.pop(key, None)

            if runtime is not None:

                runtime.retire()

            log.info("PIPELINE_RETIRED key=%s", key)

        # ---- build runtimes for newly added instruments ----

        for key in diff["added"]:

            pipeline = self.registry.get(key)

            if pipeline is None:

                continue

            self.runtimes[key] = PaperRuntime(
                instrument=pipeline.instrument,
                pipeline=pipeline,
                starting_balance=self.starting_balance,
                portfolio_gate=self._portfolio_gate,
                portfolio_release=self._portfolio_release,
                journal=self.journal,
                market_data_max_age_seconds=self.market_data_max_age_seconds,
                market_data_now_provider=self.market_data_now_provider,
                market_data_gate_required=getattr(self, "market_data_gate_required", False),
            )

            log.info("PIPELINE_ADDED key=%s symbol=%s", key, pipeline.instrument.symbol)

        for key in diff["retained"]:

            log.debug("PIPELINE_RETAINED key=%s", key)

        # ---- sync the live subscriptions to the same cut ----

        self.subscriptions.sync(instruments)

    # --------------------------------------------------
    # Delivery routing (symbol -> instrument identity)
    # --------------------------------------------------

    def _on_closed_candle(self, candle):
        """6D manager delivery: a POST-entropy closed candle for
        one subscribed symbol. Resolve the symbol to its eligible
        instrument record, then route on the (exchange,
        instrument_id) identity key -- never by position or
        subscription order."""

        symbol = getattr(candle, "symbol", "") or ""

        instrument = self._instruments.get(symbol)

        if instrument is None:

            self.unrouted += 1

            return

        key = instrument_identity_key(
            getattr(instrument, "exchange", "") or "",
            getattr(instrument, "instrument_id", "") or "",
        )

        runtime = self.runtimes.get(key)

        if runtime is None:

            self.unrouted += 1

            return

        self.routed += 1

        try:

            runtime.process_closed_candle(candle)

        except Exception as error:

            self.route_errors += 1
            self.last_route_error = str(error)[:200]

            log.error(
                "RUNTIME_ROUTE_ERROR symbol=%s key=%s error=%s",
                symbol, key, error,
            )

    # --------------------------------------------------
    # Portfolio gate / release (Phase 8 / 8B)
    # --------------------------------------------------

    def _portfolio_gate(self, order):
        """Canonical portfolio gate shared by every PaperRuntime.

        Phase 8B preferred: consults the shared PortfolioState and,
        on a True verdict, RESERVES capital (bookkeeping). Pure
        decision -- never mutates the order / setup / strategy."""

        if self.portfolio_state is not None:

            from core.risk.portfolio_state import CapitalCandidate

            candidate = CapitalCandidate.from_order(order)

            if not self.portfolio_state.can_accept(candidate):

                return False

            rid = self.portfolio_state.reserve(candidate)

            symbol = getattr(order, "symbol", None)

            self._reservation_by_symbol[symbol] = rid

            return True

        if not self.portfolio_manager.order_allows(order):

            return False

        self.portfolio_manager.register_open(order)

        return True

    # --------------------------------------------------

    def _portfolio_release(self, closed_trade):
        """Release a closed trade's exposure.

        Phase 8B preferred: releases the shared state's reservation,
        folding realized PnL into shared equity (bookkeeping only)."""

        if self.portfolio_state is not None:

            symbol = getattr(closed_trade, "symbol", None)

            rid = self._reservation_by_symbol.pop(symbol, None)

            if rid is not None:

                self.portfolio_state.release(
                    rid,
                    pnl=getattr(closed_trade, "pnl", 0.0),
                )

            return

        self.portfolio_manager.release_closed(closed_trade)

    # --------------------------------------------------
    # Observability
    # --------------------------------------------------

    def statuses(self):
        """Per-symbol runtime snapshot merged with the 6D
        subscription status for the live control surface."""

        statuses = {}

        for key, runtime in self.runtimes.items():

            state = runtime.state()

            state["subscription_status"] = (
                self.subscriptions.status(
                    state["symbol"]
                )
            )

            statuses[state["symbol"]] = state

        return statuses

    # --------------------------------------------------

    def ledger(self):
        """symbol -> PaperRuntime ledger (PAPER_TRADE_REGISTRY)."""

        return {
            runtime.symbol: runtime.ledger
            for runtime in self.runtimes.values()
        }

    # --------------------------------------------------

    def performance(self, symbol=None):
        """Canonical runtime performance report(s) (Phase 9P-c).

        symbol given  -> single PerformanceReport for that
                         symbol's active runtime (None if the symbol
                         is not currently active -- matching the
                         universe-routing semantics).
        symbol None   -> aggregate PerformanceReport across ALL
                         active runtimes' completed trades, with the
                         shared portfolio starting balance (sum of the
                         per-runtime starting balances) so final
                         equity reconciles across the whole PAPER
                         book.

        PURE delegation to PerformanceAnalytics (the one canonical
        PF/expectancy/win-rate calculation) -- the engine never
        recomputes any metric. On-demand only, never in the candle
        path; deterministic for the same completed-trade state. No
        report metric is copied into any Account/AccountState (the
        accounts remain counter-only).
        """

        from core.analytics.performance import PerformanceAnalytics
        from core.backtesting.trade_registry import TradeRegistry
        from core.risk.account import Account

        if symbol is not None:

            for runtime in self.runtimes.values():

                if runtime.symbol == symbol:

                    return PerformanceAnalytics.analyze(
                        runtime.account,
                        runtime.ledger,
                    )

            return None

        aggregate = TradeRegistry()

        starting = 0.0

        for runtime in self.runtimes.values():

            for trade in runtime.ledger.all():

                aggregate.add(trade)

            acc = getattr(runtime.account, "state", runtime.account)

            starting += float(acc.starting_balance)

        account = Account(starting_balance=starting)

        return PerformanceAnalytics.analyze(account, aggregate)

    # --------------------------------------------------

    def all_trades(self):
        """Flat closed-trade view across every active runtime,
        lexicographic by (symbol, entry_time)."""

        keyed = []

        for runtime in self.runtimes.values():

            symbol = runtime.symbol

            for trade in runtime.ledger.all():

                keyed.append((symbol, trade))

        keyed.sort(
            key=lambda pair: (
                pair[0],
                getattr(pair[1], "entry_time", 0) or 0,
            )
        )

        return [trade for _, trade in keyed]

    # --------------------------------------------------

    @property
    def portfolio(self):
        """The active shared portfolio coordination object.

        Phase 8B preferred: the unified PortfolioState (shared
        capital + reservation ledger), observable via .snapshot().
        Falls back to the Phase 8 PortfolioRiskManager when no state
        is configured (default). The gate is read-only for the
        strategy and only ever declines / reserves -- never mutates."""

        if self.portfolio_state is not None:

            return self.portfolio_state

        return self.portfolio_manager