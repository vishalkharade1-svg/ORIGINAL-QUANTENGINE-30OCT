"""
====================================================

QuantEngine

Market Structure Trend

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class TrendState:

    trend: str = "UNKNOWN"

    last_high: float | None = None

    last_low: float | None = None

    higher_highs: int = 0

    higher_lows: int = 0

    lower_highs: int = 0

    lower_lows: int = 0