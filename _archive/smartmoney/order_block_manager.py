"""
====================================================

QuantEngine

Build : 4.12

Order Block Manager

Tracks mitigation and invalidation.

====================================================
"""


class OrderBlockManager:

    def update(self, bars, blocks):

        candles = bars.candles

        for candle in candles:

            for block in blocks:

                if not block.active:
                    continue

                # Price touches block

                if (

                    candle.low <= block.high

                    and

                    candle.high >= block.low

                ):

                    block.touches += 1

                    block.mitigated = True

                    block.mitigation_timestamp = candle.timestamp

                # Bullish block invalidation

                if (

                    block.direction == "BULLISH"

                    and

                    candle.close < block.low

                ):

                    block.invalidated = True

                    block.active = False

                    block.invalidation_timestamp = candle.timestamp

                # Bearish block invalidation

                elif (

                    block.direction == "BEARISH"

                    and

                    candle.close > block.high

                ):

                    block.invalidated = True

                    block.active = False

                    block.invalidation_timestamp = candle.timestamp

        return blocks