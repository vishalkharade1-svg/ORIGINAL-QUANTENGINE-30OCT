"""
====================================================

QuantEngine

Performance Dashboard Example

Run with:

    python -m examples.test_performance_dashboard

Runs the canonical PAPER TRADING replay (full institutional
pipeline, no credentials) and renders the Performance
Dashboard over the resulting shared Account + TradeRegistry --
the identical flow any mode (Backtest / Paper / Live Broker)
would display, since all book into the same objects.

Prints: stat block, ASCII equity curve, recent trades table,
and a CSV export of the closed trade list to a temp file.

====================================================
"""

import os
import tempfile

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

from core.dashboard.dashboard import PerformanceDashboard


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

    report = PerformanceAnalytics.analyze(
        paper.account,
        paper.trades,
    )

    print(
        PerformanceDashboard.render(
            report,
            label=f"PERFORMANCE DASHBOARD -- {symbol}",
        )
    )

    print(
        "\n".join(
            PerformanceDashboard.render_equity_curve(
                report,
                height=12,
                width=60,
            )
        )
    )

    print(
        PerformanceDashboard.render_trades(
            report,
            paper.trades,
            limit=15,
        )
    )

    fd, path = tempfile.mkstemp(
        prefix="performance_",
        suffix=".csv",
    )

    os.close(fd)

    written = PerformanceDashboard.export_csv(
        paper.trades,
        path=path,
    )

    print("\n" + "=" * 60)
    print("CSV EXPORT")
    print("=" * 60)
    print(f"Wrote : {written}")

    with open(path, encoding="utf-8") as fh:
        preview = fh.read(400)

    print(preview)

    os.remove(path)

    print()


if __name__ == "__main__":
    main()