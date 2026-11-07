"""
====================================================

QuantEngine

Build : 3.2
Module : Trading Signal

Represents a strategy signal.

====================================================
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:

    action: str
    strategy: str
    confidence: float
    reason: str

    price: Optional[float] = None
    timestamp: Optional[int] = None