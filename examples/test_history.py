from config.settings import settings
from data.historical_loader import HistoricalLoader

loader = HistoricalLoader()

data = loader.candles(settings.SYMBOLS[0])

print("Success :", data["success"])
print("Candles :", len(data["result"]))

print("\nFirst Candle:")
print(data["result"][0])

print("\nLast Candle:")
print(data["result"][-1])

loader.close()