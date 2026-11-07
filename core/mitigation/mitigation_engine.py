"""
====================================================

QuantEngine

Mitigation Engine

Pipeline adapter that runs the MitigationScanner as a
pipeline stage so context.mitigations actually reaches
RegimeEngine (which otherwise reads None and scores the
mitigation sub-score at 0 forever).

Consumes:
    context.order_blocks

Produces:
    context.mitigations (core.mitigation.mitigation_registry.MitigationRegistry)

The scanner itself keeps its standalone .scan(order_blocks)
API (core/mitigation/mitigation_scanner.py); this engine
only bridges it into the BaseEngine lifecycle.

====================================================
"""

from core.common.base_engine import BaseEngine

from core.mitigation.mitigation_scanner import MitigationScanner


class MitigationEngine(BaseEngine):

    priority = 331

    dependencies = [
        "OrderBlockScanner",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.scanner = MitigationScanner()

    # -------------------------------------------------

    def analyze(self, context):

        order_blocks = context.order_blocks

        if order_blocks is None or order_blocks.count() == 0:

            self.scanner.reset()

            context.mitigations = self.scanner.registry

            return

        context.mitigations = self.scanner.scan(
            order_blocks,
        )

    # -------------------------------------------------

    def reset(self):

        self.scanner.reset()