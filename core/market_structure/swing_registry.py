"""
====================================================

Institutional Swing Registry

====================================================
"""

from core.registry.indexed_registry import IndexedRegistry
from core.market_structure.swing import Swing


class SwingRegistry(IndexedRegistry[Swing]):

    def highs(self):

        return [

            s

            for s in self.active()

            if s.kind == "HIGH"

        ]

    def lows(self):

        return [

            s

            for s in self.active()

            if s.kind == "LOW"

        ]

    def confirmed(self):

        return [

            s

            for s in self.active()

            if s.confirmed

        ]

    def confirmed_as_of(self, bar):
        """Swings confirmed at or before absolute bar `bar`.

        Phase 12 causality helper: a swing is actionable only
        once its right-side confirmation window has closed
        (confirmed_bar <= bar). Unstamped legacy swings
        (confirmed_bar 0) are excluded -- confirmation unknown
        means unusable, never assumed. Deterministic pure
        filter over the active set.
        """

        try:
            cutoff = int(bar)
        except (TypeError, ValueError):
            return []

        return [

            s

            for s in self.active()

            if s.confirmed
            and getattr(s, "confirmed_bar", 0)
            and s.confirmed_bar <= cutoff

        ]

    def institutional(self):

        return [

            s

            for s in self.active()

            if s.institutional

        ]

    def majors(self):

        return [

            s

            for s in self.active()

            if s.major

        ]

    def latest(self):

        objects = self.active()

        if not objects:

            return None

        return max(

            objects,

            key=lambda x: x.timestamp,

        )