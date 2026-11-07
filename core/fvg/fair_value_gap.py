"""
====================================================

QuantEngine

Institutional Fair Value Gap

====================================================
"""

from dataclasses import dataclass, field

from core.common.base_market_object import BaseMarketObject


@dataclass(slots=True)
class FairValueGap(BaseMarketObject):

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

    upper: float

    lower: float

    size: float

    # ==================================================
    # Institutional Quality
    # ==================================================

    displacement_strength: float

    volume_ratio: float = 0.0

    institutional_score: float = 0.0

    score: float = 0.0

    # ==================================================
    # Relationships
    # ==================================================

    displacement_index: int = -1

    bos_index: int = -1

    choch_index: int = -1

    order_block_index: int = -1

    # ==================================================
    # State
    # ==================================================

    active: bool = True

    filled: bool = False

    partially_filled: bool = False

    invalidated: bool = False

    fill_percentage: float = 0.0

    fill_timestamp: int = 0

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

    def mark_filled(

        self,

        timestamp: int,

    ):

        self.filled = True

        self.active = False

        self.fill_percentage = 100.0

        self.fill_timestamp = timestamp

    # --------------------------------------------------

    def mark_partial(

        self,

        percent: float,

    ):

        self.partially_filled = True

        self.fill_percentage = max(

            self.fill_percentage,

            min(percent, 100.0),

        )

    # --------------------------------------------------

    def invalidate(

        self,

        timestamp: int,

    ):

        self.invalidated = True

        self.active = False

        self.fill_timestamp = timestamp