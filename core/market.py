"""
====================================================

QuantEngine

Build : 2.8
Module: Market

Represents one trading market.

====================================================
"""

from core.market_state import MarketState
from data.candle_builder import CandleBuilder


class Market:
    """Represents a single trading symbol."""

    def __init__(self, symbol: str):

        self.symbol = symbol

        # Live market information
        self.state = MarketState(symbol=symbol)

        # Builds OHLC candles
        self.candle_builder = CandleBuilder()

        # Will be added in future builds
        self.indicator_manager = None
        self.indicator_state = None
        self.position = None

    def __repr__(self):

        return f"Market(symbol='{self.symbol}')"