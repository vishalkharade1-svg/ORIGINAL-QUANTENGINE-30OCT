from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.atr import ATR

from core.displacement.displacement_scanner import DisplacementScanner


def main():

    # -------------------------------------------------
    # Load History
    # -------------------------------------------------

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
    # ATR
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
    # Scan
    # -------------------------------------------------

    scanner = DisplacementScanner()

    registry = scanner.scan(

        bars,

        atr,

    )

    # -------------------------------------------------
    # Output
    # -------------------------------------------------

    print()

    print("=" * 70)
    print("DISPLACEMENT SCANNER")
    print("=" * 70)

    print("Total Events :", len(registry.all()))
    print("Strong Events:", len(registry.strong()))

    print()

    print("=" * 70)
    print("LAST 10 STRONG DISPLACEMENTS")
    print("=" * 70)

    strong = registry.strong()

    if not strong:

        print("No strong displacement candles found.")

    else:

        for event in strong[-10:]:

            print()

            print("Time        :", event.timestamp)
            print("Direction   :", event.direction)
            print("Open        :", round(event.open, 2))
            print("High        :", round(event.high, 2))
            print("Low         :", round(event.low, 2))
            print("Close       :", round(event.close, 2))
            print("Body        :", round(event.body, 2))
            print("Range       :", round(event.candle_range, 2))
            print("ATR x       :", round(event.atr_multiple, 2))
            print("Body Ratio  :", round(event.body_ratio, 2))
            print("Score       :", round(event.score, 2))
            print("Grade       :", event.grade)
            print("Sweep       :", event.liquidity_sweep)
            print("Trend Align :", event.trend_alignment)

    loader.close()


if __name__ == "__main__":

    main()