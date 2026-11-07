"""
====================================================

QuantEngine

Timeframe Aggregator

Aggregates Candle objects into higher timeframes.

====================================================
"""

from core.history.candle import Candle


class TimeframeAggregator:

    # -------------------------------------------------

    def aggregate(

        self,

        candles: list[Candle],

        timeframe: str,

    ) -> list[Candle]:

        if not candles:

            return []

        seconds = self._seconds(timeframe)

        result = []

        bucket = []

        current_bucket = None

        for candle in candles:

            bucket_start = (

                candle.timestamp // seconds

            ) * seconds

            if current_bucket is None:

                current_bucket = bucket_start

            if bucket_start != current_bucket:

                result.append(

                    self._merge(bucket)

                )

                bucket = []

                current_bucket = bucket_start

            bucket.append(candle)

        if bucket:

            result.append(

                self._merge(bucket)

            )

        return result

    # -------------------------------------------------

    def _merge(

        self,

        candles: list[Candle],

    ) -> Candle:

        return Candle(

            timestamp=candles[0].timestamp,

            open=candles[0].open,

            high=max(

                c.high

                for c in candles

            ),

            low=min(

                c.low

                for c in candles

            ),

            close=candles[-1].close,

            volume=sum(

                c.volume

                for c in candles

            ),

        )

    # -------------------------------------------------

    def _seconds(

        self,

        timeframe: str,

    ) -> int:

        tf = timeframe.lower()

        if tf.endswith("m"):

            return int(tf[:-1]) * 60

        if tf.endswith("h"):

            return int(tf[:-1]) * 3600

        if tf.endswith("d"):

            return int(tf[:-1]) * 86400

        if tf.endswith("w"):

            return int(tf[:-1]) * 604800

        raise ValueError(

            f"Unsupported timeframe: {timeframe}"

        )