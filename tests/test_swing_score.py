from core.objects.market_object import MarketObject
from core.scoring.swing_score_engine import SwingScoreEngine


def main():

    swing = MarketObject(

        object_type="SWING",

        symbol="BTCUSDT",

        timeframe="1m",

    )

    swing.metadata = {

        "atr_score": 18,

        "volume_score": 14,

        "liquidity_score": 20,

        "bos_score": 15,

        "htf_score": 10,

        "time_score": 5,

    }

    engine = SwingScoreEngine()

    engine.score(

        swing,

    )

    print()

    print("=" * 60)

    print("SWING SCORE")

    print("=" * 60)

    print("Score       :", swing.score)

    print("Confidence  :", swing.confidence)

    print("Quality     :", swing.quality)


if __name__ == "__main__":

    main()