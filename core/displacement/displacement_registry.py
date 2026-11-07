"""
====================================================

QuantEngine

Institutional Displacement Registry

====================================================
"""

from core.common.base_registry import BaseRegistry


class DisplacementRegistry(BaseRegistry):

    # ==================================================
    # Strength
    # ==================================================

    def strong(self):

        return [

            event

            for event in self.all()

            if event.strong

        ]

    # --------------------------------------------------

    def weak(self):

        return [

            event

            for event in self.all()

            if not event.strong

        ]

    # ==================================================
    # Direction
    # ==================================================

    def bullish(self):

        return [

            event

            for event in self.all()

            if event.direction == "BULLISH"

        ]

    # --------------------------------------------------

    def bearish(self):

        return [

            event

            for event in self.all()

            if event.direction == "BEARISH"

        ]

    # ==================================================
    # State
    # ==================================================

    def active(self):

        return [

            event

            for event in self.all()

            if event.active

        ]

    # --------------------------------------------------

    def inactive(self):

        return [

            event

            for event in self.all()

            if not event.active

        ]

    # ==================================================
    # Queries
    # ==================================================

    def latest(self):

        events = self.all()

        if not events:

            return None

        return max(

            events,

            key=lambda event: event.timestamp,

        )

    # --------------------------------------------------

    def strongest(self):

        events = self.strong()

        if not events:

            return None

        return max(

            events,

            key=lambda event: event.score,

        )

    # ==================================================

    def reset(self):

        self.clear()