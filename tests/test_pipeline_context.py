"""
====================================================

Institutional Pipeline Context Test

====================================================
"""

from core.history.history_database import HistoryDatabase
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline


def main():

    db = HistoryDatabase()

    candles = db.get(
        "BTCUSDT",
        "1m",
        days=1,
    )

    context = PipelineContext()

    pipeline = InstitutionalPipeline(context)

    for candle in candles[:100]:

        context.add_candle(candle)

        pipeline.process()

    print()
    print("=" * 60)
    print("PIPELINE OK")
    print("=" * 60)

    print()
    print("Latest Candle")
    print(context.latest_candle)

    print()
    print("Trend")
    print(context.trend)

    print()
    print("Swings")
    print(context.swings)

    print()
    print("Structure Events")
    print(context.structure_events)

    print()
    print("Market Structure")
    print(context.market_structure)

    print()
    print("Regime")
    print(context.regime)


if __name__ == "__main__":

    main()