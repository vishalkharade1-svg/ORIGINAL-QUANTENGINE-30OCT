from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine

from core.indicators.ema import EMA
from core.indicators.atr import ATR
from core.indicators.adx import ADX
from core.indicators.rsi import RSI

from core.trend.trend_engine import TrendEngine
from core.market_structure.engine import MarketStructureEngine
from core.regime.regime_engine import RegimeEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    indicator = IndicatorEngine()

    indicator.register(EMA(20))
    indicator.register(EMA(50))
    indicator.register(EMA(200))

    indicator.register(ATR(14))
    indicator.register(ADX(14))
    indicator.register(RSI(14))

    cache = indicator.calculate(

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

    print()

    print("=" * 70)
    print("MARKET REGIME")
    print("=" * 70)

    print("Trend      :", regime.trend)
    print("Regime     :", regime.regime)
    print("Momentum   :", regime.momentum)
    print("Volatility :", regime.volatility)
    print("Score      :", regime.score)
    print("Confidence :", regime.confidence)

    loader.close()


if __name__ == "__main__":

    main()