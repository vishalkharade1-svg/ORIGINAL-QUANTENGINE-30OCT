"""
====================================================

Institutional Breaker Scanner

====================================================
"""

from core.common.base_scanner import BaseScanner

from core.breaker.breaker_block import BreakerBlock
from core.breaker.breaker_registry import BreakerRegistry
from core.breaker.breaker_score import BreakerScore


class BreakerScanner(BaseScanner):

    def __init__(self):

        super().__init__(registry=BreakerRegistry())

        self.score = BreakerScore()

    # -------------------------------------------------

    def scan(

        self,

        order_blocks,

    ):

        self.reset()

        for i, block in enumerate(

            order_blocks.mitigated()

        ):

            breaker = BreakerBlock(

                index=block.index,

                timestamp=block.timestamp,

                direction=block.direction,

                high=block.high,

                low=block.low,

                score=self.score.calculate(

                    block.score,

                ),

                source_order_block=i,

            )

            self.registry.add(breaker)

        return self.result()