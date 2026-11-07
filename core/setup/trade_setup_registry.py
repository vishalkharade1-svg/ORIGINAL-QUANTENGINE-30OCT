"""
====================================================

Trade Setup Registry

====================================================
"""

from core.common.registry import Registry


class TradeSetupRegistry(Registry):

    def bullish(self):

        return [

            s

            for s in self.all()

            if s.direction == "BULLISH"

        ]

    # -------------------------------------------------

    def bearish(self):

        return [

            s

            for s in self.all()

            if s.direction == "BEARISH"

        ]

    # -------------------------------------------------

    def high_confidence(self):

        return [

            s

            for s in self.all()

            if s.confidence >= 80

        ]