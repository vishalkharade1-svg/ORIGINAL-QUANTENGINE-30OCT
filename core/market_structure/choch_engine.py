"""
====================================================

QuantEngine

Institutional CHoCH Engine

Pipeline Engine

Consumes:
    PipelineContext.structure_events
    PipelineContext.bos

Produces:
    PipelineContext.choch

====================================================
"""

from dataclasses import dataclass

from core.common.base_engine import BaseEngine


# =====================================================
# CHoCH Event
# =====================================================

@dataclass(slots=True)
class CHoCHEvent:

    direction: str
    level: float
    timestamp: int


# =====================================================
# CHoCH Engine
# =====================================================

class CHoCHEngine(BaseEngine):

    priority = 140

    dependencies = [
        "StructureEngine",
        "BOSEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.events = []
        self.last_bos = None

    # -------------------------------------------------

    def analyze(self, context):

        structure_events = getattr(
            context,
            "structure_events",
            None,
        )

        bos_events = getattr(
            context,
            "bos",
            None,
        )

        context.choch = self.update(
            structure_events,
            bos_events,
        )

    # -------------------------------------------------

    def update(
        self,
        structure_events,
        bos_events,
    ):

        self.events.clear()

        # ---------------------------------------------
        # Nothing to process
        # ---------------------------------------------

        if not bos_events:
            return self.events

        if not structure_events:
            return self.events

        if len(structure_events) == 0:
            return self.events

        latest_bos = bos_events[-1]

        # ---------------------------------------------
        # First BOS establishes market direction
        # ---------------------------------------------

        if self.last_bos is None:

            self.last_bos = latest_bos.direction

            return self.events

        # ---------------------------------------------
        # No change in BOS direction
        # ---------------------------------------------

        if latest_bos.direction == self.last_bos:

            return self.events

        # ---------------------------------------------
        # Create CHoCH
        # ---------------------------------------------

        current = structure_events[-1]

        self.events.append(

            CHoCHEvent(

                direction=latest_bos.direction,

                level=current.price,

                timestamp=current.timestamp,

            )

        )

        self.last_bos = latest_bos.direction

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
            if event.direction == "BULLISH"
        ]

    # -------------------------------------------------

    def bearish(self):

        return [
            event
            for event in self.events
            if event.direction == "BEARISH"
        ]

    # -------------------------------------------------

    def reset(self):

        self.events.clear()

        self.last_bos = None