"""
====================================================

QuantEngine

Institutional Delta Signal

====================================================
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class DeltaSignal:

    # ==================================================
    # Directional Signals
    # ==================================================

    bullish_divergence: bool = False

    bearish_divergence: bool = False

    buying_exhaustion: bool = False

    selling_exhaustion: bool = False

    increasing_delta: bool = False

    decreasing_delta: bool = False

    strong_buying: bool = False

    strong_selling: bool = False

    # ==================================================
    # Institutional Signals
    # ==================================================

    absorption: bool = False

    trapped_buyers: bool = False

    trapped_sellers: bool = False

    aggressive_buying: bool = False

    aggressive_selling: bool = False

    imbalance_buy: bool = False

    imbalance_sell: bool = False

    # ==================================================
    # Scoring
    # ==================================================

    score: float = 0.0

    confidence: float = 0.0

    institutional_score: float = 0.0

    # ==================================================
    # State
    # ==================================================

    confirmed: bool = True

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

    def bullish(self):

        return any(

            (

                self.bullish_divergence,

                self.strong_buying,

                self.aggressive_buying,

                self.imbalance_buy,

            )

        )

    # --------------------------------------------------

    def bearish(self):

        return any(

            (

                self.bearish_divergence,

                self.strong_selling,

                self.aggressive_selling,

                self.imbalance_sell,

            )

        )

    # --------------------------------------------------

    def reset(self):

        self.__init__()