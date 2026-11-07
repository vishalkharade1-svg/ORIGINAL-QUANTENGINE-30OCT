"""
====================================================

QuantEngine

Live Broker Engine Example

Run with:

    python -m examples.test_live_broker

Replays the configured symbol's Delta history through the
full institutional pipeline and routes every RiskEngine
OrderIntent through the BrokerEngine -> DeltaOrderExecutor
flight path.

DRY-RUN BY DEFAULT: with dry_run=True the broker records each
would-be intent on `placed` and manages a paper position with
the shared TradeSimulator -- zero exchange calls, fully
offline. To actually arm live placement:

    set LIVE_EXECUTE=1 (and DELTA_API_KEY / DELTA_API_SECRET
    in .env) -- the DeltaExchange._require_auth guard is a
    second backstop: no private endpoint fires without keys.

====================================================
"""

import os

from config.settings import settings

from data.historical_loader import HistoricalLoader

from data.candle_builder import CandleBuilder

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext

from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus


from core.exchanges.delta.delta_contract_loader import DeltaContractLoader
from core.exchanges.delta.delta_exchange import DeltaExchange

from core.execution.order_executor import DeltaOrderExecutor

from core.live.broker_engine import BrokerEngine


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

    executor = DeltaOrderExecutor(
        exchange=DeltaExchange(),
        registry=DeltaContractLoader().load(),
    )

    dry_run = os.getenv("LIVE_EXECUTE", "0") != "1"

    broker = BrokerEngine(
        pipeline,
        event_bus,
        executor=executor,
        dry_run=dry_run,
    )

    print("\n" + "=" * 60)
    print("Running LIVE BROKER replay")
    print("=" * 60)
    print(f"Symbol : {symbol}")
    print(f"Bars   : {len(history)}")
    print(
        "Mode   : "
        + (
            "DRY-RUN (LIVE_EXECUTE=1 to arm live placement)"
            if dry_run
            else "LIVE"
        )
    )

    for candle in history:
        broker.run_candle(candle)

    print()
    print("=" * 60)
    print("ROUTING AUDIT")
    print("=" * 60)
    print(f"Intents routed : {len(broker.placed)}")

    for i, placed in enumerate(broker.placed, 1):

        if dry_run:

            print(f"  {i:>3} would-place {placed.direction:8} "
                  f"entry={placed.entry:10.2f} qty={placed.quantity:.4f}")

        else:

            print(f"  {i:>3} execute success={placed.get('success')}")

    print()
    print("=" * 60)
    print("ACCOUNT")
    print("=" * 60)
    print(f"Starting balance : {broker.account.state.starting_balance:,.2f}")
    print(f"Final balance    : {broker.account.balance:,.2f}")
    print(f"Realized P&L     : {broker.account.state.realized_pnl:,.2f}")
    print(f"Trades           : {len(broker.completed_trades)}")

    print()
    print("=" * 60)
    print("CLOSED TRADES")
    print("=" * 60)

    for trade in broker.completed_trades:
        print(
            f"{trade.direction:8} "
            f"entry={trade.entry:10.2f} "
            f"exit={trade.exit_price:10.2f} "
            f"{trade.result:4} "
            f"pnl={trade.pnl:+12.2f}"
        )


if __name__ == "__main__":
    main()