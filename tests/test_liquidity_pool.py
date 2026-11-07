from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.swing_engine import SwingEngine
from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine


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

    engine = LiquidityPoolEngine()

    buy, sell = engine.update(

        registry

    )

    print()

    print("=" * 70)
    print("BUY SIDE LIQUIDITY")
    print("=" * 70)

    for pool in buy:

        print(

            f"{pool.price:.2f}",

            "Touches:",

            pool.touches,

        )

    print()

    print("=" * 70)
    print("SELL SIDE LIQUIDITY")
    print("=" * 70)

    for pool in sell:

        print(

            f"{pool.price:.2f}",

            "Touches:",

            pool.touches,

        )

    loader.close()


if __name__ == "__main__":

    main()