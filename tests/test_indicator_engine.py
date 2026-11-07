from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.indicators.indicator_engine import IndicatorEngine

from core.indicators.sma import SMA
from core.indicators.ema import EMA
from core.indicators.atr import ATR
from core.indicators.adx import ADX
from core.indicators.rsi import RSI


def main():

    loader = HistoricalLoader()

    builder = CandleBuilder()

    history = loader.candles(

        settings.SYMBOLS[0]

    )

    builder.load_history(

        list(reversed(history["result"]))

    )

    engine = IndicatorEngine()

    engine.register(SMA(20))
    engine.register(SMA(50))
    engine.register(SMA(200))

    engine.register(EMA(20))
    engine.register(EMA(50))
    engine.register(EMA(200))

    engine.register(ATR(14))
    engine.register(ADX(14))
    engine.register(RSI(14))

    cache = engine.calculate(

        builder.series

    )

    print()

    print("=" * 70)
    print("INSTITUTIONAL INDICATORS")
    print("=" * 70)

    print(f"SMA20   : {cache.latest('SMA_20')}")
    print(f"SMA50   : {cache.latest('SMA_50')}")
    print(f"SMA200  : {cache.latest('SMA_200')}")

    print()

    print(f"EMA20   : {cache.latest('EMA_20')}")
    print(f"EMA50   : {cache.latest('EMA_50')}")
    print(f"EMA200  : {cache.latest('EMA_200')}")

    print()

    print(f"ATR14   : {cache.latest('ATR_14')}")
    print(f"ADX14   : {cache.latest('ADX_14')}")
    print(f"RSI14   : {cache.latest('RSI_14')}")

    loader.close()


if __name__ == "__main__":

    main()