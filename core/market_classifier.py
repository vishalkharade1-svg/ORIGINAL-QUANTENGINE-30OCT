"""
====================================================

QuantEngine

Sprint 6

Market Classifier

====================================================
"""

from core.market_state_type import MarketStateType


class MarketClassifier:

    def classify(

        self,

        ema20,

        ema50,

        atr,

    ):

        if ema20 > ema50:

            trend = MarketStateType.TREND_UP

        elif ema20 < ema50:

            trend = MarketStateType.TREND_DOWN

        else:

            trend = MarketStateType.RANGE

        if atr > 100:

            volatility = MarketStateType.HIGH_VOLATILITY

        else:

            volatility = MarketStateType.LOW_VOLATILITY

        return trend, volatility