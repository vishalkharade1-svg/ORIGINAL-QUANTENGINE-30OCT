"""
====================================================

QuantEngine

Institutional Mitigation Scanner

Creates institutional mitigation blocks from
valid Order Blocks.

====================================================
"""

from core.common.base_scanner import BaseScanner

from core.mitigation.mitigation_block import MitigationBlock
from core.mitigation.mitigation_registry import MitigationRegistry
from core.mitigation.mitigation_score import MitigationScore


class MitigationScanner(BaseScanner):

    def __init__(self):

        super().__init__(

            registry=MitigationRegistry(),

        )

        self.scorer = MitigationScore()

    # ==================================================

    def scan(

        self,

        order_block_registry,

    ):

        self.reset()

        if (

            order_block_registry is None

            or order_block_registry.count() == 0

        ):

            return self.result()

        # -------------------------------------------------

        for i, block in enumerate(

            order_block_registry.all()

        ):

            # Ignore invalid blocks

            if block.invalidated:

                continue

            # Only blocks that have been touched
            # become mitigation blocks

            if block.touches <= 0:

                continue

            mitigation = MitigationBlock(

                index=block.index,

                timestamp=block.timestamp,

                timeframe=getattr(

                    block,

                    "timeframe",

                    "",

                ),

                direction=block.direction,

                high=block.high,

                low=block.low,

                source_order_block=i,

                source_fvg=getattr(

                    block,

                    "fvg_index",

                    -1,

                ),

                touches=block.touches,

            )

            # -----------------------------------------
            # Score
            # -----------------------------------------

            mitigation.score = block.score

            self.scorer.calculate(

                mitigation,

            )

            self.registry.add(

                mitigation,

            )

        return self.result()