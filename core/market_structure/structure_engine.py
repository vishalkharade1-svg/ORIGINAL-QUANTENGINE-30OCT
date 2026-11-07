"""
====================================================

QuantEngine

Institutional Structure Engine

Pipeline Engine

Consumes:
    PipelineContext.swings

Produces:
    PipelineContext.structure_events

====================================================
"""

from dataclasses import dataclass

from core.common.base_engine import BaseEngine

from core.enums import StructureType


# =====================================================
# Structure Event
# =====================================================

@dataclass(slots=True)
class StructureEvent:

    kind: StructureType

    price: float

    timestamp: int

    index: int

    timeframe: str


# =====================================================
# Structure Engine
# =====================================================

class StructureEngine(BaseEngine):

    priority = 120

    dependencies = [
        "SwingEngine",
        "TrendEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.events = []

    # -------------------------------------------------
    # Pipeline Entry
    # -------------------------------------------------

    def analyze(self, context):

        registry = context.swings

        if registry is None:
            return

        context.structure_events = self.update(registry)

    # -------------------------------------------------
    # Standalone Analyzer
    # -------------------------------------------------

    def update(
        self,
        registry,
    ):

        self.events.clear()

        swings = sorted(
            registry.all(),
            key=lambda s: s.timestamp,
        )

        last_high = None

        last_low = None

        for swing in swings:

            # -----------------------------------------
            # HIGHS
            # -----------------------------------------

            if swing.kind == "HIGH":

                if last_high is not None:

                    if swing.price > last_high.price:
                        structure = StructureType.HH
                    else:
                        structure = StructureType.LH

                    self.events.append(
                        StructureEvent(
                            kind=structure,
                            price=swing.price,
                            timestamp=swing.timestamp,
                            index=swing.index,
                            timeframe=swing.timeframe,
                        )
                    )

                last_high = swing

                continue

            # -----------------------------------------
            # LOWS
            # -----------------------------------------

            if last_low is not None:

                if swing.price > last_low.price:
                    structure = StructureType.HL
                else:
                    structure = StructureType.LL

                self.events.append(
                    StructureEvent(
                        kind=structure,
                        price=swing.price,
                        timestamp=swing.timestamp,
                        index=swing.index,
                        timeframe=swing.timeframe,
                    )
                )

            last_low = swing

        return list(self.events)

    # -------------------------------------------------

    def latest(self):

        if not self.events:
            return None

        return self.events[-1]

    # -------------------------------------------------

    def bullish(self):

        return [
            event
            for event in self.events
            if event.kind in (
                StructureType.HH,
                StructureType.HL,
            )
        ]

    # -------------------------------------------------

    def bearish(self):

        return [
            event
            for event in self.events
            if event.kind in (
                StructureType.LH,
                StructureType.LL,
            )
        ]

    # -------------------------------------------------

    def reset(self):

        self.events.clear()