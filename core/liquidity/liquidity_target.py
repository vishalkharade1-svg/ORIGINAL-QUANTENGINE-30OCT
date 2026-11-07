"""
====================================================

QuantEngine

Institutional Liquidity Target

====================================================
"""

from dataclasses import dataclass

from core.objects.market_object import MarketObject


@dataclass(slots=True)
class LiquidityTarget(MarketObject):

    # ==================================================
    # Identity
    # ==================================================

    side: str = ""

    price: float = 0.0

    timeframe: str = ""

    # ==================================================
    # Probability
    # ==================================================

    probability: float = 0.0

    score: float = 0.0

    distance: float = 0.0

    strength: float = 0.0

    # ==================================================
    # Metadata
    # ==================================================

    reason: str = ""

    source_pool: str | None = None

    reached: bool = False

    # ==================================================
    # Constructor
    # ==================================================

    def __post_init__(self):

        self.object_type = "LIQUIDITY_TARGET"

        self.add_tag("liquidity_target")

    # ==================================================
    # Helpers
    # ==================================================

    def is_buy_side(self):

        return self.side.upper() == "BUY"

    def is_sell_side(self):

        return self.side.upper() == "SELL"

    def mark_reached(self):

        self.reached = True