from config.settings import settings

from data.historical_loader import HistoricalLoader

from data.candle_builder import CandleBuilder

from backtesting.portfolio_backtester import PortfolioBacktester

from core.exchanges.delta.delta_contract_loader import DeltaContractLoader

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus



loader = HistoricalLoader()


def make_pipeline(symbol):

    market = MarketState(symbol=symbol)

    context = PipelineContext()

    context.market = market

    event_bus = EventBus()

    pipeline = InstitutionalPipeline(context)

    
    pipeline.subscribe(event_bus)

    return pipeline, event_bus


portfolio = PortfolioBacktester(pipeline_factory=make_pipeline)

history = {}

symbols = None  # deferred so UNIVERSE=all hits the loader once

if settings.UNIVERSE == "all":
    symbols = [
        contract.symbol
        for contract in DeltaContractLoader().load().all()
    ]

for symbol in symbols if symbols is not None else settings.SYMBOLS:

    print("Loading", symbol)

    candles = loader.candles(symbol)

    builder = CandleBuilder()

    builder.load_history(

        list(reversed(candles["result"]))

    )

    history[symbol] = builder.history

    portfolio.add_symbol(symbol)

print()

print("=" * 60)

print("Running Portfolio Backtest")

print("=" * 60)

results = portfolio.run(history)

print()

print("=" * 60)

print("SUMMARY")

print("=" * 60)

for symbol, total in results.items():

    print(

        f"{symbol:12}",

        total,

        "bars",

    )

loader.close()