from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.atr import ATR

from core.displacement.displacement_scanner import DisplacementScanner
from core.fvg.fvg_scanner import FVGScanner
from core.fvg.fvg_lifecycle import FVGLifecycle

from core.order_blocks.order_block_scanner import OrderBlockScanner
from core.order_blocks.order_block_lifecycle import OrderBlockLifecycle

from core.breaker.breaker_scanner import BreakerScanner


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
    # Indicators
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
    # Displacement
    # -------------------------------------------------

    displacement_registry = DisplacementScanner().scan(

        bars,

        atr,

    )

    # -------------------------------------------------
    # Fair Value Gaps
    # -------------------------------------------------

    fvg_registry = FVGScanner().scan(

        bars,

        displacement_registry,

    )

    FVGLifecycle().update(

        bars,

        fvg_registry,

    )

    # -------------------------------------------------
    # Order Blocks
    # -------------------------------------------------

    order_block_registry = OrderBlockScanner().scan(

        bars,

        displacement_registry,

        fvg_registry,

    )

    OrderBlockLifecycle().update(

        bars,

        order_block_registry,

    )

    # -------------------------------------------------
    # Breaker Blocks
    # -------------------------------------------------

    breaker_registry = BreakerScanner().scan(

        order_block_registry,

    )

    # -------------------------------------------------
    # Results
    # -------------------------------------------------

    print()

    print("=" * 70)
    print("BREAKER BLOCK SCANNER")
    print("=" * 70)

    print("Total Breakers :", breaker_registry.count())
    print("Active         :", len(breaker_registry.active()))
    print("Invalidated    :", len(breaker_registry.invalidated()))

    print()

    print("=" * 70)
    print("BREAKER BLOCKS")
    print("=" * 70)

    if breaker_registry.count() == 0:

        print("No breaker blocks detected.")

    else:

        for breaker in breaker_registry.all():

            print()

            print("Direction      :", breaker.direction)
            print("High           :", round(breaker.high, 2))
            print("Low            :", round(breaker.low, 2))
            print("Score          :", round(breaker.score, 2))
            print("Source OB      :", breaker.source_order_block)
            print("Active         :", breaker.active)
            print("Invalidated    :", breaker.invalidated)

    loader.close()


if __name__ == "__main__":

    main()