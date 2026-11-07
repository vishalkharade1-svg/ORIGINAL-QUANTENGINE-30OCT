from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.atr import ATR

from core.displacement.displacement_scanner import DisplacementScanner
from core.fvg.fvg_scanner import FVGScanner


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    bars = list(builder.history)

    # -------------------------------------------------

    indicators = IndicatorEngine()

    indicators.register(

        ATR(14)

    )

    cache = indicators.calculate(

        bars

    )

    atr = cache.latest(

        "ATR_14"

    )

    # -------------------------------------------------

    displacement_registry = DisplacementScanner().scan(

        bars,

        atr,

    )

    # -------------------------------------------------

    registry = FVGScanner().scan(

        bars,

        displacement_registry,

    )

    # -------------------------------------------------

    print()

    print("=" * 70)
    print("FAIR VALUE GAPS")
    print("=" * 70)

    print("Total :", registry.count())

    print()

    for gap in registry.last(10):

        print()

        print("Direction :", gap.direction)
        print("Upper     :", round(gap.upper, 2))
        print("Lower     :", round(gap.lower, 2))
        print("Size      :", round(gap.size, 2))
        print("Score     :", round(gap.score, 2))
        print("Active    :", gap.active)

    loader.close()


if __name__ == "__main__":

    main()