"""
====================================================

QuantEngine

Institutional Fair Value Gap Scanner

Pipeline Native

Consumes:
    context.candles
    context.displacement

Produces:
    context.fvgs

====================================================
"""

from core.common.base_engine import BaseEngine

from core.fvg.fair_value_gap import FairValueGap
from core.fvg.fvg_registry import FVGRegistry
from core.fvg.fvg_score import FVGScore


class FVGScanner(BaseEngine):

    priority = 310

    dependencies = [
        "DisplacementScanner",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.registry = FVGRegistry()
        self.scorer = FVGScore()

    # ==================================================

    def analyze(self, context):

        self.registry.clear()

        bars = list(context.candles)

        displacement_registry = context.displacement

        if len(bars) < 3 or displacement_registry is None:

            context.fvgs = self.registry
            return

        strong_events = displacement_registry.strong()

        if not strong_events:

            context.fvgs = self.registry
            return

        # -------------------------------------------------

        for event in strong_events:

            i = event.index

            if i < 2:
                continue

            left = bars[i - 2]
            right = bars[i]

            # =============================================
            # Bullish FVG
            # =============================================

            if event.direction == "BULLISH":

                if right.low <= left.high:
                    continue

                gap = FairValueGap(

                    index=i,

                    timestamp=right.timestamp,

                    timeframe=context.market.timeframe,

                    direction="BULLISH",

                    upper=right.low,

                    lower=left.high,

                    size=right.low - left.high,

                    displacement_strength=event.score,

                    volume_ratio=getattr(
                        event,
                        "volume_ratio",
                        0.0,
                    ),

                    displacement_index=i,

                )

            # =============================================
            # Bearish FVG
            # =============================================

            else:

                if right.high >= left.low:
                    continue

                gap = FairValueGap(

                    index=i,

                    timestamp=right.timestamp,

                    timeframe=context.market.timeframe,

                    direction="BEARISH",

                    upper=left.low,

                    lower=right.high,

                    size=left.low - right.high,

                    displacement_strength=event.score,

                    volume_ratio=getattr(
                        event,
                        "volume_ratio",
                        0.0,
                    ),

                    displacement_index=i,

                )

            self.scorer.calculate(gap)

            self.registry.add(gap)

        context.fvgs = self.registry

    # ==================================================

    def reset(self):

        self.registry.clear()