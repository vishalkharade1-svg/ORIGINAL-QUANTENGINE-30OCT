"""
====================================================

QuantEngine

Paper Trading Package

====================================================

The PaperTradingEngine reuses the canonical institutional
pipeline end-to-end (indicators -> structure -> setup ->
decision -> execution -> risk) with NO exchange credentials
required. Finished candles -- from a live websocket feed or
a replayed history -- run through the exact same execution
flow as the Backtester: pipeline first, then a paper fill,
then SL/TP management, then account booking.

Replay, Paper and Live share ONE execution flow. The only
difference between them is where the candles come from.
"""

from core.paper_trading.paper_trading_engine import (
    PaperTradingEngine,
)

__all__ = [
    "PaperTradingEngine",
]