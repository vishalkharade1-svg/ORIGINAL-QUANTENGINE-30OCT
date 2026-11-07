"""
====================================================

QuantEngine

Build : 4.9

Institutional Order Block Detector

====================================================
"""

from smartmoney.order_block import OrderBlock


class OrderBlockDetector:

    def detect(self, bars, bos_events):

        candles = bars.candles

        blocks = []

        for bos in bos_events:

            candidate = None

            candidate_index = None

            for i, candle in enumerate(candles):

                if candle.timestamp >= bos.timestamp:
                    break

                if bos.direction == "BULLISH":

                    # Last bearish candle
                    if candle.close < candle.open:

                        candidate = candle
                        candidate_index = i

                else:

                    # Last bullish candle
                    if candle.close > candle.open:

                        candidate = candle
                        candidate_index = i

            if candidate is None:
                continue

            blocks.append(

                OrderBlock(

                    direction=bos.direction,

                    high=candidate.high,

                    low=candidate.low,

                    timestamp=candidate.timestamp,

                )

            )

        return blocks