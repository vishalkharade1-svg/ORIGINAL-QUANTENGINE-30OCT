"""
====================================================

QuantEngine

Build : 4.3
Module : Market Structure Labels

====================================================
"""

from dataclasses import dataclass


@dataclass
class StructurePoint:

    swing: object

    label: str