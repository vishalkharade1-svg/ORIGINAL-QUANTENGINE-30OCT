"""
====================================================

Trade Registry

====================================================
"""


class TradeRegistry:

    def __init__(self):

        self._trades = []

    def add(self, trade):

        self._trades.append(trade)

    def all(self):

        return self._trades

    def clear(self):

        self._trades.clear()

    def count(self):

        return len(self._trades)

    def winners(self):

        return [

            t

            for t in self._trades

            if t.result == "WIN"

        ]

    def losers(self):

        return [

            t

            for t in self._trades

            if t.result == "LOSS"

        ]

    def open(self):

        return [

            t

            for t in self._trades

            if t.status == "OPEN"

        ]

    def closed(self):

        return [

            t

            for t in self._trades

            if t.status == "CLOSED"

        ]