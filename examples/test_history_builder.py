from config.settings import settings
from data.candle_builder import CandleBuilder
from data.historical_loader import HistoricalLoader

loader = HistoricalLoader()
builder = CandleBuilder()

data = loader.candles(settings.SYMBOLS[0])

# Delta returns newest first.
candles = list(reversed(data["result"]))

builder.load_history(candles)

print("History Loaded :", builder.count())

print("\nOldest Loaded Candle:")
print(builder.history[0])

print("\nNewest Loaded Candle:")
print(builder.history[-1])

loader.close()