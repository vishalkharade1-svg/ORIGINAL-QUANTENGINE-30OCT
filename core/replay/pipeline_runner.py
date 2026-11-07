"""
====================================================

QuantEngine

Replay Pipeline Runner

ReplayEngine
      │
      ▼
EventBus
      │
      ▼
InstitutionalPipeline
      │
      ▼
Registered Engines

====================================================
"""

from core.events.event_bus import EventBus
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.replay.replay_engine import ReplayEngine


class PipelineRunner:

    def __init__(
        self,
        replay: ReplayEngine,
        pipeline: InstitutionalPipeline,
        event_bus: EventBus | None = None,
    ):

        self.replay = replay

        self.pipeline = pipeline

        self.event_bus = event_bus or EventBus()

        # Connect pipeline to event bus
        self.pipeline.subscribe(
            self.event_bus
        )

        # Replay publishes CandleEvents
        self.replay.event_bus = self.event_bus

    # -------------------------------------------------

    def run(self):

        while not self.replay.finished():

            self.replay.next()

            self.event_bus.dispatch()