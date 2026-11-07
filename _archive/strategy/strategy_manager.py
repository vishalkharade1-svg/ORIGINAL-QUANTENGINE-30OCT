"""
====================================================

QuantEngine

Sprint 5

Strategy Manager

====================================================
"""

from strategy.strategy import Strategy

from strategy.weights import (
    ICT,
    SWING,
    SCALPING,
)


class StrategyManager:

    def __init__(self):

        self.strategies = {

            "ICT": Strategy(

                name="ICT",

                weights=ICT,

                enabled=[
                    "bos",
                    "choch",
                    "orderblock",
                    "fvg",
                    "liquidity",
                    "displacement",
                ],

                risk=0.01,

            ),

            "SWING": Strategy(

                name="SWING",

                weights=SWING,

                enabled=[
                    "bos",
                    "orderblock",
                    "ema",
                ],

                risk=0.02,

            ),

            "SCALPING": Strategy(

                name="SCALPING",

                weights=SCALPING,

                enabled=[
                    "ema",
                    "liquidity",
                    "fvg",
                ],

                risk=0.005,

            ),

        }

    def get(self, name):

        return self.strategies[name]