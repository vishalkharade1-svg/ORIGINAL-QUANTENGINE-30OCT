"""
====================================================

QuantEngine

Institutional Volume Profile Registry

====================================================
"""

from core.common.base_registry import BaseRegistry


class ProfileRegistry(BaseRegistry):

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
    # Queries
    # ==================================================

    def bullish(self):

        return [

            profile

            for profile in self.all()

            if profile.delta > 0

        ]

    # --------------------------------------------------

    def bearish(self):

        return [

            profile

            for profile in self.all()

            if profile.delta < 0

        ]

    # --------------------------------------------------

    def balanced(self):

        return [

            profile

            for profile in self.all()

            if profile.balanced

        ]

    # --------------------------------------------------

    def trend_days(self):

        return [

            profile

            for profile in self.all()

            if profile.trend_day

        ]

    # --------------------------------------------------

    def strongest(self):

        if self.count() == 0:

            return None

        return max(

            self.all(),

            key=lambda profile: profile.score,

        )

    # --------------------------------------------------

    def average_volume(self):

        if self.count() == 0:

            return 0.0

        return (

            sum(

                profile.total_volume

                for profile in self.all()

            )

            / self.count()

        )

    # --------------------------------------------------

    def average_delta(self):

        if self.count() == 0:

            return 0.0

        return (

            sum(

                profile.delta

                for profile in self.all()

            )

            / self.count()

        )

    # ==================================================

    def reset(self):

        self.clear()