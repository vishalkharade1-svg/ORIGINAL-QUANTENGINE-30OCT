from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.atr import ATR

from core.displacement.displacement_scanner import DisplacementScanner
from core.fvg.fvg_scanner import FVGScanner
from core.order_blocks.order_block_scanner import OrderBlockScanner
from core.order_blocks.order_block_lifecycle import OrderBlockLifecycle


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(settings.SYMBOLS[0])

    builder.load_history(

        list(reversed(history["result"]))

    )

    bars = list(builder.history)

    engine = IndicatorEngine()

    engine.register(ATR(14))

    cache = engine.calculate(bars)

    atr = cache.latest("ATR_14")

    displacement = DisplacementScanner().scan(

        bars,

        atr,

    )

    fvg = FVGScanner().scan(

        bars,

        displacement,

    )

    order_blocks = OrderBlockScanner().scan(

        bars,

        displacement,

        fvg,

    )

    OrderBlockLifecycle().update(

        bars,

        order_blocks,

    )

    print()

    print("=" * 70)
    print("ORDER BLOCK LIFECYCLE")
    print("=" * 70)

    print("Active     :", len(order_blocks.active()))
    print("Mitigated  :", len(order_blocks.mitigated()))

    print()

    for block in order_blocks.all():

        print(

            block.direction,

            "Touches=", block.touches,

            "Active=", block.active,

            "Mitigated=", block.mitigated,

            "Score=", round(block.score, 2),

        )

    loader.close()


if __name__ == "__main__":

    main()