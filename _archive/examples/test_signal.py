from strategy.ema_cross import EMACrossStrategy
from data.candle_builder import Candle

strategy = EMACrossStrategy()

candle = Candle(
    timestamp=1234567890,
    open=100,
    high=105,
    low=99,
    close=103,
)

signal = strategy.evaluate(
    candle,
    {
        "ema20": 105,
        "ema50": 100,
    },
)

print(signal)