"""
====================================================

QuantEngine

Institutional Liquidity Sweep

====================================================
"""

from dataclasses import dataclass

from core.objects.market_object import MarketObject


@dataclass(slots=True)
class LiquiditySweep(MarketObject):

    # ==================================================
    # Identity
    # ==================================================

    side: str = ""

    timeframe: str = ""

    timestamp: int = 0

    # ==================================================
    # Prices
    # ==================================================

    pool_price: float = 0.0

    sweep_price: float = 0.0

    rejection_price: float = 0.0

    # ==================================================
    # Validation
    # ==================================================

    confirmed: bool = False

    mitigated: bool = False

    strength: float = 0.0

    probability: float = 0.0

    # ==================================================
    # Relationships
    # ==================================================

    pool_id: str | None = None

    target_id: str | None = None

    # ==================================================
    # Constructor
    # ==================================================

    def __post_init__(self):

        self.object_type = "LIQUIDITY_SWEEP"

        self.add_tag("liquidity_sweep")

    # ==================================================
    # Helpers
    # ==================================================

    def is_buy_side(self):

        return self.side.upper() == "BUY"

    def is_sell_side(self):

        return self.side.upper() == "SELL"

    def confirm(self):

        self.confirmed = True

    def mitigate(self):

        self.mitigated = True