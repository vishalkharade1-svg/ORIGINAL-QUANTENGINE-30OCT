"""
====================================================

QuantEngine

Institutional Liquidity Sweep Engine

Consumes:
    PipelineContext.candles
    PipelineContext.liquidity

Produces:
    PipelineContext.liquidity_sweeps

====================================================
"""

from core.common.base_engine import BaseEngine

from core.liquidity.liquidity_sweep import LiquiditySweep


class LiquiditySweepEngine(BaseEngine):

    priority = 220

    dependencies = [
        "LiquidityPoolEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.sweeps = []

    # ==================================================
    # Pipeline Entry
    # ==================================================

    def analyze(

        self,

        context,

    ):

        pools = context.liquidity

        bars = list(context.candles)

        if not pools or not bars:

            context.liquidity_sweeps = []

            return

        buy_pools = [

            pool

            for pool in pools

            if pool.side == "BUY"

        ]

        sell_pools = [

            pool

            for pool in pools

            if pool.side == "SELL"

        ]

        context.liquidity_sweeps = self.update(

            bars,

            buy_pools,

            sell_pools,

        )

    # ==================================================
    # Standalone Analyzer
    # ==================================================

    def update(

        self,

        bars,

        buy_pools,

        sell_pools,

    ):

        self.sweeps.clear()

        if not bars:

            return self.sweeps

        latest = bars[-1]

        # -------------------------------------------------
        # BUY SIDE SWEEPS
        # -------------------------------------------------

        for pool in buy_pools:

            if not pool.active:

                continue

            if (

                latest.high > pool.price

                and latest.close < pool.price

            ):

                sweep = LiquiditySweep(

                    side="BUY",

                    timeframe=pool.timeframe,

                    pool_price=pool.price,

                    sweep_price=latest.high,

                    rejection_price=latest.close,

                    timestamp=latest.timestamp,

                    strength=pool.score,

                    probability=min(

                        99.0,

                        pool.score,

                    ),

                    confirmed=True,

                )

                sweep.pool_id = pool.id

                pool.mark_swept()

                self.sweeps.append(

                    sweep

                )

        # -------------------------------------------------
        # SELL SIDE SWEEPS
        # -------------------------------------------------

        for pool in sell_pools:

            if not pool.active:

                continue

            if (

                latest.low < pool.price

                and latest.close > pool.price

            ):

                sweep = LiquiditySweep(

                    side="SELL",

                    timeframe=pool.timeframe,

                    pool_price=pool.price,

                    sweep_price=latest.low,

                    rejection_price=latest.close,

                    timestamp=latest.timestamp,

                    strength=pool.score,

                    probability=min(

                        99.0,

                        pool.score,

                    ),

                    confirmed=True,

                )

                sweep.pool_id = pool.id

                pool.mark_swept()

                self.sweeps.append(

                    sweep

                )

        return self.sweeps

    # ==================================================

    def latest(self):

        if not self.sweeps:

            return None

        return self.sweeps[-1]

    # ==================================================

    def reset(self):

        self.sweeps.clear()