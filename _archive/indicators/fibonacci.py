"""
====================================================

QuantEngine

Sprint 8

Fibonacci Retracement

====================================================
"""


class Fibonacci:

    RATIOS = {

        "0.236": 0.236,
        "0.382": 0.382,
        "0.500": 0.500,
        "0.618": 0.618,
        "0.786": 0.786,

    }

    def calculate(self, high, low):

        diff = high - low

        levels = {}

        for name, ratio in self.RATIOS.items():

            levels[name] = high - diff * ratio

        return levels