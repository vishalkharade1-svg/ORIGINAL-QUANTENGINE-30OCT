"""
====================================================

QuantEngine

Sprint 6

Paper Trading Account

====================================================
"""


class PaperAccount:

    def __init__(self):

        self.orders = []

    def add(self, order):

        self.orders.append(order)

    def history(self):

        return self.orders