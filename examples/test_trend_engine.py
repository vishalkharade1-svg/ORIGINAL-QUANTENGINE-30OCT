from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_structure.swing_engine import SwingEngine
from core.market_structure.swing_trend_engine import SwingStructureTrendEngine


loader = HistoricalLoader()

builder = CandleBuilder()

history = loader.candles(settings.SYMBOLS[0])

builder.load_history(

    list(reversed(history["result"]))

)

swing = SwingEngine("1m")

registry = swing.scan(builder.history)

trend = SwingStructureTrendEngine()

state = trend.update(registry)

print()

print("=" * 60)

print("TREND")

print("=" * 60)

print(state.trend)

print()

print("HH", state.higher_highs)

print("HL", state.higher_lows)

print("LH", state.lower_highs)

print("LL", state.lower_lows)

loader.close()