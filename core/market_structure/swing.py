"""
====================================================

Institutional Swing Object

====================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from core.objects.market_object import MarketObject


@dataclass(slots=True)
class Swing(MarketObject):

    # ==================================================
    # Identity
    # ==================================================

    index: int = 0

    timestamp: int = 0

    timeframe: str = ""

    # ==================================================
    # Price
    # ==================================================

    price: float = 0.0

    high: float = 0.0

    low: float = 0.0

    # ==================================================
    # Classification
    # ==================================================

    kind: str = ""

    major: bool = False

    confirmed: bool = False

    # Phase 12 confirmation semantics: a fractal pivot at
    # absolute bar `index` is only knowable once `right`
    # bars exist to its right, so the earliest bar whose
    # close could have confirmed it is index + right. The
    # scanner stamps this; downstream consumers must only
    # act on swings with confirmed_bar <= current bar
    # (see SwingRegistry.confirmed_as_of). 0 = unstamped
    # (legacy/scripted swings: confirmation unknown).
    confirmed_bar: int = 0

    institutional: bool = False

    # ==================================================
    # Market Structure
    # ==================================================

    bos: bool = False

    choch: bool = False

    mss: bool = False

    liquidity_sweep: bool = False

    displacement: bool = False

    # ==================================================
    # Market Metrics
    # ==================================================

    atr: float = 0.0

    volume: float = 0.0

    reaction: float = 0.0

    distance: float = 0.0

    # ==================================================
    # Relationships
    # ==================================================

    previous_swing: str | None = None

    next_swing: str | None = None

    parent_leg: str | None = None

    # ==================================================
    # Constructor
    # ==================================================

    def __post_init__(self):

        self.object_type = "SWING"

        if self.high == 0.0:
            self.high = self.price

        if self.low == 0.0:
            self.low = self.price

    # ==================================================
    # Helpers
    # ==================================================

    def is_high(self):

        return self.kind == "HIGH"

    def is_low(self):

        return self.kind == "LOW"

    def is_bullish(self):

        return self.kind in ("HL", "HH")

    def is_bearish(self):

        return self.kind in ("LH", "LL")