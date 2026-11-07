"""
====================================================

QuantEngine

Build : 4.10

Fair Value Gap Detector

====================================================
"""

from smartmoney.fair_value_gap import FairValueGap


class FVGDetector:

    def detect(self, bars):

        candles = bars.candles

        gaps = []

        for i in range(2, len(candles)):

            c1 = candles[i - 2]
            c2 = candles[i - 1]
            c3 = candles[i]

            # Bullish FVG
            if c3.low > c1.high:

                gaps.append(

                    FairValueGap(

                        direction="BULLISH",

                        top=c3.low,

                        bottom=c1.high,

                        timestamp=c2.timestamp,

                    )

                )

            # Bearish FVG
            elif c3.high < c1.low:

                gaps.append(

                    FairValueGap(

                        direction="BEARISH",

                        top=c1.low,

                        bottom=c3.high,

                        timestamp=c2.timestamp,

                    )

                )

        return gaps