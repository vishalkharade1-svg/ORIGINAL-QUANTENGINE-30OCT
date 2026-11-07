"""
====================================================

Simple Moving Average

Stateful Version

====================================================
"""

from core.indicators.indicator import Indicator


class SMA(Indicator):

    def __init__(self, period):

        super().__init__(f"SMA_{period}")

        self.period = period

        self._rolling_sum = 0.0

    # -------------------------------------------------

    def calculate(self, bars):

        self.clear()

        self._rolling_sum = 0.0

        closes = [b.close for b in bars]

        for i, close in enumerate(closes):

            self._rolling_sum += close

            if i >= self.period:

                self._rolling_sum -= closes[i - self.period]

            if i + 1 < self.period:

                self.values.append(None)

            else:

                self.values.append(

                    self._rolling_sum / self.period

                )

        return self.values

    # -------------------------------------------------

    def update(self, bars):

        # Recompute from the full window, exactly like EMA/ATR/
        # ADX/RSI. The previous append-only version left
        # `values` growing and misaligned with `bars` across
        # repeated update() calls.
        return self.calculate(bars)