"""
====================================================

QuantEngine

Institutional Price Ladder

Represents the complete price ladder for a candle.

====================================================
"""

from dataclasses import dataclass, field

from core.orderflow.price_level import PriceLevel


@dataclass(slots=True)
class PriceLadder:

    # ==================================================
    # Identification
    # ==================================================

    candle_index: int = 0

    timestamp: int = 0

    timeframe: str = ""

    # ==================================================
    # Price Levels
    # ==================================================

    levels: list[PriceLevel] = field(

        default_factory=list,

    )

    # ==================================================
    # Volume Profile
    # ==================================================

    poc: float = 0.0

    vah: float = 0.0

    val: float = 0.0

    total_volume: float = 0.0

    total_delta: float = 0.0

    # ==================================================
    # Extremes
    # ==================================================

    max_buy_volume: float = 0.0

    max_sell_volume: float = 0.0

    strongest_level: PriceLevel | None = None

    weakest_level: PriceLevel | None = None

    # ==================================================
    # Institutional Statistics
    # ==================================================

    buying_pressure: float = 0.0

    selling_pressure: float = 0.0

    imbalance: float = 0.0

    absorption: bool = False

    exhaustion: bool = False

    stacked_imbalance: bool = False

    balanced: bool = False

    score: float = 0.0

    confidence: float = 0.0

    # ==================================================
    # Metadata
    # ==================================================

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

        if not self.levels:

            return

        self.total_volume = sum(

            level.total_volume

            for level in self.levels

        )

        self.total_delta = sum(

            level.delta

            for level in self.levels

        )

        self.max_buy_volume = max(

            level.buy_volume

            for level in self.levels

        )

        self.max_sell_volume = max(

            level.sell_volume

            for level in self.levels

        )

        self.strongest_level = max(

            self.levels,

            key=lambda level: level.total_volume,

        )

        self.weakest_level = min(

            self.levels,

            key=lambda level: level.total_volume,

        )

        if self.total_volume > 0:

            self.buying_pressure = (

                sum(

                    level.buy_volume

                    for level in self.levels

                )

                / self.total_volume

            )

            self.selling_pressure = (

                sum(

                    level.sell_volume

                    for level in self.levels

                )

                / self.total_volume

            )

            self.imbalance = (

                abs(self.total_delta)

                / self.total_volume

            ) * 100.0

        self.balanced = (

            abs(

                self.buying_pressure

                - self.selling_pressure

            ) < 0.10

        )

    # --------------------------------------------------

    def reset(self):

        self.levels.clear()

        self.poc = 0.0
        self.vah = 0.0
        self.val = 0.0

        self.total_volume = 0.0
        self.total_delta = 0.0

        self.max_buy_volume = 0.0
        self.max_sell_volume = 0.0

        self.strongest_level = None
        self.weakest_level = None

        self.buying_pressure = 0.0
        self.selling_pressure = 0.0

        self.imbalance = 0.0

        self.absorption = False
        self.exhaustion = False
        self.stacked_imbalance = False
        self.balanced = False

        self.score = 0.0
        self.confidence = 0.0

        self.metadata.clear()