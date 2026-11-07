"""
====================================================

Market Structure Pipeline Stage

Legacy Adapter

====================================================
"""

from core.common.base_engine import BaseEngine
from core.market_structure.engine import MarketStructureEngine


class MarketStructureStage(BaseEngine):
    """
    Legacy adapter.

    Reads:
        context.structure_events
        context.bos
        context.choch
        context.trend
        context.swings

    Writes:
        context.market_structure
    """

    priority = 150

    enabled = True

    def __init__(self):

        super().__init__()

        self.engine = MarketStructureEngine()

    # -------------------------------------------------

    def analyze(self, context):

        self.engine.process(context)

        return context.market_structure

    # -------------------------------------------------

    def reset(self):

        self.engine.reset()