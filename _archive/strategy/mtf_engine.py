"""
====================================================

QuantEngine

Sprint 5

Multi-Timeframe Confluence Engine

====================================================
"""

from strategy.timeframe_signal import TimeframeSignal


class MultiTimeframeEngine:

    def evaluate(self, signals):

        buy = 0
        sell = 0

        for signal in signals:

            if signal.direction == "BUY":
                buy += signal.score

            elif signal.direction == "SELL":
                sell += signal.score

        if buy > sell:

            direction = "BUY"
            score = buy

        elif sell > buy:

            direction = "SELL"
            score = sell

        else:

            direction = "NONE"
            score = 0

        if score >= 350:

            confidence = "VERY HIGH"

        elif score >= 250:

            confidence = "HIGH"

        elif score >= 150:

            confidence = "MEDIUM"

        else:

            confidence = "LOW"

        return TimeframeSignal(

            timeframe="MTF",

            direction=direction,

            score=score,

            confidence=confidence,

        )