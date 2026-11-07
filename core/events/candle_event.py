"""
====================================================

QuantEngine

Candle Event

====================================================
"""

from dataclasses import dataclass

from core.events.event import Event
from core.events.event_types import EventType
from core.history.candle import Candle


@dataclass(slots=True)
class CandleEvent(Event):
    """
    Event published whenever a candle is completed.

    Used by both Replay and Live data pipelines.
    """

    event_type: str = EventType.CANDLE

    candle: Candle | None = None

    symbol: str = ""

    timeframe: str = ""