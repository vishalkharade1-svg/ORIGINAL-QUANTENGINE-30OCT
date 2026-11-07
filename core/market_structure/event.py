"""
====================================================

QuantEngine

Market Structure Event

====================================================
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MarketStructureEvent:

    event: str

    symbol: str

    timeframe: str

    timestamp: int

    data: Any = None