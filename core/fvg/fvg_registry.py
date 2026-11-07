"""
====================================================

QuantEngine

Fair Value Gap Registry

====================================================
"""

from core.common.base_registry import BaseRegistry


class FVGRegistry(BaseRegistry):

    # ==================================================
    # State
    # ==================================================

    def active(self):

        return [

            gap

            for gap in self.all()

            if gap.active

        ]

    # --------------------------------------------------

    def inactive(self):

        return [

            gap

            for gap in self.all()

            if not gap.active

        ]

    # --------------------------------------------------

    def filled(self):

        return [

            gap

            for gap in self.all()

            if gap.filled

        ]

    # --------------------------------------------------

    def unfilled(self):

        return [

            gap

            for gap in self.all()

            if not gap.filled

        ]

    # --------------------------------------------------

    def partial(self):

        return [

            gap

            for gap in self.all()

            if gap.partially_filled

        ]

    # --------------------------------------------------

    def invalidated(self):

        return [

            gap

            for gap in self.all()

            if gap.invalidated

        ]

    # ==================================================
    # Direction
    # ==================================================

    def bullish(self):

        return [

            gap

            for gap in self.all()

            if gap.direction == "BULLISH"

        ]

    # --------------------------------------------------

    def bearish(self):

        return [

            gap

            for gap in self.all()

            if gap.direction == "BEARISH"

        ]

    # ==================================================
    # Queries
    # ==================================================

    def latest(self):

        gaps = self.all()

        if not gaps:

            return None

        return max(

            gaps,

            key=lambda gap: gap.timestamp,

        )

    # --------------------------------------------------

    def strongest(self):

        gaps = self.active()

        if not gaps:

            return None

        return max(

            gaps,

            key=lambda gap: gap.score,

        )

    # --------------------------------------------------

    def nearest(

        self,

        price,

        direction=None,

    ):

        gaps = self.active()

        if direction is not None:

            gaps = [

                gap

                for gap in gaps

                if gap.direction == direction

            ]

        if not gaps:

            return None

        return min(

            gaps,

            key=lambda gap: min(

                abs(gap.upper - price),

                abs(gap.lower - price),

            ),

        )

    # ==================================================

    def reset(self):

        self.clear()