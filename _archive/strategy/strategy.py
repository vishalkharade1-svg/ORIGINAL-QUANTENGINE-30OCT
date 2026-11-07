"""
====================================================

QuantEngine

Sprint 5

Trading Strategy

====================================================
"""

from dataclasses import dataclass


@dataclass
class Strategy:

    name: str

    weights: dict

    enabled: list

    risk: float