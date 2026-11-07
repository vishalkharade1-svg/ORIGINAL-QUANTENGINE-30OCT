"""
====================================================

QuantEngine

Trade Setup Builder / Decision Engine Diagnostic

Runs the full InstitutionalPipeline candle-by-candle over
real historical data and prints the resulting regime,
accepted trade setups, and rejected trade setups with
reasons.

This replaces a previous version of this script that called
each engine directly with the pre-PipelineContext calling
convention (e.g. DisplacementScanner().scan(bars, atr),
RegimeEngine().analyze(trend=..., structure=..., ...)).
None of that matches the current engine contract -- every
registered engine now implements analyze(context) and reads
its inputs from / publishes its outputs to PipelineContext.
See core/pipeline/institutional_pipeline.py for the
canonical registration list.

====================================================
"""

from config.settings import settings

from data.historical_loader import HistoricalLoader
from data.candle_builder import CandleBuilder

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.diagnostics.pipeline_report import PipelineReport


def main():

    InstitutionalPipeline.DEBUG = False

    loader = HistoricalLoader()

    # See test_backtester.py / data/historical_loader.py:
    # a single request caps out around 2000 candles at Delta's
    # API limit -- candles_paginated() walks backward across
    # multiple requests to gather more.
    history = loader.candles_paginated(
        settings.SYMBOLS[0],
        resolution=settings.TIMEFRAME,
        total_candles=5000,
    )

    builder = CandleBuilder(max_history=len(history["result"]) or 1)

    builder.load_history(
        list(reversed(history["result"]))
    )

    candles = list(builder.history)

    print(f"Loaded {len(candles)} candles.")

    market = MarketState(
        symbol=settings.SYMBOLS[0]
    )

    context = PipelineContext()
    context.market = market

    # InstitutionalPipeline already registers the full
    # institutional engine set internally -- do not
    # re-register any of them here (see main.py / the
    # audit notes for why that used to silently corrupt
    # context.indicators).
    pipeline = InstitutionalPipeline(context)

    for candle in candles:
        context.add_candle(candle)
        pipeline.process()

    # -------------------------------------------------
    # Diagnostics
    # -------------------------------------------------

    PipelineReport().report(context)

    # -------------------------------------------------
    # Rejected Setups
    # -------------------------------------------------

    decision_engine = None
    for engine in pipeline.engines:
        if type(engine).__name__ == "DecisionEngine":
            decision_engine = engine
            break

    print()
    print("=" * 70)
    print("REJECTED SETUPS")
    print("=" * 70)

    if decision_engine and decision_engine.rejected:

        for reject in decision_engine.rejected:

            print()
            print("Direction :", reject.direction)
            print("Reasons:")

            for reason in reject.reasons:
                print("  -", reason)

    else:
        print("None")

    # -------------------------------------------------
    # Accepted Setups
    # -------------------------------------------------

    print()
    print("=" * 70)
    print("ACCEPTED TRADE SETUPS")
    print("=" * 70)

    setups = context.decision

    if setups is None or setups.count() == 0:

        print("No valid institutional trade setup.")
        print()
        print(
            "This is not necessarily an error -- see spec section 31: "
            "the pipeline can legitimately process an entire dataset "
            "without a qualifying setup. DecisionEngine requires "
            "regime.score >= 70, confidence >= 80, and risk_reward "
            ">= 2.0 simultaneously (see core/setup/decision_engine.py). "
            "Check REJECTED SETUPS above for the specific reasons on "
            "each candidate that was considered and turned down."
        )

    else:

        for setup in setups.all():

            print()

            print("Direction   :", setup.direction)
            print("Entry       :", round(setup.entry, 2))
            print("Stop Loss   :", round(setup.stop_loss, 2))
            print("Take Profit :", round(setup.take_profit, 2))
            print("Risk Reward :", round(setup.risk_reward, 2))
            print("Score       :", round(setup.score, 2))
            print("Confidence  :", round(setup.confidence, 2))

            if hasattr(setup, "order_block") and setup.order_block:

                print()
                print("Order Block")
                print("  High :", setup.order_block.high)
                print("  Low  :", setup.order_block.low)

            if hasattr(setup, "liquidity_target") and setup.liquidity_target:

                print()
                print("Liquidity Target")
                print("  Price :", setup.liquidity_target.price)

    loader.close()


if __name__ == "__main__":
    main()
