"""
====================================================

Institutional ADX

True Wilder Average Directional Index

====================================================
"""

from core.indicators.indicator import Indicator


class ADX(Indicator):

    def __init__(self, period=14):

        super().__init__(f"ADX_{period}")

        self.period = period

        # Incremental state: full-history TR / +DM / -DM / DX
        # series plus the live Wilder rolling sums and smoothed
        # ADX. Carried across update() calls so one candle
        # appends one value instead of rescanning the window.
        self._tr = [0.0]
        self._plus_dm = [0.0]
        self._minus_dm = [0.0]
        self._dx = [None]
        self._tr14 = None
        self._plus14 = None
        self._minus14 = None
        self._adx = None

    # -------------------------------------------------

    def clear(self):

        super().clear()

        self._tr = [0.0]
        self._plus_dm = [0.0]
        self._minus_dm = [0.0]
        self._dx = [None]
        self._tr14 = None
        self._plus14 = None
        self._minus14 = None
        self._adx = None

    # -------------------------------------------------

    def calculate(self, bars):

        self.clear()

        n = len(bars)

        if n < self.period * 2:

            self.values = [None] * n
            return self.values

        tr = [0.0]
        plus_dm = [0.0]
        minus_dm = [0.0]

        # ---------------------------------------------
        # Raw TR / +DM / -DM
        # ---------------------------------------------

        for i in range(1, n):

            current = bars[i]
            previous = bars[i - 1]

            up_move = current.high - previous.high
            down_move = previous.low - current.low

            pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
            mdm = down_move if (down_move > up_move and down_move > 0) else 0.0

            true_range = max(

                current.high - current.low,

                abs(current.high - previous.close),

                abs(current.low - previous.close),

            )

            tr.append(true_range)
            plus_dm.append(pdm)
            minus_dm.append(mdm)

        # ---------------------------------------------
        # Wilder Initial Sums
        # ---------------------------------------------

        tr14 = sum(tr[1:self.period + 1])
        plus14 = sum(plus_dm[1:self.period + 1])
        minus14 = sum(minus_dm[1:self.period + 1])

        dx = [None] * n

        # ---------------------------------------------
        # DX Calculation
        # ---------------------------------------------

        for i in range(self.period, n):

            if i > self.period:

                tr14 = tr14 - (tr14 / self.period) + tr[i]
                plus14 = plus14 - (plus14 / self.period) + plus_dm[i]
                minus14 = minus14 - (minus14 / self.period) + minus_dm[i]

            if tr14 == 0:

                continue

            plus_di = 100 * plus14 / tr14
            minus_di = 100 * minus14 / tr14

            denom = plus_di + minus_di

            if denom == 0:

                continue

            dx[i] = 100 * abs(plus_di - minus_di) / denom

        # ---------------------------------------------
        # ADX (Wilder Smoothed DX)
        # ---------------------------------------------

        self.values = [None] * n

        start = self.period * 2 - 1

        first_dx = [

            d

            for d in dx[self.period:start + 1]

            if d is not None

        ]

        if len(first_dx) < self.period:

            self._tr = tr
            self._plus_dm = plus_dm
            self._minus_dm = minus_dm
            self._dx = dx
            self._tr14 = tr14
            self._plus14 = plus14
            self._minus14 = minus14
            self._adx = None
            return self.values

        adx = sum(first_dx) / self.period

        self.values[start] = adx

        for i in range(start + 1, n):

            if dx[i] is None:

                self.values[i] = adx

                continue

            adx = (

                (adx * (self.period - 1))

                + dx[i]

            ) / self.period

            self.values[i] = adx

        # Rebuild the incremental state so a subsequent
        # update() continuation picks up from exactly this
        # recomputation.
        self._tr = tr
        self._plus_dm = plus_dm
        self._minus_dm = minus_dm
        self._dx = dx
        self._tr14 = tr14
        self._plus14 = plus14
        self._minus14 = minus14
        self._adx = adx

        return self.values

    # -------------------------------------------------

    def _rolled_dx(self):

        if self._tr14 == 0:

            return None

        plus_di = 100 * self._plus14 / self._tr14
        minus_di = 100 * self._minus14 / self._tr14

        denom = plus_di + minus_di

        if denom == 0:

            return None

        return 100 * abs(plus_di - minus_di) / denom

    # -------------------------------------------------

    def update(self, bars):

        if not self._is_continuation(bars):

            return self.calculate(bars)

        current = bars[-1]
        first_ever = (
            self._n == 0
            and len(self._tr) == 1
            and self._last_ts is None
        )

        if first_ever:

            # Candle index 0 fills the pre-seeded placeholder
            # arrays (calculate() sizes tr/plus_dm/minus_dm with
            # a tr[0] = 0.0 dummy that all sums skip).
            self._tr[0] = current.high - current.low
            self._plus_dm[0] = 0.0
            self._minus_dm[0] = 0.0
            self._dx[0] = None
            k = 0

        else:

            k = len(self._tr)

            previous = bars[-2]

            up_move = current.high - previous.high
            down_move = previous.low - current.low

            pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
            mdm = down_move if (down_move > up_move and down_move > 0) else 0.0

            true_range = max(

                current.high - current.low,

                abs(current.high - previous.close),

                abs(current.low - previous.close),

            )

            self._tr.append(true_range)
            self._plus_dm.append(pdm)
            self._minus_dm.append(mdm)
            self._dx.append(None)

        n = len(self._tr)
        start = self.period * 2 - 1

        value = None

        if k == self.period:

            # Wilder initial sums, once.
            self._tr14 = sum(self._tr[1:self.period + 1])
            self._plus14 = sum(self._plus_dm[1:self.period + 1])
            self._minus14 = sum(self._minus_dm[1:self.period + 1])

        elif k > self.period:

            # Roll before computing DX at index k.
            self._tr14 = self._tr14 - (self._tr14 / self.period) + self._tr[-1]
            self._plus14 = self._plus14 - (self._plus14 / self.period) + self._plus_dm[-1]
            self._minus14 = self._minus14 - (self._minus14 / self.period) + self._minus_dm[-1]

        if k >= self.period and self._tr14 is not None:

            self._dx[-1] = self._rolled_dx()

        if k == start:

            first_dx = [

                d

                for d in self._dx[self.period:start + 1]

                if d is not None

            ]

            if len(first_dx) >= self.period:

                self._adx = sum(first_dx) / self.period
                value = self._adx

        elif k > start:

            # A failed seed (fewer than `period` non-None DX
            # bars in the seed window) leaves ADX undefined --
            # calculate() returns an all-None series in that
            # case, so the incremental path carries None instead
            # of recursing on a missing average.
            if self._dx[-1] is None or self._adx is None:

                value = self._adx

            else:

                self._adx = (
                    (self._adx * (self.period - 1))
                    + self._dx[-1]
                ) / self.period
                value = self._adx

        self.values.append(value)

        while len(self.values) > len(bars):

            self.values.pop(0)

        self._n = len(bars)

        self._last_ts = bars[-1].timestamp

        return self.values