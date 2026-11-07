# Phase 12 triage: DOCUMENTED AS EXAMPLE (manual
# replay-pipeline demo; collects 0 tests by design).
#
# Previously this file executed a live database fetch
# (HistoryDatabase.get) and a full replay run AT IMPORT
# TIME, so every pytest collection paid for network I/O.
# All execution now lives under main(), guarded by
# __main__: collection is side-effect free.
from core.history.history_database import HistoryDatabase

from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.replay.pipeline_runner import PipelineRunner
from core.replay.replay_engine import ReplayEngine

from core.market_structure.swing_engine import SwingEngine


def main():
    db = HistoryDatabase()

    candles = db.get(
        "BTCUSDT",
        "1m",
        days=1,
    )

    context = PipelineContext()

    pipeline = InstitutionalPipeline(context)

    pipeline.register(
        SwingEngine(
            timeframe="1m",
        )
    )

    replay = ReplayEngine(candles)

    runner = PipelineRunner(
        replay=replay,
        pipeline=pipeline,
    )

    runner.run()

    print()
    print("=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print()
    print(context.swings)


if __name__ == "__main__":
    main()
