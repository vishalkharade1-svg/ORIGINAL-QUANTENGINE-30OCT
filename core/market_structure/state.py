"""
====================================================

QuantEngine

Institutional Market Structure State

Single source of truth for all market structure.

====================================================
"""

from dataclasses import dataclass, field

from core.enums import StructureType
from core.enums import TrendType


@dataclass(slots=True)
class MarketStructureState:

    # -------------------------------------------------
    # Trend
    # -------------------------------------------------

    trend: TrendType = TrendType.RANGE

    internal_trend: TrendType = TrendType.RANGE

    external_trend: TrendType = TrendType.RANGE

    # -------------------------------------------------
    # Market Structure
    # -------------------------------------------------

    structure: str = ""

    bos: bool = False

    choch: bool = False

    # -------------------------------------------------
    # Swings
    # -------------------------------------------------

    major_high: float = 0.0

    major_low: float = 0.0

    internal_high: float = 0.0

    internal_low: float = 0.0

    # -------------------------------------------------
    # Liquidity
    # -------------------------------------------------

    buy_side_liquidity: float = 0.0

    sell_side_liquidity: float = 0.0

    liquidity_sweep: bool = False

    # -------------------------------------------------
    # Premium / Discount
    # -------------------------------------------------

    premium: bool = False

    discount: bool = False

    equilibrium: float = 0.0

    # -------------------------------------------------
    # Fibonacci
    # -------------------------------------------------

    fib_anchor_high: float = 0.0

    fib_anchor_low: float = 0.0

    # -------------------------------------------------
    # Confluence
    # -------------------------------------------------

    score: float = 0.0

    confidence: float = 0.0

    # -------------------------------------------------
    # Structure History
    # -------------------------------------------------

    structure_events: list = field(default_factory=list)

    last_structure: StructureType = StructureType.NONE

    last_bos: StructureType = StructureType.NONE

    last_choch: StructureType = StructureType.NONE

    last_mss: StructureType = StructureType.NONE

    # -------------------------------------------------
    # Signals
    # -------------------------------------------------

    signals: list = field(default_factory=list)