"""
====================================================

QuantEngine

Institutional Liquidity Pool

====================================================
"""

from dataclasses import dataclass, field

from core.objects.market_object import MarketObject


@dataclass(slots=True)
class LiquidityPool(MarketObject):

    # ==================================================
    # Identity
    # ==================================================

    side: str = ""

    price: float = 0.0

    timeframe: str = ""

    # ==================================================
    # Detection
    # ==================================================

    touches: int = 0

    first_timestamp: int = 0

    last_timestamp: int = 0

    active: bool = True

    swept: bool = False

    # ==================================================
    # Metrics
    # ==================================================

    score: float = 0.0

    strength: float = 0.0

    reaction: float = 0.0

    volume: float = 0.0

    # ==================================================
    # Relationships
    # ==================================================

    source_swings: list[str] = field(default_factory=list)

    target_id: str | None = None

    # ==================================================
    # Constructor
    # ==================================================

    def __post_init__(self):

        self.object_type = "LIQUIDITY_POOL"

        self.add_tag("liquidity")

    # ==================================================
    # Helpers
    # ==================================================

    def is_buy_side(self):

        return self.side.upper() == "BUY"

    def is_sell_side(self):

        return self.side.upper() == "SELL"

    def activate(self):

        self.active = True

    def deactivate(self):

        self.active = False

    def mark_swept(self):

        self.swept = True

        self.active = False