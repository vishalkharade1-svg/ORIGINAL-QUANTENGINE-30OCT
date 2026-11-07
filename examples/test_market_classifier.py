from core.market_classifier import MarketClassifier


trend, volatility = MarketClassifier().classify(

    ema20=64250,

    ema50=64180,

    atr=145,

)

print()

print("Market Classification")

print("=" * 50)

print("Trend      :", trend.value)

print("Volatility :", volatility.value)