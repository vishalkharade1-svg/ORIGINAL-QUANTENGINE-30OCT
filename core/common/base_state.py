"""
====================================================

QuantEngine

Base State

Shared parent for all state objects.

====================================================
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class BaseState:

    # -------------------------------------------------
    # Identity
    # -------------------------------------------------

    symbol: str = ""

    timeframe: str = ""

    timestamp: datetime | None = None

    # -------------------------------------------------
    # Generic Metrics
    # -------------------------------------------------

    score: float = 0.0

    confidence: float = 0.0

    active: bool = True