"""
====================================================

QuantEngine

Build : 4.10

Module : Fair Value Gap

====================================================
"""

from dataclasses import dataclass


@dataclass
class FairValueGap:

    direction: str

    top: float

    bottom: float

    timestamp: int

    active: bool = True

    filled: bool = False