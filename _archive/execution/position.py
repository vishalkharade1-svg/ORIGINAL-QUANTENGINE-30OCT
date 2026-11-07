"""
====================================================

QuantEngine

Sprint 6

Position Model

====================================================
"""

from dataclasses import dataclass


@dataclass
class Position:

    symbol: str

    side: str

    quantity: float

    entry: float

    stop_loss: float

    take_profit: float

    open: bool = True

    exit_price: float = 0.0

    pnl: float = 0.0