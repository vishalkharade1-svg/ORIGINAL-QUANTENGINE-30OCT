"""
====================================================

Historical Database Manager

====================================================
"""

from core.exchanges.delta.delta_history import DeltaHistory
from core.history.history_storage import HistoryStorage
from core.history.timeframe_aggregator import TimeframeAggregator
from core.history.candle_mapper import CandleMapper


class HistoryDatabase:

    def __init__(self):

        self.history = DeltaHistory()

        self.storage = HistoryStorage()

        self.aggregator = TimeframeAggregator()

        self.mapper = CandleMapper()

        self.cache = {}

    # -------------------------------------------------

    def update(

        self,

        symbol,

        days=30,

    ):

        candles = self.history.candles(

            symbol=symbol,

            resolution="1m",

            days=days,

        )

        self.storage.save(

            symbol,

            "1m",

            candles,

        )

        return len(candles)

    # -------------------------------------------------

    def get(

        self,

        symbol,

        timeframe="1m",

        days=30,

    ):

        key = (symbol, timeframe)

        if key in self.cache:

            return self.cache[key]

        if not self.storage.exists(

            symbol,

            "1m",

        ):

            self.update(

                symbol,

                days,

            )

        # ---------------------------------------------
        # Load DataFrame
        # ---------------------------------------------

        df = self.storage.load(

            symbol,

            "1m",

        )

        # ---------------------------------------------
        # Convert to Candle objects
        # ---------------------------------------------

        candles = self.mapper.dataframe_to_candles(

            df,

        )

        # ---------------------------------------------
        # Aggregate Candle objects
        # ---------------------------------------------

        if timeframe != "1m":

            candles = self.aggregator.aggregate(

                candles,

                timeframe,

            )

        self.cache[key] = candles

        return candles

    # -------------------------------------------------

    def clear_cache(self):

        self.cache.clear()