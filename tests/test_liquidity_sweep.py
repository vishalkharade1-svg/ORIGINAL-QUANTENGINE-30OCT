from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.pipeline.pipeline_context import PipelineContext

from core.market_structure.swing_engine import SwingEngine

from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine
from core.liquidity.liquidity_sweep_engine import LiquiditySweepEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    context = PipelineContext()

    for candle in builder.history:

        context.add_candle(candle)

    swing = SwingEngine()

    swing.analyze(context)

    pool_engine = LiquidityPoolEngine()

    pool_engine.analyze(context)

    pools = context.liquidity or []

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

    sweep_engine = LiquiditySweepEngine()

    sweeps = sweep_engine.update(

        list(builder.history),

        buy_pools,

        sell_pools,

    )

    print()

    print("=" * 70)
    print("LIQUIDITY SWEEPS")
    print("=" * 70)

    if not sweeps:

        print("No sweeps detected.")

    for sweep in sweeps:

        print()

        print("Side       :", sweep.side)
        print("Pool       :", sweep.pool_price)
        print("Sweep      :", sweep.sweep_price)
        print("Rejection  :", sweep.rejection_price)
        print("Strength   :", sweep.strength)
        print("Confirmed  :", sweep.confirmed)

    loader.close()


if __name__ == "__main__":

    main()