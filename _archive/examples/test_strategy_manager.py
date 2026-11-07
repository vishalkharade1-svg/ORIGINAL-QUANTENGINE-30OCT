from strategy.strategy_manager import StrategyManager

manager = StrategyManager()

strategy = manager.get("ICT")

print()

print("Loaded Strategy")

print("=" * 50)

print("Name:", strategy.name)

print("Risk:", strategy.risk)

print()

print("Enabled Modules")

print(strategy.enabled)

print()

print("Weights")

for key, value in strategy.weights.items():

    print(f"{key:15} {value}")