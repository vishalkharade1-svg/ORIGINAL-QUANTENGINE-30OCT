"""
====================================================

QuantEngine

Institutional Swing Strength

====================================================
"""


class SwingStrength:

    def __init__(self):

        self.max_score = 100

    def score(self, bars, index):

        """
        Returns a strength score (0-100)
        for a detected swing.
        """

        score = 0

        current = bars[index]

        # -------------------------------------------------
        # Price displacement
        # -------------------------------------------------

        body = abs(current.close - current.open)

        candle_range = current.high - current.low

        if candle_range > 0:

            ratio = body / candle_range

            score += min(25, ratio * 25)

        # -------------------------------------------------
        # Large candle
        # -------------------------------------------------

        if candle_range > 20:

            score += 15

        # -------------------------------------------------
        # Wick rejection
        # -------------------------------------------------

        upper = current.high - max(current.open, current.close)

        lower = min(current.open, current.close) - current.low

        if upper > body:

            score += 10

        if lower > body:

            score += 10

        # -------------------------------------------------
        # Volume
        # -------------------------------------------------

        if hasattr(current, "volume"):

            if current.volume > 0:

                score += 20

        return min(score, 100)