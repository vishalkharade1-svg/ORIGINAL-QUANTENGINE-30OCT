"""
====================================================

QuantEngine

Institutional Replay Delta Provider

OHLCV-based Delta Estimation

====================================================
"""

from core.orderflow.delta import Delta
from core.orderflow.delta_provider import DeltaProvider


class ReplayDeltaProvider(DeltaProvider):

    @property
    def name(self) -> str:

        return "Replay"

    # -------------------------------------------------

    @property
    def live(self) -> bool:

        return False

    # -------------------------------------------------

    def calculate(

        self,

        candle,

    ) -> Delta:

        result = Delta(

            timestamp=candle.timestamp,

        )

        if hasattr(candle, "index"):

            result.candle_index = candle.index

        if hasattr(candle, "timeframe"):

            result.timeframe = candle.timeframe

        result.mode = "ESTIMATED"

        volume = getattr(

            candle,

            "volume",

            0.0,

        )

        result.total_volume = volume

        # ---------------------------------------------
        # Zero Range Candle
        # ---------------------------------------------

        candle_range = (

            candle.high

            - candle.low

        )

        if candle_range <= 0:

            result.buy_volume = volume * 0.5

            result.sell_volume = volume * 0.5

            result.confidence = 0.10

            result.update_totals()

            result.metadata["method"] = "zero_range"

            return result

        # ---------------------------------------------
        # Close Position
        # ---------------------------------------------

        close_strength = (

            (candle.close - candle.low)

            / candle_range

        )

        close_strength = max(

            0.0,

            min(

                close_strength,

                1.0,

            ),

        )

        buy_ratio = close_strength

        # ---------------------------------------------
        # Body Strength Adjustment
        # ---------------------------------------------

        body = abs(

            candle.close

            - candle.open

        )

        body_ratio = body / candle_range

        adjustment = body_ratio * 0.20

        if candle.close > candle.open:

            buy_ratio += adjustment

        elif candle.close < candle.open:

            buy_ratio -= adjustment

        buy_ratio = max(

            0.0,

            min(

                buy_ratio,

                1.0,

            ),

        )

        sell_ratio = 1.0 - buy_ratio

        # ---------------------------------------------
        # Volumes
        # ---------------------------------------------

        result.buy_volume = volume * buy_ratio

        result.sell_volume = volume * sell_ratio

        result.update_totals()

        # ---------------------------------------------
        # Confidence
        # ---------------------------------------------

        result.confidence = min(

            0.40

            + body_ratio * 0.40,

            0.80,

        )

        # ---------------------------------------------
        # Estimated Aggression
        # ---------------------------------------------

        result.buy_aggression = buy_ratio

        result.sell_aggression = sell_ratio

        result.imbalance = abs(

            result.delta_percent

        )

        # ---------------------------------------------
        # Metadata
        # ---------------------------------------------

        result.metadata.update(

            {

                "method": "ohlcv_estimation",

                "body_ratio": body_ratio,

                "close_strength": close_strength,

                "buy_ratio": buy_ratio,

                "sell_ratio": sell_ratio,

            }

        )

        return result