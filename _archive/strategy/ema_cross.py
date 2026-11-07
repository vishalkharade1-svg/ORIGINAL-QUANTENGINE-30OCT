"""
====================================================

QuantEngine

Build : 3.2

EMA Cross Strategy

====================================================
"""

from signals.signal import Signal
from strategy.base import Strategy


class EMACrossStrategy(Strategy):

    def __init__(self):

        super().__init__("EMA Cross")

    def evaluate(self, candle, indicators):

        ema20 = indicators["ema20"]
        ema50 = indicators["ema50"]

        if ema20 is None or ema50 is None:

            return Signal(
                action="HOLD",
                strategy=self.name,
                confidence=0.0,
                reason="Indicators not ready",
            )

        if ema20 > ema50:

            return Signal(
                action="BUY",
                strategy=self.name,
                confidence=0.75,
                reason="EMA20 above EMA50",
                price=candle.close if candle else None,
                timestamp=candle.timestamp if candle else None,
            )

        if ema20 < ema50:

            return Signal(
                action="SELL",
                strategy=self.name,
                confidence=0.75,
                reason="EMA20 below EMA50",
                price=candle.close if candle else None,
                timestamp=candle.timestamp if candle else None,
            )

        return Signal(
            action="HOLD",
            strategy=self.name,
            confidence=0.0,
            reason="No signal",
        )