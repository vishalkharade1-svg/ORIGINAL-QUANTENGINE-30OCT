"""
====================================================

QuantEngine

Institutional Delta Registry

====================================================
"""

from core.common.base_registry import BaseRegistry


class DeltaRegistry(BaseRegistry):

    # ==================================================
    # Navigation
    # ==================================================

    def latest(self):

        history = self.all()

        if not history:

            return None

        return history[-1]

    # --------------------------------------------------

    def previous(self):

        history = self.all()

        if len(history) < 2:

            return None

        return history[-2]

    # --------------------------------------------------

    def last(

        self,

        count: int,

    ):

        if count <= 0:

            return []

        return self.all()[-count:]

    # ==================================================
    # Statistics
    # ==================================================

    def cumulative(self):

        latest = self.latest()

        if latest is None:

            return 0.0

        return latest.cumulative_delta

    # --------------------------------------------------

    def average_delta(self):

        history = self.all()

        if not history:

            return 0.0

        return (

            sum(

                d.delta

                for d in history

            )

            / len(history)

        )

    # --------------------------------------------------

    def max_delta(self):

        history = self.all()

        if not history:

            return 0.0

        return max(

            d.delta

            for d in history

        )

    # --------------------------------------------------

    def min_delta(self):

        history = self.all()

        if not history:

            return 0.0

        return min(

            d.delta

            for d in history

        )

    # ==================================================
    # Queries
    # ==================================================

    def bullish(self):

        return [

            delta

            for delta in self.all()

            if delta.delta > 0

        ]

    # --------------------------------------------------

    def bearish(self):

        return [

            delta

            for delta in self.all()

            if delta.delta < 0

        ]

    # --------------------------------------------------

    def strongest_buying(self):

        bullish = self.bullish()

        if not bullish:

            return None

        return max(

            bullish,

            key=lambda d: d.delta,

        )

    # --------------------------------------------------

    def strongest_selling(self):

        bearish = self.bearish()

        if not bearish:

            return None

        return min(

            bearish,

            key=lambda d: d.delta,

        )

    # ==================================================

    def reset(self):

        self.clear()