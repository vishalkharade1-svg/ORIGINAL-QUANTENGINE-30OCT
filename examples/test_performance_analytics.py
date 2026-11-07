"""
====================================================

QuantEngine

Performance Analytics Example

Run with:

    python -m examples.test_performance_analytics

Runs the canonical PAPER TRADING replay (full institutional
pipeline, no credentials) and feeds the resulting shared
Account + TradeRegistry into PerformanceAnalytics -- the
same report the Backtest and Live Broker paths would produce,
because all three modes book into the same objects.

====================================================
"""

from config.settings import settings

from data.historical_loader import HistoricalLoader

from data.candle_builder import CandleBuilder

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext

from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus


from core.paper_trading.paper_trading_engine import (
    PaperTradingEngine,
)

from core.analytics.performance import PerformanceAnalytics


def main():

    symbol = settings.SYMBOLS[0]

    market = MarketState(symbol=symbol)

    context = PipelineContext()

    context.market = market

    event_bus = EventBus()

    pipeline = InstitutionalPipeline(context)

    
    loader = HistoricalLoader()

    candles = loader.candles(symbol)

    builder = CandleBuilder()

    builder.load_history(
        list(reversed(candles["result"]))
    )

    history = builder.history

    loader.close()

    paper = PaperTradingEngine(
        pipeline,
        event_bus,
    )

    print("\n" + "=" * 60)
    print("Running PAPER TRADING replay")
    print("=" * 60)
    print(f"Symbol : {symbol}")
    print(f"Bars   : {len(history)}")

    for candle in history:
        paper.run_candle(candle)

    print(
        PerformanceAnalytics.summary(
            paper.account,
            paper.trades,
            label=f"PERFORMANCE ANALYTICS -- {symbol}",
        )
    )

    print()
    print("=" * 60)
    print("EQUITY CURVE")
    print("=" * 60)

    report = PerformanceAnalytics.analyze(
        paper.account,
        paper.trades,
    )

    for timestamp, equity in report.equity_curve:
        print(f"  {timestamp}  {equity:,.2f}")

    print()


if __name__ == "__main__":
    main()