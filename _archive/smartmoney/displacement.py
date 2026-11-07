"""
====================================================

QuantEngine

Build : 4.11

Module : Displacement

====================================================
"""

from dataclasses import dataclass


@dataclass
class Displacement:

    direction: str

    timestamp: int

    open: float

    high: float

    low: float

    close: float

    body: float

    range: float