"""
====================================================

QuantEngine

Order Block Registry

====================================================
"""

from core.common.base_registry import BaseRegistry


class OrderBlockRegistry(BaseRegistry):

    # ==================================================
    # State
    # ==================================================

    def active(self):

        return [

            block

            for block in self.all()

            if block.active

        ]

    # --------------------------------------------------

    def inactive(self):

        return [

            block

            for block in self.all()

            if not block.active

        ]

    # --------------------------------------------------

    def mitigated(self):

        return [

            block

            for block in self.all()

            if block.mitigated

        ]

    # --------------------------------------------------

    def unmitigated(self):

        return [

            block

            for block in self.all()

            if not block.mitigated

        ]

    # --------------------------------------------------

    def invalidated(self):

        return [

            block

            for block in self.all()

            if block.invalidated

        ]

    # ==================================================
    # Direction
    # ==================================================

    def bullish(self):

        return [

            block

            for block in self.all()

            if block.direction == "BULLISH"

        ]

    # --------------------------------------------------

    def bearish(self):

        return [

            block

            for block in self.all()

            if block.direction == "BEARISH"

        ]

    # ==================================================
    # Queries
    # ==================================================

    def latest(self):

        blocks = self.all()

        if not blocks:

            return None

        return max(

            blocks,

            key=lambda block: block.timestamp,

        )

    # --------------------------------------------------

    def strongest(self):

        blocks = self.active()

        if not blocks:

            return None

        return max(

            blocks,

            key=lambda block: block.score,

        )

    # --------------------------------------------------

    def nearest(

        self,

        price,

        direction=None,

    ):

        blocks = self.active()

        if direction is not None:

            blocks = [

                block

                for block in blocks

                if block.direction == direction

            ]

        if not blocks:

            return None

        return min(

            blocks,

            key=lambda block: abs(

                block.close - price

            ),

        )

    # ==================================================

    def reset(self):

        self.clear()