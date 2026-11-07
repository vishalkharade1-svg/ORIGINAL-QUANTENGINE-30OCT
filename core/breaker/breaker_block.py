"""
====================================================

Institutional Breaker Block

====================================================
"""

from dataclasses import dataclass

from core.common.base_market_object import BaseMarketObject


@dataclass(slots=True)
class BreakerBlock(BaseMarketObject):

    # -------------------------------------------------
    # Identification
    # -------------------------------------------------

    index: int

    timestamp: int

    direction: str

    # -------------------------------------------------
    # Price Range
    # -------------------------------------------------

    high: float

    low: float

    # -------------------------------------------------
    # Quality
    # -------------------------------------------------

    score: float

    # -------------------------------------------------
    # Relationships
    # -------------------------------------------------

    source_order_block: int

    # -------------------------------------------------
    # Runtime State
    # -------------------------------------------------

    active: bool = True

    invalidated: bool = False