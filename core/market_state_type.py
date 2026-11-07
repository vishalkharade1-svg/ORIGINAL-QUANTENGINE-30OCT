"""
====================================================

QuantEngine

Sprint 6

Market State Types

====================================================
"""

from enum import Enum


class MarketStateType(Enum):

    TREND_UP = "TREND_UP"

    TREND_DOWN = "TREND_DOWN"

    RANGE = "RANGE"

    BREAKOUT = "BREAKOUT"

    REVERSAL = "REVERSAL"

    HIGH_VOLATILITY = "HIGH_VOLATILITY"

    LOW_VOLATILITY = "LOW_VOLATILITY"