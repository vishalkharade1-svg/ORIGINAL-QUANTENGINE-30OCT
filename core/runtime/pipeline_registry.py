"""
====================================================

QuantEngine

Pipeline Registry

Phase 6E -- Real-time integration (paper mode only).

Stable per-instrument pipeline ownership keyed by the
canonical instrument identity -- (exchange, instrument_id)
-- never by array position or subscription order. The
universe diff is ADD / RETAIN / RETIRE:

    Universe pass 1: BTC, ETH
    Universe pass 2: BTC, SOL

        BTC  -> RETAIN  (same SymbolPipeline object keeps its
                         real-time structural state)
        ETH  -> RETIRE  (moves to the retired snapshot; no
                         longer receives candles)
        SOL  -> ADD     (a brand-new isolated pipeline)

SymbolPipelines are built through the injectable world
factory (production = InstitutionalPipeline), so a retained
instrument never rebuilds its world across refreshes.
====================================================
"""

from core.scanning.symbol_pipeline import SymbolPipeline


def instrument_identity_key(exchange, instrument_id):
    """(exchange, instrument_id) tuple -- the stable identity the
    candle router and every downstream registry bind to."""

    return (str(exchange or ""), str(instrument_id or ""))


class PipelineRegistry:

    def __init__(
        self,
        world_factory=None,
        timeframe="1m",
        strategy="",
        data_source=None,
    ):

        self._world_factory = world_factory
        self.timeframe = timeframe
        self.strategy = strategy
        self.data_source = data_source

        self._pipelines = {}
        self._retired = {}

    # --------------------------------------------------

    @property
    def pipelines(self):

        return self._pipelines

    @property
    def retired_pipelines(self):

        return self._retired

    @property
    def keys(self):

        return tuple(sorted(self._pipelines))

    @property
    def count(self):

        return len(self._pipelines)

    # --------------------------------------------------

    def get(self, key, default=None):

        return self._pipelines.get(key, default)

    def get_retired(self, key, default=None):

        return self._retired.get(key, default)

    # --------------------------------------------------

    def pipeline_for(self, instrument):
        """Build + reset a fresh isolated SymbolPipeline for one
        instrument (world_factory injectable; default =
        InstitutionalPipeline). reset() primes context / market /
        world / bus / simulator / backtester exactly once."""

        pipeline = SymbolPipeline(
            instrument=instrument,
            timeframe=self.timeframe,
            strategy=self.strategy,
            data_source=self.data_source,
            world_factory=self._world_factory,
        )

        pipeline.reset()

        return pipeline

    # --------------------------------------------------

    def reconcile(self, instruments):
        """Diff the eligible-instrument cut against the owned
        pipelines: in-place RETAIN, RETIRE the absent, ADD the new.
        Returns {"added": [...], "retained": [...],
        "retired": [...]} keyed by instrument identity."""

        desired = {}

        for instrument in instruments:

            exchange = getattr(instrument, "exchange", "") or ""
            instrument_id = getattr(instrument, "instrument_id", "") or ""

            if not instrument_id:
                continue

            key = instrument_identity_key(exchange, instrument_id)
            desired[key] = instrument

        added = []
        retained = []
        retired = []

        for key in list(self._pipelines):

            if key not in desired:

                retired.append(key)
                self._retired[key] = self._pipelines.pop(key)

        for key, instrument in desired.items():

            if key in self._pipelines:

                retained.append(key)
                continue

            self._pipelines[key] = self.pipeline_for(instrument)
            added.append(key)

        return {
            "added": added,
            "retained": retained,
            "retired": retired,
        }