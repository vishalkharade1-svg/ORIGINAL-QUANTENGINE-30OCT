"""
====================================================

QuantEngine

Institutional Delta

Represents cumulative order-flow statistics for
a single candle.

====================================================
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Delta:

    # ==================================================
    # Identification
    # ==================================================

    candle_index: int = 0

    timestamp: int = 0

    timeframe: str = ""

    # ==================================================
    # Volume
    # ==================================================

    buy_volume: float = 0.0

    sell_volume: float = 0.0

    total_volume: float = 0.0

    # ==================================================
    # Delta
    # ==================================================

    delta: float = 0.0

    cumulative_delta: float = 0.0

    delta_percent: float = 0.0

    # ==================================================
    # Aggression
    # ==================================================

    buy_aggression: float = 0.0

    sell_aggression: float = 0.0

    imbalance: float = 0.0

    # ==================================================
    # Data Quality
    # ==================================================

    mode: str = "ESTIMATED"

    confidence: float = 0.0

    # ==================================================
    # State
    # ==================================================

    confirmed: bool = True

    active: bool = True

    # ==================================================
    # Metadata
    # ==================================================

    metadata: dict = field(

        default_factory=dict,

    )

    # ==================================================

    def update_totals(self):

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

        self.buy_aggression = 0.0

        self.sell_aggression = 0.0

        self.imbalance = 0.0

        self.metadata.clear()