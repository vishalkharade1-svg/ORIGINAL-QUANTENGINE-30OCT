from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.swing_engine import SwingEngine

from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine
from core.liquidity.liquidity_ranker import LiquidityRanker


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

    print()

    print("=" * 70)
    print("RANKED LIQUIDITY")
    print("=" * 70)

    for pool in ranked:

        print(

            f"{pool.side:4}",

            f"{pool.price:.2f}",

            f"Touches={pool.touches}",

            f"Score={pool.score:.2f}",

        )

    loader.close()


if __name__ == "__main__":

    main()