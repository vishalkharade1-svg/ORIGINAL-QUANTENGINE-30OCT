"""
====================================================

QuantEngine

Institutional Live Delta Provider

Consumes real exchange trade data.

====================================================
"""

from core.orderflow.delta import Delta
from core.orderflow.delta_provider import DeltaProvider


class LiveDeltaProvider(DeltaProvider):

    @property
    def name(self) -> str:

        return "Live"

    # -------------------------------------------------

    @property
    def live(self) -> bool:

        return True

    # -------------------------------------------------

    def calculate(

        self,

        trades,

    ) -> Delta:

        result = Delta()

        result.mode = "LIVE"

        if not trades:

            result.confidence = 0.0

            return result

        buy = 0.0

        sell = 0.0

        latest_timestamp = 0

        candle_index = 0

        timeframe = ""

        # -------------------------------------------------

        for trade in trades:

            latest_timestamp = getattr(

                trade,

                "timestamp",

                latest_timestamp,

            )

            candle_index = getattr(

                trade,

                "candle_index",

                candle_index,

            )

            timeframe = getattr(

                trade,

                "timeframe",

                timeframe,

            )

            quantity = getattr(

                trade,

                "quantity",

                0.0,

            )

            side = getattr(

                trade,

                "side",

                "",

            ).upper()

            if side == "BUY":

                buy += quantity

            elif side == "SELL":

                sell += quantity

        # -------------------------------------------------

        result.timestamp = latest_timestamp

        result.candle_index = candle_index

        result.timeframe = timeframe

        result.buy_volume = buy

        result.sell_volume = sell

        result.update_totals()

        result.cumulative_delta = result.delta

        result.buy_aggression = (

            buy / result.total_volume

            if result.total_volume > 0

            else 0.0

        )

        result.sell_aggression = (

            sell / result.total_volume

            if result.total_volume > 0

            else 0.0

        )

        result.imbalance = abs(

            result.delta_percent

        )

        result.confidence = 1.0

        result.metadata.update(

            {

                "method": "live_trades",

                "trade_count": len(trades),

            }

        )

        return result