from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.swing_metrics import SwingMetrics


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    metrics = SwingMetrics()

    print()

    print("=" * 60)

    print("SWING METRICS")

    print("=" * 60)

    for index in [

        100,

        200,

        300,

        400,

    ]:

        result = metrics.calculate(

            builder.history,

            index,

        )

        print(

            index,

            result,

        )

    loader.close()


if __name__ == "__main__":

    main()