from strategy.ema_cross import EMACrossStrategy

strategy = EMACrossStrategy()

signal = strategy.evaluate(
    None,
    {
        "ema20": 95,
        "ema50": 100,
    }
)

print(signal)