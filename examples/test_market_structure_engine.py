from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.engine import MarketStructureEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    engine = MarketStructureEngine(

        timeframe="1m"

    )

    state = engine.update(

        builder.history

    )

    print()

    print("=" * 60)

    print("STRUCTURE EVENTS")

    print("=" * 60)

    for event in engine.structure.events[-20:]:

        print(

            f"{event.kind:<4}"

            f"{event.price:10.2f}"

            f"  {event.timestamp}"

        )

    print()

    print("=" * 60)

    print("BOS EVENTS")

    print("=" * 60)

    if engine.bos_engine.events:

        for bos in engine.bos_engine.events:

            print(

                f"{bos.direction:<8}"

                f"{bos.level:10.2f}"

                f"  {bos.timestamp}"

            )

    else:

        print("None")

    print()

    print("=" * 60)

    print("CHOCH EVENTS")

    print("=" * 60)

    if engine.choch_engine.events:

        for choch in engine.choch_engine.events:

            print(

                f"{choch.direction:<8}"

                f"{choch.level:10.2f}"

                f"  {choch.timestamp}"

            )

    else:

        print("None")

    print()

    print("=" * 60)

    print("MARKET STRUCTURE STATE")

    print("=" * 60)

    print(f"Trend            : {state.trend}")
    print(f"Internal Trend   : {state.internal_trend}")
    print(f"External Trend   : {state.external_trend}")
    print(f"Structure        : {state.structure}")
    print(f"Major High       : {state.major_high:.2f}")
    print(f"Major Low        : {state.major_low:.2f}")
    print(f"BOS              : {state.bos}")
    print(f"CHoCH            : {state.choch}")
    print(f"Signals          : {state.signals}")
    print(f"Score            : {state.score:.2f}")

    loader.close()


if __name__ == "__main__":

    main()