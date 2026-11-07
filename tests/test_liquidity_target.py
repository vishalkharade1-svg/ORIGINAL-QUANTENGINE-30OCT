from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.swing_engine import SwingEngine

from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine
from core.liquidity.liquidity_ranker import LiquidityRanker
from core.liquidity.liquidity_target_engine import LiquidityTargetEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    swing = SwingEngine(

        timeframe="1m"

    )

    registry = swing.scan(

        builder.series

    )

    pool_engine = LiquidityPoolEngine()

    buy, sell = pool_engine.update(

        registry

    )

    pools = buy + sell

    ranked = LiquidityRanker().rank(

        pools,

        builder.series,

    )

    current = builder.series[-1].close

    target = LiquidityTargetEngine().next_target(

        ranked,

        current,

    )

    print()

    print("=" * 70)

    print("NEXT LIQUIDITY TARGET")

    print("=" * 70)

    if target:

        print("Side        :", target.side)

        print("Price       :", target.price)

        print("Score       :", target.score)

        print("Probability :", target.probability)

        print("Distance    :", round(target.distance, 2))

        print("Reason      :", target.reason)

    else:

        print("No target found.")

    loader.close()


if __name__ == "__main__":

    main()