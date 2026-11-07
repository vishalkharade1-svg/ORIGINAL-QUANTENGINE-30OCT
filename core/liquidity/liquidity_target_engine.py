"""
====================================================

QuantEngine

Institutional Liquidity Target Engine

Pipeline Native

Consumes:
    context.liquidity
    context.candles
    context.trend

Produces:
    context.liquidity_target

====================================================
"""

from core.common.base_engine import BaseEngine

from core.liquidity.liquidity_target import LiquidityTarget


class LiquidityTargetEngine(BaseEngine):

    priority = 210

    dependencies = [
        "LiquidityPoolEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

    # ==================================================
    # Pipeline Entry
    # ==================================================

    def analyze(self, context):

        pools = context.liquidity
        bars = list(context.candles)

        if not pools or not bars:

            context.liquidity_target = None
            return

        current_price = bars[-1].close

        # -------------------------------------------------
        # Wrong-side rejection
        #
        # A target is the liquidity the market is expected to
        # magnet toward, so it must sit on the SAME side as the
        # prevailing trend: a BULLISH trend targets BUY-side
        # liquidity ABOVE price, a BEARISH trend targets SELL-side
        # liquidity BELOW price. Without this gate the engine
        # could pick a counter-trend pool (e.g. a SELL-side target
        # while the trend is up), which the setup builder then had
        # to patch around per-order-block. RANGE / WARMUP / no
        # trend carry no directional conviction, so both sides are
        # still eligible there.
        # -------------------------------------------------

        direction = getattr(
            getattr(context, "trend", None),
            "direction",
            None,
        )

        if direction == "BULLISH":

            allowed_sides = ["BUY"]

        elif direction == "BEARISH":

            allowed_sides = ["SELL"]

        else:

            allowed_sides = ["BUY", "SELL"]

        candidates = []

        for pool in pools:

            if not pool.active:
                continue

            if pool.side not in allowed_sides:
                continue

            if pool.side == "BUY":

                if pool.price <= current_price:
                    continue

            else:

                if pool.price >= current_price:
                    continue

            candidates.append(pool)

        if not candidates:

            context.liquidity_target = None
            return

        candidates.sort(

            key=lambda pool: (

                pool.score,
                pool.strength,
                pool.touches,

            ),

            reverse=True,

        )

        best = candidates[0]

        distance = abs(
            best.price - current_price
        )

        probability = min(
            99.0,
            best.score,
        )

        target = LiquidityTarget(

            side=best.side,

            price=best.price,

            timeframe=best.timeframe,

            score=best.score,

            probability=probability,

            distance=distance,

            strength=best.strength,

            reason="Highest institutional liquidity score",

        )

        target.source_pool = best.id

        context.liquidity_target = target

    # ==================================================

    def reset(self):

        pass