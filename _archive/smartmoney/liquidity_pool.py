"""
====================================================

QuantEngine

Build : 4.8
Module : Liquidity Pool

====================================================
"""

from dataclasses import dataclass


@dataclass
class LiquidityPool:

    type: str

    price: float

    touches: int = 1

    strength: float = 0.0

    active: bool = True

    swept: bool = False

    sweep_timestamp: int = 0

    first_timestamp: int = 0

    last_timestamp: int = 0