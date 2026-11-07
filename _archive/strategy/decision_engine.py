"""
====================================================

QuantEngine

Sprint 6

Trade Decision Engine

====================================================
"""

from strategy.decision import TradeDecision


class TradeDecisionEngine:

    def decide(self, signal, strategy):

        if signal.score >= 80:

            action = "BUY"

        elif signal.score <= 20:

            action = "SELL"

        else:

            action = "HOLD"

        return TradeDecision(

            action=action,

            confidence=signal.confidence,

            score=signal.score,

            reasons=signal.reasons,

            strategy=strategy.name,

        )