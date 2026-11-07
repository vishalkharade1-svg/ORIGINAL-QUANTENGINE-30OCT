"""
====================================================

Price Ladder Pipeline Stage

Not currently registered in InstitutionalPipeline.
Part of the future order-flow/footprint work
(see docs section 24). Kept for when that subsystem
is wired in, using the canonical engine contract so
it doesn't drift into its own generation.

Consumes:
    context.latest_candle
    context.cumulative_delta

Produces:
    context.price_ladder

====================================================
"""

from core.common.base_engine import BaseEngine
from core.orderflow.price_ladder_engine import PriceLadderEngine


class PriceLadderStage(BaseEngine):

    priority = 90

    dependencies = [
        "CumulativeDelta",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.engine = PriceLadderEngine()

    # -------------------------------------------------

    def validate(self, context):

        return (
            hasattr(context, "latest_candle")
            and hasattr(context, "cumulative_delta")
        )

    # -------------------------------------------------

    def analyze(self, context):

        context.price_ladder = self.engine.process(context)

    # -------------------------------------------------

    def reset(self):

        pass
