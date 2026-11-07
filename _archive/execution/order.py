"""
====================================================

QuantEngine

Sprint 6

Order Model

====================================================
"""

from dataclasses import dataclass


@dataclass
class Order:

    symbol: str

    side: str

    quantity: float

    entry: float

    stop_loss: float

    take_profit: float

    strategy: str

    paper: bool = True