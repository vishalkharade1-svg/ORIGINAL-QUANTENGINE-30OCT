"""
====================================================

Exchange Registry

====================================================
"""


class ExchangeRegistry:

    def __init__(self):

        self._exchanges = {}

    # -------------------------------------------------

    def register(self, name, exchange):

        self._exchanges[name.upper()] = exchange

    # -------------------------------------------------

    def get(self, name):

        return self._exchanges.get(name.upper())

    # -------------------------------------------------

    def all(self):

        return self._exchanges