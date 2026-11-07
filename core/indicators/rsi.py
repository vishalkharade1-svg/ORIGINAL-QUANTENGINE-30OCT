"""
====================================================

Institutional RSI

Wilder RSI

====================================================
"""

from core.indicators.indicator import Indicator


class RSI(Indicator):

    def __init__(self, period=14):

        super().__init__(f"RSI_{period}")

        self.period = period

        # Incremental state: full-history closes, gains, losses
        # and the current Wilder averages. Carried across
        # update() calls so each candle appends one value
        # instead of rescanning the whole window.
        self._closes = []
        self._gains = []
        self._losses = []
        self._avg_gain = None
        self._avg_loss = None

    # -------------------------------------------------

    def clear(self):

        super().clear()

        self._closes = []
        self._gains = []
        self._losses = []
        self._avg_gain = None
        self._avg_loss = None

    # -------------------------------------------------

    def calculate(self, bars):

        self.clear()

        closes = [b.close for b in bars]

        if len(closes) < self.period + 1:

            self.values = [None] * len(closes)

            self._closes = closes
            return self.values

        gains = []
        losses = []

        for i in range(1, len(closes)):

            diff = closes[i] - closes[i - 1]

            gains.append(max(diff, 0))

            losses.append(max(-diff, 0))

        self.values = [None] * len(closes)

        avg_gain = sum(gains[:self.period]) / self.period
        avg_loss = sum(losses[:self.period]) / self.period

        if avg_loss == 0:

            self.values[self.period] = 100

        else:

            rs = avg_gain / avg_loss

            self.values[self.period] = 100 - (100 / (1 + rs))

        for i in range(self.period + 1, len(closes)):

            avg_gain = (

                (avg_gain * (self.period - 1))

                + gains[i - 1]

            ) / self.period

            avg_loss = (

                (avg_loss * (self.period - 1))

                + losses[i - 1]

            ) / self.period

            if avg_loss == 0:

                rsi = 100

            else:

                rs = avg_gain / avg_loss

                rsi = 100 - (100 / (1 + rs))

            self.values[i] = rsi

        # Rebuild the incremental state so a subsequent
        # update() continuation picks up from exactly this
        # recomputation.
        self._closes = closes
        self._gains = gains
        self._losses = losses
        self._avg_gain = avg_gain
        self._avg_loss = avg_loss

        return self.values

    # -------------------------------------------------

    def _rsi_value(self, avg_gain, avg_loss):

        if avg_loss == 0:

            return 100

        rs = avg_gain / avg_loss

        return 100 - (100 / (1 + rs))

    # -------------------------------------------------

    def update(self, bars):

        if not self._is_continuation(bars):

            return self.calculate(bars)

        self._closes.append(bars[-1].close)

        k = len(self._closes) - 1

        if k >= 1:

            diff = self._closes[k] - self._closes[k - 1]

            self._gains.append(max(diff, 0))

            self._losses.append(max(-diff, 0))

        if k < self.period:

            value = None

        elif k == self.period:

            self._avg_gain = sum(self._gains[:self.period]) / self.period
            self._avg_loss = sum(self._losses[:self.period]) / self.period

            value = self._rsi_value(self._avg_gain, self._avg_loss)

        else:

            self._avg_gain = (

                (self._avg_gain * (self.period - 1))

                + self._gains[k - 1]

            ) / self.period

            self._avg_loss = (

                (self._avg_loss * (self.period - 1))

                + self._losses[k - 1]

            ) / self.period

            value = self._rsi_value(self._avg_gain, self._avg_loss)

        self.values.append(value)

        while len(self.values) > len(bars):

            self.values.pop(0)

        self._n = len(bars)

        self._last_ts = bars[-1].timestamp

        return self.values