"""
====================================================

QuantEngine

Build : 4.2
Module : Swing Detector

Detects confirmed swing highs and lows.

====================================================
"""

from smartmoney.swing import Swing


class SwingDetector:

    def __init__(self, left=2, right=2):

        self.left = left
        self.right = right

    def detect(self, bars):

        swings = []

        highs = bars.high()
        lows = bars.low()

        candles = bars.candles

        start = self.left
        end = len(candles) - self.right

        for i in range(start, end):

            high = highs[i]

            if (
                high == max(highs[i-self.left:i+self.right+1])
            ):

                swings.append(
                    Swing(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=high,
                        type="HIGH",
                    )
                )

            low = lows[i]

            if (
                low == min(lows[i-self.left:i+self.right+1])
            ):

                swings.append(
                    Swing(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=low,
                        type="LOW",
                    )
                )

        return swings