from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.ema import EMA
from core.indicators.atr import ATR
from core.indicators.adx import ADX
from core.indicators.rsi import RSI

from core.market_structure.engine import MarketStructureEngine
from core.trend.trend_engine import TrendEngine
from core.regime.regime_engine import RegimeEngine

from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine
from core.liquidity.liquidity_ranker import LiquidityRanker
from core.liquidity.liquidity_target_engine import LiquidityTargetEngine

from core.confluence.confluence_engine import ConfluenceEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    indicators = IndicatorEngine()

    indicators.register(EMA(20))
    indicators.register(EMA(50))
    indicators.register(EMA(200))
    indicators.register(ATR(14))
    indicators.register(ADX(14))
    indicators.register(RSI(14))

    cache = indicators.calculate(

        builder.series

    )

    trend = TrendEngine().analyze(

        builder.series,

        cache,

    )

    structure = MarketStructureEngine(

        timeframe="1m"

    ).update(

        builder.series

    )

    regime = RegimeEngine().analyze(

        trend,

        structure,

        cache,

    )

    registry = MarketStructureEngine(

        timeframe="1m"

    ).swing.scan(

        builder.series

    )

    buy, sell = LiquidityPoolEngine().update(

        registry

    )

    pools = LiquidityRanker().rank(

        buy + sell,

        builder.series,

    )

    target = LiquidityTargetEngine().next_target(

        pools,

        builder.series[-1].close,

    )

    result = ConfluenceEngine().analyze(

        trend,

        regime,

        structure,

        target,

    )

    print()

    print("=" * 70)
    print("CONFLUENCE")
    print("=" * 70)

    print("Score :", result.score)

    print()

    for reason in result.reasons:

        print("-", reason)

    loader.close()


if __name__ == "__main__":

    main()