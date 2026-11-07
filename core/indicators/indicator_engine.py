"""
====================================================

Indicator Engine

Canonical Institutional Indicator Engine

Owner of IndicatorCache.

Pipeline publishes ONLY the IndicatorCache
through PipelineContext.indicators.

====================================================
"""

from core.common.base_engine import BaseEngine
from core.indicators.indicator_cache import IndicatorCache
from core.common.logging_config import get_logger

log = get_logger(__name__)


class IndicatorEngine(BaseEngine):

    priority = 10

    dependencies = []

    enabled = True

    # -------------------------------------------------

    def __init__(self):

        super().__init__()

        self.cache = IndicatorCache()

        self.indicators = []

    # -------------------------------------------------

    def register(
        self,
        indicator,
    ):

        if indicator not in self.indicators:

            self.indicators.append(indicator)

    # -------------------------------------------------

    def unregister(
        self,
        indicator,
    ):

        if indicator in self.indicators:

            self.indicators.remove(indicator)

            self.cache.data.pop(
                indicator.name,
                None,
            )

    # -------------------------------------------------

    def calculate(
        self,
        bars,
    ):

        self.cache.clear()

        for indicator in self.indicators:

            values = indicator.calculate(bars)

            log.debug(
                "%s calculated: %d values, last5=%s",
                indicator.name,
                len(values),
                values[-5:] if len(values) >= 5 else values,
            )

            self.cache.set(
                indicator.name,
                values,
            )

        return self.cache

    # -------------------------------------------------

    def update(
        self,
        bars,
    ):

        if not bars:

            # No new data: leave the existing cache intact.
            # Feeding an empty window would recompute every
            # indicator to zero length, wipe the series, and
            # make latest() return None for a cache that
            # already holds valid values.
            return self.cache

        for indicator in self.indicators:

            values = indicator.update(bars)

            log.debug(
                "%s updated: bars=%d values=%d last=%s",
                indicator.name,
                len(bars),
                len(values),
                values[-1] if values else None,
            )

            self.cache.set(
                indicator.name,
                values,
            )

        log.debug(
            "Indicator cache updated: keys=%s",
            list(self.cache.data.keys()),
        )

        return self.cache

    # -------------------------------------------------

    def analyze(
        self,
        context,
    ):
        """
        Calculate every registered indicator and publish
        the IndicatorCache into the PipelineContext.

        IndicatorEngine owns the cache. InstitutionalPipeline
        drives the engine directly through update()/calculate()
        and publishes the shared cache itself, so analyze() is
        normally NOT reached through the engine registry.

        If analyze() is still invoked (an IndicatorEngine was
        accidentally registered into the engine list), it MUST
        converge on the exact same shared cache instead of
        publishing a fresh or empty one -- otherwise
        context.indicators silently detaches from
        IndicatorEngine.cache and downstream engines all see an
        empty key set (the historical "Cache keys = []" bug).
        """

        if not self.indicators:

            log.error(
                "IndicatorEngine.analyze() called with no "
                "registered indicators. Refusing to publish an "
                "empty/detached cache -- register indicators "
                "first (InstitutionalPipeline does this "
                "automatically)."
            )

            return None

        cache = self.update(
            list(context.candles),
        )

        context.indicators = self.cache

        return cache

    # -------------------------------------------------

    def latest(
        self,
        name,
    ):

        return self.cache.latest(name)

    # -------------------------------------------------

    def validate(
        self,
        context,
    ):

        return context.candle_count > 0

    # -------------------------------------------------

    def reset(
        self,
    ):

        for indicator in self.indicators:

            indicator.clear()

        self.cache.clear()