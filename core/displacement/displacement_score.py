"""
====================================================

QuantEngine

Institutional Displacement Score

Version 2.0

====================================================
"""


class DisplacementScore:

    def __init__(self):

        self.max_score = 100.0

    # ==================================================

    def calculate(self, d):

        score = 0.0

        # -------------------------------------------------
        # 1. Candle Body (20)
        # -------------------------------------------------

        body_score = min(
            d.body_ratio * 20.0,
            20.0,
        )

        score += body_score

        # -------------------------------------------------
        # 2. ATR Expansion (20)
        # -------------------------------------------------

        atr_score = min(
            d.atr_multiple * 12.0,
            20.0,
        )

        score += atr_score

        # -------------------------------------------------
        # 3. Relative Volume (15)
        # -------------------------------------------------

        volume_score = min(
            d.volume_ratio * 10.0,
            15.0,
        )

        score += volume_score

        # -------------------------------------------------
        # 4. Close Position (15)
        # -------------------------------------------------

        close_score = d.close_position * 15.0

        score += close_score

        # -------------------------------------------------
        # 5. Structure Break (15)
        # -------------------------------------------------

        structure_score = 0.0

        if d.broke_previous_high:

            structure_score += 7.5

        if d.broke_previous_low:

            structure_score += 7.5

        score += structure_score

        # -------------------------------------------------
        # 6. Consecutive Impulse (10)
        # -------------------------------------------------

        momentum_score = min(
            d.consecutive_impulse * 5.0,
            10.0,
        )

        score += momentum_score

        # -------------------------------------------------
        # 7. Liquidity Sweep Bonus (5)
        # -------------------------------------------------

        sweep_score = 5.0 if d.liquidity_sweep else 0.0

        score += sweep_score

        # -------------------------------------------------
        # Final
        # -------------------------------------------------

        final = round(
            min(score, self.max_score),
            2,
        )

        d.body_score = body_score
        d.atr_score = atr_score
        d.volume_score = volume_score
        d.close_score = close_score
        d.structure_score = structure_score
        d.momentum_score = momentum_score

        d.score = final
        d.institutional_score = final

        # -------------------------------------------------
        # Grade
        # -------------------------------------------------

        if final >= 90:

            d.grade = "ELITE"

        elif final >= 75:

            d.grade = "STRONG"

        elif final >= 60:

            d.grade = "MODERATE"

        else:

            d.grade = "WEAK"

        d.strong = final >= 75

        # -------------------------------------------------
        # Debug Metadata
        # -------------------------------------------------

        d.metadata.update({

            "body_score": body_score,

            "atr_score": atr_score,

            "volume_score": volume_score,

            "close_score": close_score,

            "structure_score": structure_score,

            "momentum_score": momentum_score,

            "sweep_score": sweep_score,

            "grade": d.grade,

            "final_score": final,

        })

        return final

    # ==================================================

    def score(self, displacement):

        return self.calculate(displacement)