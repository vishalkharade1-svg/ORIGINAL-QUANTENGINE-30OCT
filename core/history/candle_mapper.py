"""
====================================================

Institutional Candle Mapper

====================================================
"""

from core.history.candle import Candle


class CandleMapper:

    # -------------------------------------------------

    def map(self, data):

        return Candle(

            timestamp=int(data["time"]),

            open=float(data["open"]),

            high=float(data["high"]),

            low=float(data["low"]),

            close=float(data["close"]),

            volume=float(data["volume"]),

        )

    # -------------------------------------------------

    def map_all(self, candles):

        return [

            self.map(candle)

            for candle in candles

        ]

    # -------------------------------------------------

    def dataframe_to_candles(self, df):

        candles = []

        for row in df.itertuples(index=False):

            candles.append(

                Candle(

                    timestamp=int(row.timestamp),

                    open=float(row.open),

                    high=float(row.high),

                    low=float(row.low),

                    close=float(row.close),

                    volume=float(row.volume),

                )

            )

        return candles