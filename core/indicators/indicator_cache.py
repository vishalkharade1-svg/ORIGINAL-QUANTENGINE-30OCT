"""
====================================================

Indicator Cache

====================================================
"""


class IndicatorCache:
    """Shared per-pipeline indicator values.

    Phase 12 retention semantics (bounded by construction,
    pinned by tests/test_memory_bounds_12.py): keys are
    ONLY the indicator names the owning IndicatorEngine
    registered (a fixed set per pipeline -- nothing else
    may write here); each value series is trimmed to the
    trailing bar window, so memory is O(indicators x
    window), never O(candles). One cache per pipeline
    instance: multi-symbol runs own one cache per symbol
    pipeline, so symbols cannot grow each other's cache.
    """

    def __init__(self):

        self.data = {}

    # ---------------------------------------------

    def set(

        self,

        name,

        values,

    ):

        self.data[name] = values

    # ---------------------------------------------

    def get(

        self,

        name,

    ):

        return self.data.get(name)

    # ---------------------------------------------
    def latest(self, name):

        values = self.data.get(name)

        if not values:
            return None

        return values[-1]

    # ---------------------------------------------

    def clear(self):

        self.data.clear()