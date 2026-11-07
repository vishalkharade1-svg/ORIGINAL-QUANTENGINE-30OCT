"""
====================================================

Indicator Base Class

====================================================
"""

from abc import ABC
from abc import abstractmethod


class Indicator(ABC):

    def __init__(self, name):

        self.name = name

        self.values = []

        # Incremental update bookkeeping. `_n` is the number of
        # bars represented by the last update() call and
        # `_last_ts` is that window's newest bar timestamp. They
        # let update() detect a strict continuation pass (the
        # pipeline feed: one new bar per candle, growing then
        # sliding at the deque cap) and append only the newest
        # value instead of recomputing the whole window.
        self._n = 0

        self._last_ts = None

    # -------------------------------------------------

    def _is_continuation(self, bars):
        """
        True when `bars` is a strict one-bar continuation of the
        window last fed to update(): either the same window plus
        one new bar (growth) or the window slid by one at the
        deque cap (the bar that was newest is now second-newest).
        Any other input -- a fresh engine, a different window, a
        re-feed of the same window -- is NOT a continuation and
        must take the full recompute path, preserving the classic
        update() == calculate() contract for arbitrary callers.
        """

        n = len(bars)

        if n == 0:

            return False

        if self._n == 0:

            return n == 1

        if n == self._n + 1:

            return n == 1 or bars[-2].timestamp == self._last_ts

        if n == self._n and n >= 2:

            return (
                bars[-2].timestamp == self._last_ts
                and bars[-1].timestamp != self._last_ts
            )

        return False

    # -------------------------------------------------

    @abstractmethod
    def calculate(self, bars):

        pass

    # -------------------------------------------------

    @abstractmethod
    def update(self, bars):

        pass

    # -------------------------------------------------

    def latest(self):

        if self.values:

            return self.values[-1]

        return None

    # -------------------------------------------------

    def clear(self):

        self.values.clear()

        self._n = 0

        self._last_ts = None