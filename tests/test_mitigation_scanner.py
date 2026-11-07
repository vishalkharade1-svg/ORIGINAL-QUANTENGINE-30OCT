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

from core.mitigation.mitigation_scanner import MitigationScanner


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
    # Displacement
    # -------------------------------------------------

    displacement_registry = DisplacementScanner().scan(
        bars,
        atr,
    )

    # -------------------------------------------------
    # FVG
    # -------------------------------------------------

    fvg_registry = FVGScanner().scan(
        bars,
        displacement_registry,
    )

    # -------------------------------------------------
    # IMPORTANT:
    # Build Order Blocks BEFORE updating FVG lifecycle
    # -------------------------------------------------

    order_block_registry = OrderBlockScanner().scan(
        bars,
        displacement_registry,
        fvg_registry,
    )

    # -------------------------------------------------
    # Now update lifecycles
    # -------------------------------------------------

    FVGLifecycle().update(
        bars,
        fvg_registry,
    )

    OrderBlockLifecycle().update(
        bars,
        order_block_registry,
    )

    # -------------------------------------------------
    # Breakers
    # -------------------------------------------------

    breaker_registry = BreakerScanner().scan(
        order_block_registry,
    )

    # -------------------------------------------------
    # Mitigation
    # -------------------------------------------------

    mitigation_registry = MitigationScanner().scan(
        order_block_registry,
    )

    # -------------------------------------------------

    print()
    print("=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)

    print("Displacements :", displacement_registry.count())
    print("FVGs          :", fvg_registry.count())
    print("Order Blocks  :", order_block_registry.count())
    print("Breakers      :", breaker_registry.count())
    print("Mitigations   :", mitigation_registry.count())

    print()

    print("=" * 70)
    print("MITIGATION BLOCKS")
    print("=" * 70)

    if mitigation_registry.count() == 0:

        print("No mitigation blocks detected.")

    else:

        for block in mitigation_registry.all():

            print()

            print("Direction   :", block.direction)
            print("High        :", block.high)
            print("Low         :", block.low)
            print("Score       :", block.score)
            print("Source OB   :", block.source_order_block)
            print("Active      :", block.active)
            print("Invalidated :", block.invalidated)

    loader.close()


if __name__ == "__main__":
    main()