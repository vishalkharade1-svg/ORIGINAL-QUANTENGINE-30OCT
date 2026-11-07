"""
====================================================

QuantEngine

Institutional Liquidity Ranker

====================================================
"""

from core.liquidity.liquidity_score import LiquidityScore


class LiquidityRanker:

    def __init__(self):

        self.scorer = LiquidityScore()

    # ==================================================

    def rank(

        self,

        pools,

        bars,

    ):

        if not pools or not bars:

            return []

        current_price = bars[-1].close

        ranked = []

        for pool in pools:

            self.scorer.calculate(

                pool,

                bars,

                current_price,

            )

            ranked.append(pool)

        ranked.sort(

            key=lambda pool: (

                pool.score,

                getattr(

                    pool,

                    "strength",

                    0.0,

                ),

                pool.touches,

            ),

            reverse=True,

        )

        return ranked

    # ==================================================

    def best(

        self,

        pools,

        bars,

    ):

        ranked = self.rank(

            pools,

            bars,

        )

        if not ranked:

            return None

        return ranked[0]

    # ==================================================

    def top(

        self,

        pools,

        bars,

        limit=5,

    ):

        return self.rank(

            pools,

            bars,

        )[:limit]