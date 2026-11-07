"""
====================================================

Contract Registry

====================================================
"""

class ContractRegistry:

    def __init__(self):

        self.contracts = {}

    # -------------------------------------------------

    def add(self, contract):

        self.contracts[contract.symbol] = contract

    # -------------------------------------------------

    def get(self, symbol):

        return self.contracts.get(symbol)

    # -------------------------------------------------

    def exists(self, symbol):

        return symbol in self.contracts

    # -------------------------------------------------

    def all(self):

        return list(self.contracts.values())