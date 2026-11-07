from config.settings import settings

from data.candle_builder import CandleBuilder
from data.historical_loader import HistoricalLoader
from data.bar_series import BarSeries

from smartmoney.swing_detector import SwingDetector
from smartmoney.market_structure import MarketStructure


loader = HistoricalLoader()

builder = CandleBuilder()

history = loader.candles(settings.SYMBOLS[0])

builder.load_history(
    list(reversed(history["result"]))
)

bars = BarSeries(builder.history)

detector = SwingDetector()

swings = detector.detect(bars)

engine = MarketStructure()

structure = engine.analyze(swings)

print()

print("Last 30 Structure Points")

print("=" * 60)

for point in structure[-30:]:

    print(
        point.label,
        point.swing.type,
        point.swing.price,
    )

loader.close()