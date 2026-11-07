"""
====================================================

Regime Score

====================================================
"""


class RegimeScore:

    def calculate(

        self,

        trend,

        structure,

        adx,

        atr,

    ):

        score = 0

        if trend.ema_alignment:
            score += 25

        if trend.adx_confirmed:
            score += 25

        if structure.bos:
            score += 25

        if atr is not None:
            score += 25

        return min(score, 100)