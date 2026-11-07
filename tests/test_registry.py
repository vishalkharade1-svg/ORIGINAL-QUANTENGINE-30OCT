from core.objects.market_object import MarketObject
from core.registry.indexed_registry import IndexedRegistry


def main():

    registry = IndexedRegistry()

    for i in range(5):

        obj = MarketObject(

            object_type="SWING",

            symbol="BTCUSDT",

            timeframe="1m",

        )

        obj.set_score(

            score=60 + i * 10,

            confidence=90,

            quality=80,

        )

        if i % 2 == 0:

            obj.add_tag(

                "major"

            )

        registry.add(

            obj

        )

    print()

    print("=" * 60)

    print("REGISTRY")

    print("=" * 60)

    print("Objects :", len(registry))

    print()

    print("Top Objects")

    print("-" * 60)

    for obj in registry.top():

        print(

            obj.score,

            sorted(obj.tags),

        )

    print()

    best = registry.best()

    print("Best Score :", best.score)

    print()

    print("Major Objects")

    print("-" * 60)

    for obj in registry.filter(

        "major",

    ):

        print(

            obj.score,

            sorted(obj.tags),

        )


if __name__ == "__main__":

    main()