from core.warmup import WarmupEngine
from data.candle_builder import CandleBuilder
from indicators.manager import IndicatorManager

builder = CandleBuilder()
manager = IndicatorManager()

warmup = WarmupEngine(builder, manager)

warmup.run()

print()

print("History :", builder.count())

print("Indicators Ready :", manager.ready())

print()

print(manager.snapshot())