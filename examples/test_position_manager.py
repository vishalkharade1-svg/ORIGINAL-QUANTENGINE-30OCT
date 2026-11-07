"""
====================================================

QuantEngine

Position Manager Example

Run with:

    python -m examples.test_position_manager

1. Shows the execution-layer hygiene the SHARED PositionManager
   applies at the single choke point (TradeSimulator.open_trade)
   -- rounding, notional capping, dust dropping -- by auditing a
   sample OrderIntent.
2. Runs the canonical PAPER TRADING replay and reads live
   snapshots of the open position (unrealized PnL from the
   shared Trade, no duplicated state) at each candle's close.

====================================================
"""

from config.settings import settings

from data.historical_loader import HistoricalLoader

from data.candle_builder import CandleBuilder

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext

from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus


from core.risk.order_intent import OrderIntent

from core.risk.position_manager import PositionManager

from core.paper_trading.paper_trading_engine import (
    PaperTradingEngine,
)


def main():

    manager = PositionManager()

    sample = OrderIntent(
        direction="BULLISH",
        entry=1000.0,
        stop_loss=950.0,
        take_profit=1200.0,
        quantity=10.0,
        position_value=10000.0,
        symbol="BTCUSDT",
        valid=True,
        risk_amount=50.0,
    )

    refined, reasons = manager.audit(sample)

    print("\n" + "=" * 60)
    print("POSITION MANAGER -- ORDER REFINEMENT")
    print("=" * 60)
    print(f"  Original qty    : {sample.quantity} "
          f"(notional {sample.position_value:,.0f})")
    print(f"  Refined qty     : {refined.quantity:.6f} "
          f"(notional {refined.quantity * refined.entry:,.0f})")
    print(f"  Original intact : {sample.quantity == 10.0}")
    print("  Adjustments     :")
    for reason in reasons:
        print(f"    - {reason}")
    if not reasons:
        print("    none")

    symbol = settings.SYMBOLS[0]

    market = MarketState(symbol=symbol)

    context = PipelineContext()

    context.market = market

    event_bus = EventBus()

    pipeline = InstitutionalPipeline(context)

    
    loader = HistoricalLoader()

    candles = loader.candles(symbol)

    builder = CandleBuilder()

    builder.load_history(list(reversed(candles["result"])))

    history = builder.history

    loader.close()

    paper = PaperTradingEngine(pipeline, event_bus)

    print("\n" + "=" * 60)
    print("POSITION MANAGER -- LIVE SNAPSHOTS")
    print("=" * 60)
    print(f"Symbol : {symbol}")
    print(f"Bars   : {len(history)}")

    seen = 0

    for candle in history:

        paper.run_candle(candle)

        trade = paper.current_trade

        if trade is None:
            continue

        snap = manager.snapshot(trade, candle.close)

        if seen >= 5:
            continue

        seen += 1

        print(
            f"  t={candle.timestamp} {snap['symbol']} "
            f"{snap['direction']:<7} qty={snap['quantity']:.6f} "
            f"value={snap['position_value']:,.2f} "
            f"pnl={snap['unrealized_pnl']:+.2f} "
            f"({snap['unrealized_percent']:+.2f}%) [{snap['state']}]"
        )

    if seen == 0:
        print("  No open position on the demo window.")

    print()


if __name__ == "__main__":
    main()