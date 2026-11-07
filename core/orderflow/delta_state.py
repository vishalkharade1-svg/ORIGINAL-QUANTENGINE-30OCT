"""
====================================================

QuantEngine

Institutional Delta State

Shared runtime state for Order Flow analysis.

====================================================
"""

from dataclasses import dataclass, field

from core.orderflow.delta import Delta
from core.orderflow.delta_signal import DeltaSignal


@dataclass(slots=True)
class DeltaState:

    # ==================================================
    # Core Objects
    # ==================================================

    delta: Delta | None = None

    signal: DeltaSignal | None = None

    # ==================================================
    # Runtime Status
    # ==================================================

    healthy: bool = False

    ready: bool = False

    updated: bool = False

    source: str = ""

    # ==================================================
    # Statistics
    # ==================================================

    processed_candles: int = 0

    cumulative_buy_volume: float = 0.0

    cumulative_sell_volume: float = 0.0

    cumulative_delta: float = 0.0

    average_delta: float = 0.0

    # ==================================================
    # Institutional State
    # ==================================================

    institutional_bias: str = "NEUTRAL"

    confidence: float = 0.0

    # ==================================================
    # Metadata
    # ==================================================

    metadata: dict = field(
        default_factory=dict,
    )

    # ==================================================

    def reset(self):

        self.delta = None

        self.signal = None

        self.healthy = False

        self.ready = False

        self.updated = False

        self.source = ""

        self.processed_candles = 0

        self.cumulative_buy_volume = 0.0

        self.cumulative_sell_volume = 0.0

        self.cumulative_delta = 0.0

        self.average_delta = 0.0

        self.institutional_bias = "NEUTRAL"

        self.confidence = 0.0

        self.metadata.clear()

    # --------------------------------------------------

    def update_statistics(self):

        if self.delta is None:

            return

        self.processed_candles += 1

        self.cumulative_buy_volume += self.delta.buy_volume

        self.cumulative_sell_volume += self.delta.sell_volume

        self.cumulative_delta = self.delta.cumulative_delta

        if self.processed_candles:

            self.average_delta = (

                self.cumulative_delta

                / self.processed_candles

            )

        self.confidence = self.delta.confidence

    # --------------------------------------------------

    @property
    def bullish(self):

        if self.signal is None:

            return False

        return (

            self.signal.strong_buying

            or self.signal.increasing_delta

            or self.signal.bullish_divergence

        )

    # --------------------------------------------------

    @property
    def bearish(self):

        if self.signal is None:

            return False

        return (

            self.signal.strong_selling

            or self.signal.decreasing_delta

            or self.signal.bearish_divergence

        )