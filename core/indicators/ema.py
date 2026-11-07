"""
====================================================

Institutional EMA

====================================================
"""

from core.indicators.indicator import Indicator


class EMA(Indicator):

    def __init__(

        self,

        period,

    ):

        super().__init__(

            f"EMA_{period}"

        )

        self.period = period

        self.multiplier = 2 / (period + 1)

        # Incremental state: the full-history close series and
        # the previous EMA value. Carrying this forward across
        # update() calls turns the per-candle recompute into an
        # O(1) recursion, while calculate() rebuilds it fresh.
        self._closes = []

        self._prev = None

    def clear(self):

        super().clear()

        self._closes = []

        self._prev = None

    # ==================================================

    def calculate(

        self,

        bars,

    ):

        self.clear()

        closes = [

            b.close

            for b in bars

        ]

        ema = None

        for i, close in enumerate(closes):

            if i + 1 < self.period:

                self.values.append(None)

                continue

            if ema is None:

                window = closes[

                    i - self.period + 1:

                    i + 1

                ]

                ema = sum(window) / self.period

            else:

                ema = (

                    (close - ema)

                    * self.multiplier

                ) + ema

            self.values.append(ema)

        # Rebuild the incremental state so a subsequent
        # update() continuation picks up from exactly this
        # recomputation.
        self._closes = closes

        self._prev = ema

        return self.values

    # ==================================================

    def update(

        self,

        bars,

    ):

        if not self._is_continuation(bars):

            return self.calculate(bars)

        self._closes.append(bars[-1].close)

        k = len(self._closes) - 1

        if k + 1 < self.period:

            value = None

        elif self._prev is None:

            window = self._closes[

                k - self.period + 1:

                k + 1

            ]

            value = sum(window) / self.period

            self._prev = value

        else:

            value = (

                (self._closes[k] - self._prev)

                * self.multiplier

            ) + self._prev

            self._prev = value

        self.values.append(value)

        while len(self.values) > len(bars):

            self.values.pop(0)

        self._n = len(bars)

        self._last_ts = bars[-1].timestamp

        return self.values