"""
====================================================

QuantEngine

Build : 4.8

Institutional Liquidity Pool Builder

====================================================
"""

from smartmoney.liquidity_pool import LiquidityPool


class LiquidityPoolBuilder:

    def __init__(self, tolerance=0.001):

        self.tolerance = tolerance

    def build(self, swings):

        pools = []

        for swing in swings:

            matched = False

            for pool in pools:

                if pool.type != swing.type:
                    continue

                average = (pool.price + swing.price) / 2

                if average == 0:
                    continue

                difference = abs(pool.price - swing.price)

                if difference / average <= self.tolerance:

                    pool.price = average

                    pool.touches += 1

                    pool.last_timestamp = swing.timestamp

                    matched = True

                    break

            if matched:
                continue

            pools.append(

                LiquidityPool(

                    type=swing.type,

                    price=swing.price,

                    first_timestamp=swing.timestamp,

                    last_timestamp=swing.timestamp,

                )

            )

        return pools