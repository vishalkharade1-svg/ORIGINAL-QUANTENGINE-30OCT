"""
====================================================

QuantEngine

Institutional Base Score Engine

====================================================
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from core.objects.market_object import MarketObject


class ScoreEngine(ABC):

    def score(

        self,

        obj: MarketObject,

    ) -> float:

        score = self.calculate(obj)

        score = max(

            0.0,

            min(

                100.0,

                score,

            ),

        )

        obj.score = score

        if hasattr(obj, "quality"):
            obj.quality = score

        # Compatibility ranking label, NOT a calibrated likelihood. Existing
        # threshold gates consume it as a heuristic score bucket only.
        if hasattr(obj, "confidence"):
            obj.confidence = self.confidence(score)
        # Do not let a score transform silently masquerade as probability.
        # Objects that support calibrated prediction carry this separate field.
        if hasattr(obj, "calibrated_probability"):
            obj.calibrated_probability = None

        return score

    @abstractmethod
    def calculate(

        self,

        obj: MarketObject,

    ) -> float:

        ...

    @staticmethod
    def confidence(

        score: float,

    ) -> float:

        if score >= 95:
            return 99

        if score >= 90:
            return 97

        if score >= 80:
            return 94

        if score >= 70:
            return 90

        if score >= 60:
            return 80

        if score >= 50:
            return 70

        return 50
