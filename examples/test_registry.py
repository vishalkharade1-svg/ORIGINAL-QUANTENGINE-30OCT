from core.market_registry import registry

print("Configured Markets:\n")

for market in registry.all():
    print(market)