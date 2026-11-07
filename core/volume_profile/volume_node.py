"""
====================================================

QuantEngine

Institutional Volume Node

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class VolumeNode:

    # ==================================================
    # Price
    # ==================================================

    price: float

    # ==================================================
    # Volume
    # ==================================================

    volume: float = 0.0

    buy_volume: float = 0.0

    sell_volume: float = 0.0

    delta: float = 0.0

    trades: int = 0

    # ==================================================
    # Statistics
    # ==================================================

    percentage: float = 0.0

    cumulative_volume: float = 0.0

    # ==================================================
    # Institutional Classification
    # ==================================================

    hvn: bool = False          # High Volume Node

    lvn: bool = False          # Low Volume Node

    poc: bool = False          # Point Of Control

    value_area: bool = False

    buying_node: bool = False

    selling_node: bool = False

    # ==================================================
    # Order Flow
    # ==================================================

    imbalance: float = 0.0

    absorption: bool = False

    exhaustion: bool = False

    stacked_imbalance: bool = False

    # ==================================================
    # Institutional Quality
    # ==================================================

    score: float = 0.0

    confidence: float = 0.0

    # ==================================================

    def update(self):

        self.delta = (

            self.buy_volume

            - self.sell_volume

        )

        self.volume = (

            self.buy_volume

            + self.sell_volume

        )

        if self.volume > 0:

            self.imbalance = (

                abs(self.delta)

                / self.volume

            )

        else:

            self.imbalance = 0.0

    # --------------------------------------------------

    def bullish(self):

        return self.delta > 0

    # --------------------------------------------------

    def bearish(self):

        return self.delta < 0

    # --------------------------------------------------

    def reset_flags(self):

        self.hvn = False

        self.lvn = False

        self.poc = False

        self.value_area = False

        self.buying_node = False

        self.selling_node = False

        self.absorption = False

        self.exhaustion = False

        self.stacked_imbalance = False

        self.score = 0.0

        self.confidence = 0.0