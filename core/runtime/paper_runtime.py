"""
====================================================

QuantEngine

Paper Runtime

Phase 6E -- Real-time integration (paper mode only).

The per-instrument continuous paper unit. Owns ONE frozen
SymbolPipeline and drives it through the canonical Broker
Engine in paper mode (dry_run=True) -- the SAME explicit
per-candle order as the Backtester:

    closed candle
         -> pipeline world (setup -> decision -> RiskEngine
            OrderIntent)
         -> paper fill via TradeSimulator (next-bar-close
            of the signal candle, mirroring the Backtester)
         -> TradeSimulator.update  (SL / TP exits)
         -> TradeRegistry  (the PAPER_TRADE_REGISTRY ledger)

The execution boundary -- the only part that differs for a
future live run -- is the injected ExecutionPort
(PaperExecutionAdapter here). All strategy, risk and
position-management logic is the frozen engine's: nothing
is re-implemented in this runtime. canonical_id (Phase 6C)
flows setup -> OrderIntent -> Trade verbatim.
====================================================
"""

from config import risk_settings

from core.analytics.performance import PerformanceAnalytics
from core.backtesting.trade_registry import TradeRegistry
from core.live.broker_engine import BrokerEngine
from core.risk.account import Account
from core.runtime.execution_port import PaperExecutionAdapter
from core.runtime.pipeline_registry import instrument_identity_key


class PaperRuntime:

    def __init__(
        self,
        instrument,
        pipeline,
        starting_balance=None,
        portfolio_gate=None,
        portfolio_release=None,
        journal=None,
    ):

        self.instrument = instrument

        self.pipeline = pipeline

        # Phase 9A research journal (PAPER provenance). Optional
        # observer over the settled bar; default None keeps the
        # runtime bottleneck behaviouridentical.
        self.journal = journal

        self.starting_balance = (
            starting_balance
            if starting_balance is not None
            else risk_settings.STARTING_BALANCE
        )

        self.port = PaperExecutionAdapter()

        self.engine = BrokerEngine(
            pipeline=pipeline.world,
            event_bus=pipeline.event_bus,
            executor=self.port,
            simulator=pipeline.simulator,
            account=Account(starting_balance=self.starting_balance),
            dry_run=True,
            portfolio_gate=portfolio_gate,
            portfolio_release=portfolio_release,
        )

        self.retired = False

    # --------------------------------------------------

    @property
    def key(self):

        return instrument_identity_key(
            getattr(self.instrument, "exchange", "") or "",
            getattr(self.instrument, "instrument_id", "") or "",
        )

    @property
    def symbol(self):

        return getattr(self.instrument, "symbol", "") or ""

    # --------------------------------------------------

    def process_closed_candle(self, candle):

        if self.retired:

            return

        self.engine.run_candle(candle)

        # Phase 9A research journal (PAPER): observe the settled
        # bar. Fail-safe -- the journal never raises into the
        # trading path (errors are swallowed + logged internally).
        if self.journal is not None:

            try:

                self.journal.on_bar_observed(
                    self.pipeline.context,
                    candle,
                    registry=self.engine.registry,
                    provenance="PAPER",
                )

            except Exception:

                pass

    # --------------------------------------------------

    def retire(self):
        """Halt candle intake. The ledger stays queryable so
        analytics can still read every retired instrument's
        trades; the subscription was already dropped by the
        manager's universe diff."""

        self.retired = True

    # --------------------------------------------------

    @property
    def ledger(self):

        return self.engine.registry

    @property
    def current_trade(self):

        return self.engine.current_trade

    @property
    def account(self):

        return self.engine.account

    @property
    def executed_intents(self):

        return tuple(self.engine.placed)

    @property
    def processed_bars(self):

        return self.engine.processed_bars

    # --------------------------------------------------

    def report(self):
        """Canonical per-instrument performance report (Phase 9P-c).

        Returns the SHARED PerformanceReport over this runtime's
        completed (status == "CLOSED") trades. PURE delegation to
        PerformanceAnalytics -- the single canonical PF/expectancy
        calculation -- this runtime never recomputes any metric, so
        the report can never disagree with the backtest / validation
        surfaces. On-demand only: not called in the candle path, so
        it never blocks the event loop. Deterministic for the same
        completed-trade state.

        Account stays a counter-only state holder; no report metric
        is copied into AccountState (no second analytics surface).
        """

        return PerformanceAnalytics.analyze(self.account, self.ledger)

    # --------------------------------------------------

    def state(self):
        """Observable runtime snapshot for the orchestrator /
        analytics. Live subscription state is owned by the
        manager and merged by the engine's statuses()."""

        return {
            "symbol": self.symbol,
            "exchange": getattr(self.instrument, "exchange", "") or "",
            "instrument_id": (
                getattr(self.instrument, "instrument_id", "") or ""
            ),
            "retired": self.retired,
            "processed_bars": self.processed_bars,
            "open_position": self.current_trade is not None,
            "trades": self.ledger.count(),
            "balance": self.account.balance,
            "equity": self.account.equity,
        }