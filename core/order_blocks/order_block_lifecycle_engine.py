"""
====================================================

QuantEngine

Order Block Lifecycle Engine

Pipeline adapter that runs the OrderBlockLifecycle as a
pipeline stage so order blocks actually get touched /
mitigated before the Breaker and Mitigation stages run.

Consumes:
    context.candles
    context.order_blocks (just minted by OrderBlockScanner
    at priority 320)

Produces:
    context.order_blocks (lifecycle state updated in place)

The lifecycle itself keeps its standalone
.update(bars, registry) API
(core/order_blocks/order_block_lifecycle.py); this engine
only bridges it into the BaseEngine lifecycle.

====================================================
"""

from core.common.base_engine import BaseEngine

from core.order_blocks.order_block_lifecycle import OrderBlockLifecycle
from core.order_blocks.order_block_scanner import OrderBlockScanner


class OrderBlockLifecycleEngine(BaseEngine):

    priority = 325

    dependencies = [
        "OrderBlockScanner",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.lifecycle = OrderBlockLifecycle()

    # -------------------------------------------------

    def analyze(self, context):

        registry = context.order_blocks

        if registry is None or registry.count() == 0:

            return

        self.lifecycle.update(
            list(context.candles),
            registry,
            current_bar=getattr(context, "current_index", None),
        )

    # -------------------------------------------------

    def reset(self):

        pass