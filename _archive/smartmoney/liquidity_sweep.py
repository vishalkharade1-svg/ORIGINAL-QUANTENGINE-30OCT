"""
====================================================

QuantEngine

Build : 4.7
Module : Liquidity Sweep Detector

====================================================
"""

from dataclasses import dataclass


@dataclass
class LiquiditySweep:

    direction: str

    sweep_price: float

    candle_timestamp: int

    liquidity_price: float


class LiquiditySweepDetector:

    def detect(self, bars, liquidity):

        events = []

        candles = bars.candles

        for candle in candles:

            for zone in liquidity:

                # Buy-side sweep
                if zone.type == "EQH":

                    if (
                        candle.high > zone.price
                        and candle.close < zone.price
                    ):

                        events.append(

                            LiquiditySweep(

                                direction="BUY_SIDE",

                                sweep_price=candle.high,

                                candle_timestamp=candle.timestamp,

                                liquidity_price=zone.price,

                            )

                        )

                # Sell-side sweep
                elif zone.type == "EQL":

                    if (
                        candle.low < zone.price
                        and candle.close > zone.price
                    ):

                        events.append(

                            LiquiditySweep(

                                direction="SELL_SIDE",

                                sweep_price=candle.low,

                                candle_timestamp=candle.timestamp,

                                liquidity_price=zone.price,

                            )

                        )

        return events