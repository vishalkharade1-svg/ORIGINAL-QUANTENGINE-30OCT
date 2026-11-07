"""
====================================================

QuantEngine

Live / Replay Paper Trading Example

Run with:

    python examples/test_paper_trading.py

Replays the configured symbol's Delta history through the
full institutional pipeline (indicators -> structure ->
setup -> decision -> execution -> risk) and books paper
fills with the canonical TradeSimulator + Account -- the
same execution flow the LIVE paper mode drives off the
websocket feed (see main.py).

No exchange credentials required; PAPER_MODE is the
default in config/settings.py.

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

from core.common.logging_config import get_logger

log = get_logger(__name__)


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

    print()
    print("=" * 60)
    print("ACCOUNT")
    print("=" * 60)
    print(f"Starting balance : {paper.account.state.starting_balance:,.2f}")
    print(f"Final balance    : {paper.account.balance:,.2f}")
    print(f"Realized P&L     : {paper.account.state.realized_pnl:,.2f}")
    print(f"Trades           : {paper.account.state.total_trades}")
    print(f"Wins             : {paper.account.state.winning_trades}")
    print(f"Losses           : {paper.account.state.losing_trades}")
    print(f"Win rate         : {paper.account.state.win_rate:.2f}%")
    print(f"Max drawdown     : {paper.account.state.max_drawdown:,.2f}")

    print()
    print("=" * 60)
    print("TRADES")
    print("=" * 60)

    for trade in paper.completed_trades:
        print(
            f"{trade.direction:8} "
            f"entry={trade.entry:10.2f} "
            f"exit={trade.exit_price:10.2f} "
            f"{trade.result:4} "
            f"pnl={trade.pnl:+12.2f}"
        )


if __name__ == "__main__":
    main()