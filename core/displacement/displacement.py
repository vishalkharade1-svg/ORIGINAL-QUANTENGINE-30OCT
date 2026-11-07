"""
====================================================

QuantEngine

Institutional Displacement Event

Version 2.0

====================================================
"""

from dataclasses import dataclass, field

from core.common.base_market_object import BaseMarketObject


@dataclass(slots=True)
class Displacement(BaseMarketObject):

    # ==================================================
    # Identity
    # ==================================================

    index: int
    timestamp: int
    timeframe: str

    direction: str

    # ==================================================
    # Candle
    # ==================================================

    open: float
    high: float
    low: float
    close: float

    # ==================================================
    # Measurements
    # ==================================================

    body: float
    candle_range: float

    atr_multiple: float
    body_ratio: float

    volume_ratio: float = 0.0

    # ==================================================
    # Institutional Features
    # ==================================================

    close_position: float = 0.0

    broke_previous_high: bool = False
    broke_previous_low: bool = False

    consecutive_impulse: int = 0

    liquidity_sweep: bool = False

    trend_alignment: bool = False

    fvg_created: bool = False

    # ==================================================
    # Scores
    # ==================================================

    body_score: float = 0.0
    atr_score: float = 0.0
    volume_score: float = 0.0
    close_score: float = 0.0
    structure_score: float = 0.0
    momentum_score: float = 0.0

    score: float = 0.0

    institutional_score: float = 0.0

    # ==================================================
    # Classification
    # ==================================================

    grade: str = "WEAK"

    strong: bool = False

    # ==================================================
    # Relationships
    # ==================================================

    swing_id: str | None = None

    structure_index: int = -1

    bos_index: int = -1

    choch_index: int = -1

    # ==================================================
    # State
    # ==================================================

    active: bool = True

    confirmed: bool = True

    # ==================================================
    # Metadata
    # ==================================================

    metadata: dict = field(default_factory=dict)

    # ==================================================

    def is_bullish(self):

        return self.direction == "BULLISH"

    # --------------------------------------------------

    def is_bearish(self):

        return self.direction == "BEARISH"

    # --------------------------------------------------

    def deactivate(self):

        self.active = False

    # --------------------------------------------------

    @property
    def elite(self):

        return self.score >= 90

    # --------------------------------------------------

    @property
    def institutional(self):

        return self.score >= 75

    # --------------------------------------------------

    @property
    def moderate(self):

        return 60 <= self.score < 75