"""
====================================================

QuantEngine

Institutional Bar

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class Bar:

    timestamp: int

    open: float
    high: float
    low: float
    close: float

    volume: float = 0.0

    trades: int = 0

    buy_volume: float = 0.0
    sell_volume: float = 0.0

    delta: float = 0.0

    quote_volume: float = 0.0

    open_interest: float = 0.0

    vwap: float = 0.0