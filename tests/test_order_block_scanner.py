from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.atr import ATR

from core.displacement.displacement_scanner import DisplacementScanner
from core.fvg.fvg_scanner import FVGScanner
from core.order_blocks.order_block_scanner import OrderBlockScanner


def main():

    # -------------------------------------------------
    # Load Historical Data
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
    # Displacement Scan
    # -------------------------------------------------

    displacement_registry = DisplacementScanner().scan(

        bars,

        atr,

    )

    # -------------------------------------------------
    # Fair Value Gap Scan
    # -------------------------------------------------

    fvg_registry = FVGScanner().scan(

        bars,

        displacement_registry,

    )

    # -------------------------------------------------
    # Order Block Scan
    # -------------------------------------------------

    ob_registry = OrderBlockScanner().scan(

        bars,

        displacement_registry,

        fvg_registry,

    )

    # -------------------------------------------------
    # Results
    # -------------------------------------------------

    print()

    print("=" * 70)
    print("ORDER BLOCK SCANNER")
    print("=" * 70)

    print("Total Order Blocks :", ob_registry.count())
    print("Active Order Blocks:", len(ob_registry.active()))

    print()

    print("=" * 70)
    print("LAST 10 ORDER BLOCKS")
    print("=" * 70)

    active = ob_registry.active()

    if not active:

        print("No Institutional Order Blocks Found.")

    else:

        for block in active[-10:]:

            print()

            print("Direction             :", block.direction)
            print("High                  :", round(block.high, 2))
            print("Low                   :", round(block.low, 2))
            print("Open                  :", round(block.open, 2))
            print("Close                 :", round(block.close, 2))
            print("Strength              :", round(block.strength, 2))
            print("Score                 :", round(block.score, 2))
            print("Displacement Strength :", round(block.displacement_strength, 2))
            print("FVG Index             :", block.fvg_index)
            print("Mitigated             :", block.mitigated)
            print("Invalidated           :", block.invalidated)

    loader.close()


if __name__ == "__main__":

    main()