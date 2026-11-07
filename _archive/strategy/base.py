"""
====================================================

QuantEngine

Build : 3.1
Module : Strategy Base Class

Every strategy inherits from this class.

====================================================
"""

from abc import ABC, abstractmethod


class Strategy(ABC):

    def __init__(self, name: str):

        self.name = name

    @abstractmethod
    def evaluate(self, candle, indicators):
        """
        Evaluate the latest market state.

        Returns:

            BUY
            SELL
            EXIT
            HOLD
        """

        pass