"""
====================================================

QuantEngine

Breaker Engine

Pipeline adapter that runs the BreakerScanner as a
pipeline stage so context.breakers actually reaches
RegimeEngine (which otherwise reads None and scores the
breaker sub-score at 0 forever).

Consumes:
    context.order_blocks

Produces:
    context.breakers (core.breaker.breaker_registry.BreakerRegistry)

The scanner itself keeps its standalone .scan(order_blocks)
API (core/breaker/breaker_scanner.py); this engine only
bridges it into the BaseEngine lifecycle.

====================================================
"""

from core.common.base_engine import BaseEngine

from core.breaker.breaker_scanner import BreakerScanner


class BreakerEngine(BaseEngine):

    priority = 330

    dependencies = [
        "OrderBlockScanner",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.scanner = BreakerScanner()

    # -------------------------------------------------

    def analyze(self, context):

        order_blocks = context.order_blocks

        if order_blocks is None or order_blocks.count() == 0:

            self.scanner.reset()

            context.breakers = self.scanner.registry

            return

        context.breakers = self.scanner.scan(
            order_blocks,
        )

    # -------------------------------------------------

    def reset(self):

        self.scanner.reset()