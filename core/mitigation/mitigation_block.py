"""
====================================================

QuantEngine

Institutional Mitigation Block

====================================================
"""

from dataclasses import dataclass, field

from core.common.base_market_object import BaseMarketObject


@dataclass(slots=True)
class MitigationBlock(BaseMarketObject):

    # ==================================================
    # Identification
    # ==================================================

    index: int

    timestamp: int

    timeframe: str

    direction: str

    # ==================================================
    # Price Range
    # ==================================================

    high: float

    low: float

    # ==================================================
    # Required Fields
    # ==================================================

    source_order_block: int

    # ==================================================
    # Institutional Quality
    # ==================================================

    score: float = 0.0

    institutional_score: float = 0.0

    strength: float = 0.0

    # ==================================================
    # Relationships
    # ==================================================

    source_fvg: int = -1

    source_displacement: int = -1

    # ==================================================
    # Runtime State
    # ==================================================

    active: bool = True

    mitigated: bool = False

    invalidated: bool = False

    touches: int = 0

    mitigation_timestamp: int = 0

    # ==================================================
    # Metadata
    # ==================================================

    metadata: dict = field(

        default_factory=dict,

    )

    # ==================================================

    def is_bullish(self):

        return self.direction == "BULLISH"

    # --------------------------------------------------

    def is_bearish(self):

        return self.direction == "BEARISH"

    # --------------------------------------------------

    def touch(self):

        self.touches += 1

    # --------------------------------------------------

    def mark_mitigated(

        self,

        timestamp: int,

    ):

        self.mitigated = True

        self.active = False

        self.mitigation_timestamp = timestamp

    # --------------------------------------------------

    def invalidate(

        self,

        timestamp: int,

    ):

        self.invalidated = True

        self.active = False

        self.mitigation_timestamp = timestamp