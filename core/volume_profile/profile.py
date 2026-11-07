"""
====================================================

Institutional Volume Profile

====================================================
"""

from dataclasses import dataclass, field

from core.volume_profile.volume_node import VolumeNode


@dataclass(slots=True)
class VolumeProfile:

    # ==================================================
    # Core Levels
    # ==================================================

    poc: float | None = None

    vah: float | None = None

    val: float | None = None

    developing_poc: float | None = None

    naked_poc: bool = False

    # ==================================================
    # Volume
    # ==================================================

    total_volume: float = 0.0

    buy_volume: float = 0.0

    sell_volume: float = 0.0

    delta: float = 0.0

    # ==================================================
    # Nodes
    # ==================================================

    nodes: list[VolumeNode] = field(

        default_factory=list,

    )

    hvn: list[float] = field(

        default_factory=list,

    )

    lvn: list[float] = field(

        default_factory=list,

    )

    # ==================================================
    # Statistics
    # ==================================================

    total_trades: int = 0

    node_count: int = 0

    value_area_percent: float = 70.0

    # ==================================================
    # Institutional State
    # ==================================================

    balanced: bool = False

    trend_day: bool = False

    neutral_day: bool = False

    double_distribution: bool = False

    poor_high: bool = False

    poor_low: bool = False

    # ==================================================
    # Strength
    # ==================================================

    score: float = 0.0

    confidence: float = 0.0

    # ==================================================

    def reset(self):

        self.poc = None

        self.vah = None

        self.val = None

        self.developing_poc = None

        self.naked_poc = False

        self.total_volume = 0.0

        self.buy_volume = 0.0

        self.sell_volume = 0.0

        self.delta = 0.0

        self.total_trades = 0

        self.node_count = 0

        self.score = 0.0

        self.confidence = 0.0

        self.balanced = False

        self.trend_day = False

        self.neutral_day = False

        self.double_distribution = False

        self.poor_high = False

        self.poor_low = False

        self.nodes.clear()

        self.hvn.clear()

        self.lvn.clear()

    # --------------------------------------------------

    def update(self):

        self.node_count = len(self.nodes)

        self.buy_volume = sum(

            node.buy_volume

            for node in self.nodes

        )

        self.sell_volume = sum(

            node.sell_volume

            for node in self.nodes

        )

        self.total_volume = (

            self.buy_volume

            + self.sell_volume

        )

        self.delta = (

            self.buy_volume

            - self.sell_volume

        )

        self.total_trades = sum(

            node.trades

            for node in self.nodes

        )

    # --------------------------------------------------

    def bullish(self):

        return self.delta > 0

    # --------------------------------------------------

    def bearish(self):

        return self.delta < 0