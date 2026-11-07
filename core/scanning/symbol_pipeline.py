"""
====================================================

Symbol Pipeline (per-instrument isolated pipeline)

Phase 6C -- ONE instrument, ONE pipeline, ZERO shared
mutable state.

A SymbolPipeline wraps a single instrument's pipeline
lifecycle:

    reset()  -> fresh PipelineContext (own MarketState with
                exchange + instrument_id), fresh world, fresh
                EventBus, fresh TradeSimulator, fresh
                Backtester. Nothing is shared with other
                instruments, so no state can leak between
                scans and no instrument can mutate a
                neighbour.

    run()    -> fetch bars (data_source) or accept caller
                bars, drive the per-symbol world through the
                canonical Backtester, return a
                SymbolScanResult. The world factory is
                injectable; the default is the canonical
                InstitutionalPipeline.

The wrapper also accumulates every setup candidate seen on
every candle (the per-candle context.trade_setups is a
per-candle snapshot, not a registry), so the result carries
the full scan window's setups -- each carrying its
canonical_id stamped at creation by TradeSetupBuilder.

====================================================
"""

from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester
from core.events.event_bus import EventBus
from core.events.event_types import EventType
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.scanning.scan_result import ScanStatus
from core.scanning.scan_result import SymbolScanResult


def default_world_factory(context):
    """
    The production world: the canonical InstitutionalPipeline
    wired to the given context. Injectable counterpart used by
    tests/scripted harnesses is a four-engine world with the
    same on_candle / context / reset contract.
    """
    from core.pipeline.institutional_pipeline import InstitutionalPipeline

    return InstitutionalPipeline(context)


class SymbolPipeline:

    def __init__(
        self,
        instrument,
        timeframe="1m",
        strategy="",
        data_source=None,
        world_factory=None,
    ):

        self.instrument = instrument

        self.timeframe = timeframe

        self.strategy = strategy

        self.data_source = data_source

        self._world_factory = (
            world_factory
            if world_factory is not None
            else default_world_factory
        )

        self.context = None

        self.world = None

        self.event_bus = None

        self.simulator = None

        self.backtester = None

        self._setups = []

    # -------------------------------------------------

    @property
    def symbol(self):
        return (
            getattr(self.instrument, "symbol", "")
            or ""
        )

    # -------------------------------------------------

    def reset(self):
        """
        Build a fully fresh, isolated world for THIS instrument.
        """
        self.context = PipelineContext()

        self.context.market = MarketState(
            symbol=self.symbol,
            timeframe=self.timeframe,
            exchange=(
                getattr(
                    self.instrument, "exchange", ""
                )
                or ""
            ),
            instrument_id=(
                getattr(
                    self.instrument, "instrument_id", ""
                )
                or ""
            ),
        )

        self._setups = []

        self.world = self._world_factory(self.context)

        self.event_bus = EventBus()

        self.event_bus.subscribe(
            EventType.CANDLE,
            self._on_candle,
        )

        self.simulator = TradeSimulator()

        self.backtester = Backtester(
            self.world,
            self.event_bus,
            self.simulator,
        )

    # -------------------------------------------------

    def _on_candle(self, event):
        """
        Bridge: dispatch the candle to the world, then record
        the world's candidates for THIS candle so the scan
        result holds every setup of the whole window.
        """
        on_candle = getattr(self.world, "on_candle", None)

        if on_candle is not None:
            on_candle(event)

        candidates = list(
            getattr(
                self.context, "trade_setups", ()
            )
            or ()
        )

        if candidates:
            self._setups.extend(candidates)

    # -------------------------------------------------

    def _fetch(self, window=None):
        if self.data_source is None:
            return None

        return self.data_source.get_candles(
            self.symbol,
            self.timeframe,
            window,
        )

    # -------------------------------------------------

    def run(self, candles=None, window=None):
        """
        Drive this instrument's isolated pipeline over a bar
        window. candles may be supplied directly (tests /
        replay) or fetched from the data_source (live).
        Returns a SymbolScanResult; data problems yield
        SKIPPED, engine failures propagate to the scanner,
        which isolates them per symbol.
        """
        if candles is None:
            candles = self._fetch(window)

            if candles is None:
                return self._skipped("NO_DATA_SOURCE")

        if not candles:
            return self._skipped("NO_DATA")

        self.reset()

        self.backtester.run(candles)

        return self._collect()

    # -------------------------------------------------

    def _skipped(self, reason):
        return SymbolScanResult(
            instrument=self.instrument,
            symbol=self.symbol,
            status=ScanStatus.SKIPPED,
            error=reason,
        )

    # -------------------------------------------------

    def _collect(self):
        setups = tuple(self._setups)

        decisions = ()

        accepted = getattr(self.context, "decision", None)

        if accepted is not None and hasattr(
            accepted, "all"
        ):
            decisions = tuple(accepted.all() or ())

        orders = ()

        registry = getattr(
            self.context, "order_registry", None
        )

        if registry is not None and hasattr(
            registry, "all"
        ):
            orders = tuple(registry.all() or ())

        trades = ()

        if self.simulator is not None:
            trades = tuple(
                self.simulator.registry.all() or ()
            )

        return SymbolScanResult(
            instrument=self.instrument,
            symbol=self.symbol,
            status=ScanStatus.SUCCESS,
            setups=setups,
            decisions=decisions,
            orders=orders,
            trades=trades,
            pipeline=self,
        )