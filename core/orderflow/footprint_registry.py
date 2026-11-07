"""
====================================================

QuantEngine

Institutional Footprint Registry

====================================================
"""

from core.common.base_registry import BaseRegistry


class FootprintRegistry(BaseRegistry):

    # ==================================================
    # Navigation
    # ==================================================

    def latest(self):

        if self.count() == 0:

            return None

        return self.all()[-1]

    # --------------------------------------------------

    def previous(self):

        if self.count() < 2:

            return None

        return self.all()[-2]

    # --------------------------------------------------

    def last(

        self,

        count: int,

    ):

        if count <= 0:

            return []

        return self.all()[-count:]

    # ==================================================
    # Direction
    # ==================================================

    def bullish(self):

        return [

            fp

            for fp in self.all()

            if fp.delta > 0

        ]

    # --------------------------------------------------

    def bearish(self):

        return [

            fp

            for fp in self.all()

            if fp.delta < 0

        ]

    # ==================================================
    # Order Flow
    # ==================================================

    def imbalances(self):

        return [

            fp

            for fp in self.all()

            if fp.imbalance

        ]

    # --------------------------------------------------

    def stacked_imbalances(self):

        return [

            fp

            for fp in self.all()

            if fp.stacked_imbalance

        ]

    # --------------------------------------------------

    def absorptions(self):

        return [

            fp

            for fp in self.all()

            if fp.absorption

        ]

    # --------------------------------------------------

    def exhaustions(self):

        return [

            fp

            for fp in self.all()

            if fp.exhaustion

        ]

    # --------------------------------------------------

    def iceberg_orders(self):

        return [

            fp

            for fp in self.all()

            if fp.iceberg_detected

        ]

    # --------------------------------------------------

    def trapped_buyers(self):

        return [

            fp

            for fp in self.all()

            if fp.trapped_buyers

        ]

    # --------------------------------------------------

    def trapped_sellers(self):

        return [

            fp

            for fp in self.all()

            if fp.trapped_sellers

        ]

    # ==================================================
    # Institutional Strength
    # ==================================================

    def strongest(self):

        if self.count() == 0:

            return None

        return max(

            self.all(),

            key=lambda fp: fp.institutional_score,

        )

    # --------------------------------------------------

    def weakest(self):

        if self.count() == 0:

            return None

        return min(

            self.all(),

            key=lambda fp: fp.institutional_score,

        )

    # --------------------------------------------------

    def average_score(self):

        if self.count() == 0:

            return 0.0

        return (

            sum(

                fp.institutional_score

                for fp in self.all()

            )

            / self.count()

        )

    # --------------------------------------------------

    def average_delta(self):

        if self.count() == 0:

            return 0.0

        return (

            sum(

                fp.delta

                for fp in self.all()

            )

            / self.count()

        )

    # ==================================================

    def reset(self):

        self.clear()