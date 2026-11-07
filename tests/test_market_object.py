from core.objects.market_object import MarketObject


def main():

    obj = MarketObject(

        object_type="SWING",

        symbol="BTCUSDT",

        timeframe="1m",

    )

    obj.touch()

    obj.react()

    obj.add_tag("major")

    obj.add_tag("institutional")

    obj.set_score(

        score=92,

        confidence=95,

        quality=91,

    )

    print()

    print("=" * 60)

    print("MARKET OBJECT")

    print("=" * 60)

    print("ID           :", obj.id)

    print("Type         :", obj.object_type)

    print("Symbol       :", obj.symbol)

    print("Timeframe    :", obj.timeframe)

    print("Touches      :", obj.touches)

    print("Reactions    :", obj.reactions)

    print("Score        :", obj.score)

    print("Confidence   :", obj.confidence)

    print("Quality      :", obj.quality)

    print("Tags         :", sorted(obj.tags))

    print("Active       :", obj.active)

    print("Invalidated  :", obj.invalidated)

    print("Archived     :", obj.archived)


if __name__ == "__main__":

    main()