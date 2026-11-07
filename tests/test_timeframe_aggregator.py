"""
====================================================

QuantEngine

Timeframe Aggregator Test

====================================================
"""

from core.history.history_database import HistoryDatabase
from core.history.timeframe_aggregator import TimeframeAggregator


def main():

    db = HistoryDatabase()

    agg = TimeframeAggregator()

    candles = db.get(

        "BTCUSDT",

        "1m",

        days=1,

    )

    aggregated = agg.aggregate(

        candles,

        "45m",

    )

    print()

    print("=" * 60)
    print("45 MINUTE AGGREGATION")
    print("=" * 60)
    print()

    print(f"Input Candles      : {len(candles)}")
    print(f"Output Candles     : {len(aggregated)}")
    print()

    print("First 5 Aggregated Candles")
    print("-" * 60)

    for candle in aggregated[:5]:

        print(

            f"Timestamp : {candle.timestamp}"

        )

        print(

            f"Open      : {candle.open}"

        )

        print(

            f"High      : {candle.high}"

        )

        print(

            f"Low       : {candle.low}"

        )

        print(

            f"Close     : {candle.close}"

        )

        print(

            f"Volume    : {candle.volume}"

        )

        print("-" * 60)


if __name__ == "__main__":

    main()