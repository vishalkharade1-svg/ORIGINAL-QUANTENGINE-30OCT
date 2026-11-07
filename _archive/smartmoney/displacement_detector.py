"""
====================================================

QuantEngine

Build : 4.11

Displacement Detector

====================================================
"""

from smartmoney.displacement import Displacement


class DisplacementDetector:

    def __init__(self, multiplier=2.0):

        self.multiplier = multiplier

    def detect(self, bars):

        candles = bars.candles

        if len(candles) < 20:
            return []

        events = []

        ranges = []

        for candle in candles:

            ranges.append(candle.high - candle.low)

        for i in range(20, len(candles)):

            average = sum(ranges[i-20:i]) / 20

            candle = candles[i]

            current_range = candle.high - candle.low

            if current_range < average * self.multiplier:
                continue

            body = abs(candle.close - candle.open)

            direction = (
                "BULLISH"
                if candle.close > candle.open
                else "BEARISH"
            )

            events.append(

                Displacement(

                    direction=direction,

                    timestamp=candle.timestamp,

                    open=candle.open,

                    high=candle.high,

                    low=candle.low,

                    close=candle.close,

                    body=body,

                    range=current_range,

                )

            )

        return events