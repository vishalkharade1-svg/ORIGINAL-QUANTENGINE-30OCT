"""
====================================================

QuantEngine

Institutional Price Level

Footprint / DOM Price Level

====================================================
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class PriceLevel:

    # ==================================================
    # Identification
    # ==================================================

    price: float = 0.0

    timestamp: int = 0

    candle_index: int = 0

    timeframe: str = ""

    # ==================================================
    # Volume
    # ==================================================

    buy_volume: float = 0.0

    sell_volume: float = 0.0

    total_volume: float = 0.0

    trades: int = 0

    # ==================================================
    # Order Flow
    # ==================================================

    delta: float = 0.0

    delta_percent: float = 0.0

    imbalance: float = 0.0

    buy_aggression: float = 0.0

    sell_aggression: float = 0.0

    # ==================================================
    # Institutional Signals
    # ==================================================

    absorption: bool = False

    exhaustion: bool = False

    stacked_imbalance: bool = False

    buying_tail: bool = False

    selling_tail: bool = False

    unfinished_auction: bool = False

    # ==================================================
    # Scoring
    # ==================================================

    score: float = 0.0

    institutional_score: float = 0.0

    # ==================================================
    # Metadata
    # ==================================================

    metadata: dict = field(

        default_factory=dict,

    )

    # ==================================================

    def update(self):

        self.total_volume = (

            self.buy_volume

            + self.sell_volume

        )

        self.delta = (

            self.buy_volume

            - self.sell_volume

        )

        if self.total_volume > 0:

            self.delta_percent = (

                self.delta

                / self.total_volume

            ) * 100.0

        else:

            self.delta_percent = 0.0

    # --------------------------------------------------

    def is_buying(self):

        return self.delta > 0

    # --------------------------------------------------

    def is_selling(self):

        return self.delta < 0

    # --------------------------------------------------

    def reset(self):

        self.buy_volume = 0.0

        self.sell_volume = 0.0

        self.total_volume = 0.0

        self.delta = 0.0

        self.delta_percent = 0.0

        self.trades = 0

        self.imbalance = 0.0

        self.buy_aggression = 0.0

        self.sell_aggression = 0.0

        self.absorption = False

        self.exhaustion = False

        self.stacked_imbalance = False

        self.buying_tail = False

        self.selling_tail = False

        self.unfinished_auction = False

        self.score = 0.0

        self.institutional_score = 0.0

        self.metadata.clear()