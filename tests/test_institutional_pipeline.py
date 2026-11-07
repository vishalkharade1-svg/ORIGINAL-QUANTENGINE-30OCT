from core.history.history_database import HistoryDatabase

from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline


def main():

    print("=" * 60)
    print("INSTITUTIONAL PIPELINE TEST")
    print("=" * 60)

    db = HistoryDatabase()

    candles = db.get(

        "BTCUSDT",
        "1m",
        days=1,

    )

    context = PipelineContext()

    pipeline = InstitutionalPipeline(context)

    processed = 0

    for candle in candles:

        context.add_candle(candle)

        pipeline.process()

        processed += 1

    print()

    print("Processed Candles :", processed)

    print("Pipeline Engines  :", len(pipeline.engines))

    print("Statistics")

    print("Processed :", pipeline.statistics.processed)

    print("Trades    :", pipeline.statistics.trades)

    print("PnL       :", pipeline.statistics.pnl)

    print("Win Rate  :", pipeline.statistics.win_rate)

    print()

    print("PIPELINE OK")


if __name__ == "__main__":

    main()