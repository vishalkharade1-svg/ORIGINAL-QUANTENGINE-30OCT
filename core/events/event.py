"""
====================================================

QuantEngine

Base Event

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class Event:

    timestamp: int = 0

    event_type: str = ""