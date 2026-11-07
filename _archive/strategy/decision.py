"""
====================================================

QuantEngine

Sprint 6

Trade Decision

====================================================
"""

from dataclasses import dataclass


@dataclass
class TradeDecision:

    action: str

    confidence: str

    score: int

    reasons: list

    strategy: str