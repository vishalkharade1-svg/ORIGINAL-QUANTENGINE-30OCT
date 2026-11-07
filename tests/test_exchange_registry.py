# Phase 12 triage: DOCUMENTED AS EXAMPLE (manual
# exchange-registry demo; collects 0 tests by design).
# Top-level demo code is guarded so pytest collection has
# no side effects and stays silent.
from core.exchanges.exchange_registry import ExchangeRegistry
from core.exchanges.delta.delta_exchange import DeltaExchange


def main():
    registry = ExchangeRegistry()

    registry.register("DELTA", DeltaExchange())

    print()

    print("=" * 60)
    print("REGISTERED EXCHANGES")
    print("=" * 60)

    print(registry.all())


if __name__ == "__main__":
    main()
