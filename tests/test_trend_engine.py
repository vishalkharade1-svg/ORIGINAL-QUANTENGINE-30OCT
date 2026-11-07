from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine

from core.indicators.sma import SMA
from core.indicators.ema import EMA
from core.indicators.atr import ATR
from core.indicators.adx import ADX
from core.indicators.rsi import RSI

from core.trend.trend_engine import TrendEngine


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(
        settings.SYMBOLS[0]
    )

    builder.load_history(
        list(reversed(history["result"]))
    )

    indicator_engine = IndicatorEngine()

    indicator_engine.register(EMA(20))
    indicator_engine.register(EMA(50))
    indicator_engine.register(EMA(200))
    indicator_engine.register(SMA(20))
    indicator_engine.register(SMA(50))
    indicator_engine.register(SMA(200))
    indicator_engine.register(ATR(14))
    indicator_engine.register(ADX(14))
    indicator_engine.register(RSI(14))

    cache = indicator_engine.calculate(
        builder.series
    )

    trend = TrendEngine().analyze(
        builder.series,
        cache,
    )

    print()
    print("=" * 70)
    print("TREND ENGINE")
    print("=" * 70)

    print(f"Direction      : {trend.direction}")
    print(f"Regime         : {trend.regime}")
    print(f"Strength       : {trend.strength:.2f}")
    print(f"Confidence     : {trend.confidence:.2f}")
    print(f"EMA Alignment  : {trend.ema_alignment}")
    print(f"ADX Confirmed  : {trend.adx_confirmed}")
    print(f"Momentum       : {trend.momentum}")
    print(f"Score          : {trend.score:.2f}")

    loader.close()


if __name__ == "__main__":
    main()