from core.market_structure.engine import MarketStructureEngine


engine = MarketStructureEngine()

print()

print("=" * 60)

print("MARKET STRUCTURE")

print("=" * 60)

for tf in engine.registry.states:

    state = engine.registry.get(tf)

    print(

        state.timeframe,

        state.trend,

    )