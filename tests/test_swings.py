from core.market_structure.swing import Swing


def main():

    swing = Swing(

        index=120,

        timestamp=1715000000,

        price=64250,

        kind="HIGH",

        timeframe="1m",

        confirmed=True,

    )

    print()

    print("=" * 60)

    print("INSTITUTIONAL SWING")

    print("=" * 60)

    print("ID              :", swing.id)

    print("Type            :", swing.object_type)

    print("Price           :", swing.price)

    print("Kind            :", swing.kind)

    print("Confirmed       :", swing.confirmed)

    print("Institutional   :", swing.institutional)

    print("Major           :", swing.major)

    print("Score           :", swing.score)

    print("Confidence      :", swing.confidence)

    print("Quality         :", swing.quality)


if __name__ == "__main__":

    main()