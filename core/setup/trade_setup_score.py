"""
====================================================

Trade Setup Score

====================================================
"""


class TradeSetupScore:

    def score(

        self,

        order_block,

        trend,

        regime,

    ):

        score = 0

        score += order_block.score

        if trend.direction == order_block.direction:

            score += 25

        if regime.regime == "TRENDING":

            score += 25

        return min(

            100,

            score,

        )