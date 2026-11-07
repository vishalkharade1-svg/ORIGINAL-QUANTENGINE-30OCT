"""
====================================================

QuantEngine

Build : 2.4
Module: Indicator Manager

Coordinates all indicators and updates them whenever
a new candle closes.

====================================================
"""

from indicators.ema import EMA


class IndicatorManager:

    def __init__(self):

        # Trend Indicators
        self.ema9 = EMA(9)
        self.ema20 = EMA(20)
        self.ema50 = EMA(50)
        self.ema200 = EMA(200)

    def on_new_candle(self, candle):
        """
        Called whenever a candle closes.
        """

        close = candle.close

        self.ema9.update(close)
        self.ema20.update(close)
        self.ema50.update(close)
        self.ema200.update(close)

    def snapshot(self):
        """
        Returns the latest indicator values.
        """

        return {
            "ema9": self.ema9.last(),
            "ema20": self.ema20.last(),
            "ema50": self.ema50.last(),
            "ema200": self.ema200.last(),
        }

    def ready(self):
        """
        True when long-term indicators are ready.
        """

        return self.ema200.ready()