"""
====================================================

Breaker Registry

====================================================
"""

from core.common.registry import Registry


class BreakerRegistry(Registry):

    def active(self):

        return [

            breaker

            for breaker in self.all()

            if breaker.active

        ]

    # -------------------------------------------------

    def invalidated(self):

        return [

            breaker

            for breaker in self.all()

            if breaker.invalidated

        ]