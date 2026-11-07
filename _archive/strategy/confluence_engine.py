"""
====================================================

QuantEngine

Sprint 5

Dynamic Confluence Engine

====================================================
"""

from strategy.signal import TradeSignal


class ConfluenceEngine:

    def __init__(self, weights):
        self.weights = weights

    def evaluate(self, **signals):

        score = 0
        reasons = []

        for name, active in signals.items():

            if not active:
                continue

            weight = self.weights.get(name, 0)

            score += weight

            reasons.append(name.upper())

        if score >= 80:
            confidence = "VERY HIGH"
        elif score >= 60:
            confidence = "HIGH"
        elif score >= 40:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if score >= 60:
            direction = "BUY"
        elif score <= 20:
            direction = "SELL"
        else:
            direction = "NONE"

        return TradeSignal(
            direction=direction,
            score=score,
            confidence=confidence,
            reasons=reasons,
        )