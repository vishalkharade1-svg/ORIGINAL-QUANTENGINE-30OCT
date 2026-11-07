"""
====================================================

QuantEngine

Build : 2.3
Module: EMA Engine

Calculates EMA values from completed candles.

====================================================
"""

from collections import deque


class EMA:

    def __init__(self, period: int):

        self.period = period

        self.multiplier = 2 / (period + 1)

        self.value = None

        self.history = deque(maxlen=200)

    def update(self, price: float):

        # First value
        if self.value is None:

            self.value = price

        else:

            self.value = (
                (price - self.value)
                * self.multiplier
                + self.value
            )

        self.history.append(self.value)

        return self.value

    def last(self):

        return self.value

    def ready(self):

        return len(self.history) >= self.period

    def reset(self):

        self.value = None

        self.history.clear()