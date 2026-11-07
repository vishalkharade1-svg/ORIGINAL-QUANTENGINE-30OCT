from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.swing_engine import SwingEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    engine = SwingEngine(

        timeframe="1m",

    )

    registry = engine.scan(

        builder.history,

    )

    print()

    print("=" * 70)

    print("INSTITUTIONAL SWINGS")

    print("=" * 70)

    for swing in registry.all()[-30:]:

        print(

            f"{swing.kind:<5}",

            f"{swing.price:<12.2f}",

            f"Score={swing.score:>5.1f}",

            f"Inst={swing.institutional}",

        )

    print()

    print("=" * 70)

    print("SUMMARY")

    print("=" * 70)

    print("Total Swings       :", len(registry))

    print("Institutional      :", len(registry.institutional()))
    print("Major             :", len(registry.majors()))

    loader.close()


if __name__ == "__main__":

    main()