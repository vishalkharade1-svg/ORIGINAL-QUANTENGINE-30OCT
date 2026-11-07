"""
====================================================

QuantEngine

Build : 4.2
Module : Swing

====================================================
"""

from dataclasses import dataclass


@dataclass
class Swing:

    index: int

    timestamp: int

    price: float

    type: str