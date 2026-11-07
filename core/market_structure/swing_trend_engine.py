"""
====================================================

QuantEngine

Swing-Structure Trend Engine

NOT currently registered in InstitutionalPipeline.
This is a distinct, swing/HH-HL-LH-LL-based trend
classifier -- separate from the canonical, registered
core.trend.trend_engine.TrendEngine, which classifies
trend from IndicatorCache (EMA alignment, ADX, etc).

This class was previously also named "TrendEngine" and
both wrote to PipelineContext.trend using two different
TrendState classes. That collision meant that whichever
one ran last would silently overwrite context.trend with
an incompatible object shape for every downstream
consumer (RegimeEngine, TradeSetupBuilder,
DisplacementScanner's trend_alignment, etc). Renamed here
to remove that risk.

If this engine is wired into the pipeline in the future,
it must NOT write to context.trend directly -- it should
publish to its own context field (e.g. context.swing_trend)
until/unless the two trend models are formally reconciled.

Consumes:
    PipelineContext.swings

Produces (if ever registered):
    A distinct context field, not PipelineContext.trend --
    see note above.

====================================================
"""

from core.common.base_engine import BaseEngine

from core.enums import TrendType

from core.market_structure.trend import TrendState


class SwingStructureTrendEngine(BaseEngine):

    # -------------------------------------------------
    # Pipeline Metadata
    # -------------------------------------------------

    priority = 110

    dependencies = [
        "SwingEngine",
    ]

    enabled = True

    # -------------------------------------------------

    def __init__(self):

        super().__init__()

        self.state = TrendState()

    # -------------------------------------------------
    # Pipeline Entry
    # -------------------------------------------------

    def analyze(self, context):

        registry = context.swings

        if registry is None:

            return

        # Deliberately NOT context.trend -- see module docstring.
        context.swing_trend = self.update(registry)

    # -------------------------------------------------
    # Trend Calculation
    # -------------------------------------------------

    def update(self, registry):

        swings = registry.all()

        highs = [

            swing

            for swing in swings

            if swing.kind == "HIGH"

        ]

        lows = [

            swing

            for swing in swings

            if swing.kind == "LOW"

        ]

        # ---------------------------------------------
        # Higher High / Lower High
        # ---------------------------------------------

        if len(highs) >= 2:

            previous = highs[-2]

            current = highs[-1]

            self.state.last_high = current.price

            if current.price > previous.price:

                self.state.higher_highs += 1

            elif current.price < previous.price:

                self.state.lower_highs += 1

        # ---------------------------------------------
        # Higher Low / Lower Low
        # ---------------------------------------------

        if len(lows) >= 2:

            previous = lows[-2]

            current = lows[-1]

            self.state.last_low = current.price

            if current.price > previous.price:

                self.state.higher_lows += 1

            elif current.price < previous.price:

                self.state.lower_lows += 1

        hh = self.state.higher_highs

        hl = self.state.higher_lows

        lh = self.state.lower_highs

        ll = self.state.lower_lows

        # ---------------------------------------------
        # Determine Trend
        # ---------------------------------------------

        if hh > lh and hl > ll:

            self.state.trend = TrendType.BULLISH

        elif lh > hh and ll > hl:

            self.state.trend = TrendType.BEARISH

        else:

            self.state.trend = TrendType.RANGE

        return self.state

    # -------------------------------------------------

    def reset(self):

        self.state = TrendState()