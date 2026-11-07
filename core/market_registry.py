"""
====================================================

QuantEngine

Build : 2.8
Module: Market Registry

Creates and stores all configured markets.

====================================================
"""

from config.settings import settings
from core.market import Market


class MarketRegistry:

    def __init__(self):

        self.markets = {}

        for symbol in settings.SYMBOLS:
            self.markets[symbol] = Market(symbol)

    def get(self, symbol: str):

        return self.markets.get(symbol)

    def all(self):

        return self.markets.values()


registry = MarketRegistry()