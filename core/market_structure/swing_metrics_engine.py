"""
====================================================

Institutional Swing Metrics Engine

====================================================
"""


class SwingMetricsEngine:

    def __init__(

        self,

        atr_period=14,

    ):

        self.atr_period = atr_period

    # =====================================================

    def analyze(

        self,

        bars,

        index,

    ):

        metrics = {}

        metrics["atr"] = self.atr(

            bars,

            index,

        )

        metrics["impulse"] = self.impulse(

            bars,

            index,

        )

        metrics["displacement"] = self.displacement(

            bars,

            index,

        )

        metrics["volume_ratio"] = self.volume_ratio(

            bars,

            index,

        )

        metrics["retracement"] = 0.0

        metrics["candle_quality"] = self.candle_quality(

            bars,

            index,

        )

        return metrics

    # =====================================================

    def atr(

        self,

        bars,

        index,

    ):

        if index < self.atr_period:

            return 0.0

        total = 0.0

        for i in range(

            index - self.atr_period + 1,

            index + 1,

        ):

            high = bars[i].high

            low = bars[i].low

            prev = bars[i - 1].close

            tr = max(

                high - low,

                abs(high - prev),

                abs(low - prev),

            )

            total += tr

        return total / self.atr_period

    # =====================================================

    def impulse(

        self,

        bars,

        index,

    ):

        atr = self.atr(

            bars,

            index,

        )

        if atr == 0:

            return 0.0

        return (

            bars[index].high -

            bars[index].low

        ) / atr

    # =====================================================

    def displacement(

        self,

        bars,

        index,

    ):

        body = abs(

            bars[index].close -

            bars[index].open

        )

        rng = (

            bars[index].high -

            bars[index].low

        )

        if rng == 0:

            return 0.0

        return body / rng

    # =====================================================

    def candle_quality(

        self,

        bars,

        index,

    ):

        candle = bars[index]

        rng = candle.high - candle.low

        if rng == 0:

            return 0.0

        upper = candle.high - max(

            candle.open,

            candle.close,

        )

        lower = min(

            candle.open,

            candle.close,

        ) - candle.low

        return 1.0 - (

            (upper + lower) / rng

        )

    # =====================================================

    def volume_ratio(

        self,

        bars,

        index,

        lookback=20,

    ):

        if not hasattr(

            bars[index],

            "volume",

        ):

            return 1.0

        start = max(

            0,

            index - lookback,

        )

        total = 0.0

        count = 0

        for i in range(

            start,

            index,

        ):

            total += bars[i].volume

            count += 1

        if count == 0:

            return 1.0

        avg = total / count

        if avg <= 0:

            return 1.0

        return bars[index].volume / avg