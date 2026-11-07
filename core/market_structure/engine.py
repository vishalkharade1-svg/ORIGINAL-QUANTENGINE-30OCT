"""
====================================================

QuantEngine

Institutional Market Structure Engine

Pipeline Aggregation Engine

Consumes:
    PipelineContext.swings
    PipelineContext.trend
    PipelineContext.structure_events
    PipelineContext.bos
    PipelineContext.choch

Produces:
    PipelineContext.market.structure

====================================================
"""

from core.common.base_engine import BaseEngine

from core.enums import StructureType
from core.market_structure.state import MarketStructureState


class MarketStructureEngine(BaseEngine):

    priority = 150

    dependencies = [
        "SwingEngine",
        "TrendEngine",
        "StructureEngine",
        "BOSEngine",
        "CHoCHEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.state = MarketStructureState()

    # -------------------------------------------------

    def analyze(self, context):

        state = self.state

        # ---------------------------------------------
        # Reset cycle state
        # ---------------------------------------------

        state.signals.clear()

        state.bos = False
        state.choch = False

        state.last_bos = StructureType.NONE
        state.last_choch = StructureType.NONE

        # ---------------------------------------------
        # Read Pipeline Outputs
        # ---------------------------------------------

        registry = context.swings

        trend = context.trend

        structure_events = context.structure_events

        bos_events = context.bos

        choch_events = context.choch

        # ---------------------------------------------
        # Trend
        # ---------------------------------------------

        if trend is not None:

            state.trend = trend.direction

            state.internal_trend = trend.direction

            state.external_trend = trend.direction

        # ---------------------------------------------
        # Structure
        # ---------------------------------------------

        state.structure_events = structure_events or []

        if structure_events:

            state.structure = " ".join(

                event.kind.value

                for event in structure_events[-10:]

            )

            state.last_structure = structure_events[-1].kind

        else:

            state.structure = ""

            state.last_structure = StructureType.NONE

        # ---------------------------------------------
        # BOS
        # ---------------------------------------------

        if bos_events:

            latest = bos_events[-1]

            state.bos = True

            state.last_bos = StructureType.BOS

            state.signals.append(

                f"{latest.direction}_BOS"

            )

        # ---------------------------------------------
        # CHOCH
        # ---------------------------------------------

        if choch_events:

            latest = choch_events[-1]

            state.choch = True

            state.last_choch = StructureType.CHOCH

            state.signals.append(

                f"{latest.direction}_CHOCH"

            )

        # ---------------------------------------------
        # Swing Levels
        # ---------------------------------------------

        if registry is not None:

            highs = registry.highs()

            lows = registry.lows()

            if highs:

                state.major_high = highs[-1].price

                state.internal_high = highs[-1].price

            else:

                state.major_high = None

                state.internal_high = None

            if lows:

                state.major_low = lows[-1].price

                state.internal_low = lows[-1].price

            else:

                state.major_low = None

                state.internal_low = None

        # ---------------------------------------------
        # Publish Aggregated State
        # ---------------------------------------------

        context.market_structure = state

    # -------------------------------------------------

    def reset(self):

        self.state = MarketStructureState()