"""
====================================================

QuantEngine

Institutional Footprint

Represents complete order-flow information for a
single candle.

====================================================
"""

from dataclasses import dataclass, field

from core.orderflow.price_level import PriceLevel


@dataclass(slots=True)
class Footprint:

    # ==================================================
    # Identification
    # ==================================================

    candle_index: int = 0

    timestamp: int = 0

    timeframe: str = ""

    # ==================================================
    # Volume
    # ==================================================

    bid_volume: float = 0.0

    ask_volume: float = 0.0

    total_volume: float = 0.0

    delta: float = 0.0

    delta_percent: float = 0.0

    # ==================================================
    # Order Flow
    # ==================================================

    imbalance: bool = False

    stacked_imbalance: bool = False

    absorption: bool = False

    exhaustion: bool = False

    finished_auction: bool = False

    unfinished_auction: bool = False

    buying_aggression: float = 0.0

    selling_aggression: float = 0.0

    # ==================================================
    # Advanced Institutional Features
    # ==================================================

    buy_imbalances: int = 0

    sell_imbalances: int = 0

    absorption_levels: int = 0

    exhaustion_levels: int = 0

    iceberg_detected: bool = False

    trapped_buyers: bool = False

    trapped_sellers: bool = False

    # ==================================================
    # Institutional Analysis
    # ==================================================

    confidence: float = 0.0

    score: float = 0.0

    institutional_score: float = 0.0

    # ==================================================
    # Price Levels
    # ==================================================

    levels: list[PriceLevel] = field(
        default_factory=list,
    )

    # ==================================================
    # Metadata
    # ==================================================

    reasons: list[str] = field(
        default_factory=list,
    )

    metadata: dict = field(
        default_factory=dict,
    )

    # ==================================================

    def add_level(

        self,

        level: PriceLevel,

    ):

        self.levels.append(level)

    # --------------------------------------------------

    def update(self):

        self.total_volume = (

            self.bid_volume

            + self.ask_volume

        )

        self.delta = (

            self.ask_volume

            - self.bid_volume

        )

        if self.total_volume > 0:

            self.delta_percent = (

                self.delta

                / self.total_volume

            ) * 100.0

            self.buying_aggression = (

                self.ask_volume

                / self.total_volume

            )

            self.selling_aggression = (

                self.bid_volume

                / self.total_volume

            )

        else:

            self.delta_percent = 0.0

            self.buying_aggression = 0.0

            self.selling_aggression = 0.0

        self.score = min(

            abs(self.delta_percent),

            100.0,

        )

        self.institutional_score = self.score

        self.confidence = self.score / 100.0

    # --------------------------------------------------

    def bullish(self):

        return self.delta > 0

    # --------------------------------------------------

    def bearish(self):

        return self.delta < 0

    # --------------------------------------------------

    def net_aggression(self):

        return (

            self.buying_aggression

            - self.selling_aggression

        )

    # --------------------------------------------------

    def institutional_bias(self):

        if self.delta_percent >= 30:

            return "BULLISH"

        if self.delta_percent <= -30:

            return "BEARISH"

        return "NEUTRAL"

    # --------------------------------------------------

    def add_reason(

        self,

        reason: str,

    ):

        if reason not in self.reasons:

            self.reasons.append(reason)

    # --------------------------------------------------

    def reset(self):

        self.bid_volume = 0.0

        self.ask_volume = 0.0

        self.total_volume = 0.0

        self.delta = 0.0

        self.delta_percent = 0.0

        self.imbalance = False

        self.stacked_imbalance = False

        self.absorption = False

        self.exhaustion = False

        self.finished_auction = False

        self.unfinished_auction = False

        self.buying_aggression = 0.0

        self.selling_aggression = 0.0

        self.buy_imbalances = 0

        self.sell_imbalances = 0

        self.absorption_levels = 0

        self.exhaustion_levels = 0

        self.iceberg_detected = False

        self.trapped_buyers = False

        self.trapped_sellers = False

        self.confidence = 0.0

        self.score = 0.0

        self.institutional_score = 0.0

        self.levels.clear()

        self.reasons.clear()

        self.metadata.clear()