from data.candle_builder import CandleBuilder
from data.historical_loader import HistoricalLoader

from core.bars.bar import Bar
from core.bars.bar_series import BarSeries

from config.settings import settings

loader = HistoricalLoader()
builder = CandleBuilder()

data = loader.candles(settings.SYMBOLS[0])

builder.load_history(
    list(reversed(data["result"]))
)

series = BarSeries()

for candle in builder.history:

    series.append(
        Bar(
            timestamp=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )
    )

print()

print("Bars:", len(series))

print("Last Close:", series.closes()[-1])

print("Highest High:", max(series.highs()))

print("Lowest Low:", min(series.lows()))

loader.close()