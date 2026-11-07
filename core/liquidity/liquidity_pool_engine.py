"""
====================================================

QuantEngine

Institutional Liquidity Pool Engine

Pipeline Native

Consumes:
    context.swings
    context.candles

Produces:
    context.liquidity

====================================================
"""

from core.common.base_engine import BaseEngine

from core.liquidity.liquidity_pool import LiquidityPool
from core.liquidity.liquidity_ranker import LiquidityRanker


class LiquidityPoolEngine(BaseEngine):

    priority = 200

    dependencies = [
        "SwingEngine",
    ]

    enabled = True

    def __init__(
        self,
        tolerance=0.0015,
        minimum_touches=2,
    ):

        super().__init__()

        self.tolerance = tolerance
        self.minimum_touches = minimum_touches

        self.buy_side = []
        self.sell_side = []

        self.ranker = LiquidityRanker()

    # ==================================================
    # Pipeline Entry
    # ==================================================

    def analyze(self, context):

        registry = context.swings

        if registry is None:

            context.liquidity = []

            return

        bars = list(context.candles)

        self.buy_side.clear()
        self.sell_side.clear()

        highs = registry.highs()
        lows = registry.lows()

        self.buy_side = self._build(
            highs,
            "BUY",
        )

        self.sell_side = self._build(
            lows,
            "SELL",
        )

        self.buy_side = self.ranker.rank(
            self.buy_side,
            bars,
        )

        self.sell_side = self.ranker.rank(
            self.sell_side,
            bars,
        )

        context.liquidity = self.buy_side + self.sell_side

    # ==================================================

    def _build(
        self,
        swings,
        side,
    ):

        pools = []

        used = set()

        for i, swing in enumerate(swings):

            if i in used:
                continue

            touches = 1

            members = [swing.id]

            first_timestamp = swing.timestamp
            last_timestamp = swing.timestamp

            total_price = swing.price
            count = 1

            strength = getattr(
                swing,
                "score",
                0.0,
            )

            for j in range(i + 1, len(swings)):

                if j in used:
                    continue

                other = swings[j]

                diff = abs(
                    other.price - swing.price
                )

                if diff <= swing.price * self.tolerance:

                    touches += 1

                    used.add(j)

                    members.append(other.id)

                    total_price += other.price
                    count += 1

                    last_timestamp = max(
                        last_timestamp,
                        other.timestamp,
                    )

                    strength = max(
                        strength,
                        getattr(
                            other,
                            "score",
                            0.0,
                        ),
                    )

            if touches < self.minimum_touches:
                continue

            pool = LiquidityPool(

                side=side,

                price=total_price / count,

                touches=touches,

                first_timestamp=first_timestamp,

                last_timestamp=last_timestamp,

            )

            pool.strength = strength
            pool.source_swings = members

            pools.append(pool)

        return pools

    # ==================================================

    def reset(self):

        self.buy_side.clear()
        self.sell_side.clear()