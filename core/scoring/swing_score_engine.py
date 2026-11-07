"""
====================================================

QuantEngine

Institutional Swing Score Engine

====================================================
"""

from core.objects.market_object import MarketObject
from core.scoring.score_engine import ScoreEngine

# Maximum raw score currently available from the component budget:
#
#   atr_score      <= 20
#   volume_score   <= 15
#   time_score     =  5
#   liquidity_score = 0   (placeholder, always 0 in production)
#   bos_score       = 0   (placeholder, always 0 in production)
#   htf_score       = 0   (placeholder, always 0 in production)
#                       ----------
#                     max 40
#
# ScoreEngine.score() already clamps to 0..100, but the components
# only sum to 40 -- without normalizing here a swing could never
# exceed a score of 40, so `swing.institutional` (threshold 70 in
# SwingEngine) was structurally UNREACHABLE and always False even
# for a perfect impulse+volume swing. Normalizing to 0..100 makes
# the threshold meaningful and consistent with every other
# component score scale (displacement, FVG, OB, regime all use
# 0..100 with ~70 thresholds).
SWING_SCORE_BUDGET = 40.0


class SwingScoreEngine(ScoreEngine):

    def calculate(

        self,

        swing: MarketObject,

    ) -> float:

        score = 0.0

        # ATR Expansion

        score += swing.metadata.get(

            "atr_score",

            0,

        )

        # Volume Expansion

        score += swing.metadata.get(

            "volume_score",

            0,

        )

        # Liquidity

        score += swing.metadata.get(

            "liquidity_score",

            0,

        )

        # BOS

        score += swing.metadata.get(

            "bos_score",

            0,

        )

        # HTF

        score += swing.metadata.get(

            "htf_score",

            0,

        )

        # Time

        score += swing.metadata.get(

            "time_score",

            0,

        )

        return (score / SWING_SCORE_BUDGET) * 100.0