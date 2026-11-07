"""
====================================================

QuantEngine

Live Trading Package

====================================================

The BrokerEngine routes the same RiskEngine OrderIntent the
Backtester and PaperTradingEngine consume to the REAL Delta
exchange through a DeltaOrderExecutor, tracks the open
position, and books closed P&L into the shared TradeRegistry
+ Account.

Replay, Paper and Live share ONE execution flow -- the
institutional pipeline is driven explicitly (pipeline
first), then the intent is routed, then the position is
managed, then P&L is booked. Only the fill/exit source
differs:

    Replay/Backtest : TradeSimulator candle management
    Paper           : TradeSimulator candle management
    Live (Broker)   : exchange-native bracket + position sync

dry_run=True (the default) guarantees ZERO exchange writes;
the would-be intent is recorded and the position is managed
through the same TradeSimulator, so the full flow is testable
offline. Live placement is a strict, explicit opt-in.
"""

from core.live.broker_engine import BrokerEngine

__all__ = [
    "BrokerEngine",
]