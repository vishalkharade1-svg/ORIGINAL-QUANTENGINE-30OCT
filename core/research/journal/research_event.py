"""
====================================================

QuantEngine

Research Journal -- event (Phase 9A)

A deterministic, immutable lifecycle event. Events are NOT
random; each carries a deterministic event_id derived from a
per-journal sequence + bar + provenance so identical inputs
produce identical event streams (Phase 9A determinism).

The journal is an OBSERVER: it emits events describing what
actually happened. It holds NO execution authority and never
mutates an order, setup, strategy, risk or portfolio state.
====================================================
"""

from dataclasses import dataclass, field

from core.research.journal.research_enums import Provenance, EventType


@dataclass
class ResearchEvent:
    """A single observed lifecycle event."""

    event_id: str
    provenance: str
    event_type: str
    bar: int
    timestamp: object
    canonical_id: str = ""
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""
    order_id: str = ""
    payload: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "provenance": str(self.provenance),
            "event_type": str(self.event_type),
            "bar": self.bar,
            "timestamp": self.timestamp,
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "order_id": self.order_id,
            "payload": dict(self.payload),
        }

    @property
    def kind(self):
        # `event_type` may already be an EventType member or a str.
        return (
            self.event_type.value
            if isinstance(self.event_type, EventType)
            else str(self.event_type)
        )
