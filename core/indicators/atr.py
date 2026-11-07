"""
====================================================

Average True Range

Institutional Version — Wilder RMA

TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
Initial ATR = SMA of first N TRs
Subsequent: ATR_t = ((ATR_{t-1} * (N-1)) + TR_t) / N

Deterministic, causal, batch==incremental.

====================================================
"""

from core.indicators.indicator import Indicator


class ATR(Indicator):

    def __init__(
        self,
        period=14,
    ):

        super().__init__(
            f"ATR_{period}"
        )

        self.period = period

        # Incremental state: full-history TR series, Wilder ATR
        # rolling value, and previous close for TR.
        self._trs = []

        self._atr = None

        self._prev_close = None

    def clear(self):

        super().clear()

        self._trs = []

        self._atr = None

        self._prev_close = None

    # --------------------------------------------------

    def calculate(
        self,
        bars,
    ):

        self.clear()

        if not bars:
            return self.values

        trs = []
        previous_close = None

        for bar in bars:

            if previous_close is None:
                tr = bar.high - bar.low
            else:
                tr = max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )

            trs.append(tr)
            previous_close = bar.close

        # Wilder ATR series
        atr_values = [None] * len(trs)

        if len(trs) >= self.period:
            # Seed: SMA of first N TRs
            seed = sum(trs[: self.period]) / self.period
            atr_values[self.period - 1] = seed
            prev_atr = seed

            for i in range(self.period, len(trs)):
                # Wilder RMA: ATR_t = ((ATR_{t-1}*(N-1)) + TR_t)/N
                prev_atr = ((prev_atr * (self.period - 1)) + trs[i]) / self.period
                atr_values[i] = prev_atr

        self.values = atr_values

        # Rebuild incremental state so update() continues deterministically
        self._trs = trs
        if self.values and self.values[-1] is not None:
            self._atr = self.values[-1]
        else:
            # If warmup not complete, atr is None but trs still needed;
            # _atr stays None until seed bar.
            # For edge where len(trs) >= period, _atr is last value.
            # For len(trs) < period, _atr remains None.
            self._atr = None
            # But if we have at least period TRs, seed exists
            for v in reversed(self.values):
                if v is not None:
                    self._atr = v
                    break

        self._prev_close = bars[-1].close if bars else None
        self._n = len(bars)
        self._last_ts = bars[-1].timestamp if bars else None

        return self.values

    # --------------------------------------------------

    def update(
        self,
        bars,
    ):

        if not self._is_continuation(bars):
            return self.calculate(bars)

        if not bars:
            return self.values

        current = bars[-1]

        if self._prev_close is None:
            tr = current.high - current.low
        else:
            prev_close = self._prev_close
            tr = max(
                current.high - current.low,
                abs(current.high - prev_close),
                abs(current.low - prev_close),
            )

        self._trs.append(tr)

        k = len(self._trs) - 1  # index of this bar in full history

        if k + 1 < self.period:
            value = None
        elif k + 1 == self.period:
            # Seed bar: SMA of first N TRs
            seed = sum(self._trs[: self.period]) / self.period
            value = seed
            self._atr = seed
        else:
            # Wilder recurrence
            # self._atr holds ATR_{k-1}
            if self._atr is None:
                # Should not happen if warmup logic above is correct,
                # but fallback to SMA of trailing window if state lost
                window = self._trs[k - self.period + 1 : k + 1]
                value = sum(window) / self.period
                self._atr = value
            else:
                value = ((self._atr * (self.period - 1)) + tr) / self.period
                self._atr = value

        self._prev_close = current.close

        self.values.append(value)

        while len(self.values) > len(bars):
            self.values.pop(0)

        self._n = len(bars)

        self._last_ts = bars[-1].timestamp

        return self.values
