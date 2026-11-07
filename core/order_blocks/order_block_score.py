"""
====================================================

QuantEngine

Institutional Order Block Score

====================================================
"""


class OrderBlockScore:

    def __init__(

        self,

        max_score=100.0,

    ):

        self.max_score = max_score

    # ==================================================

    def calculate(

        self,

        block,

    ):

        score = 0.0

        metadata = {}

        # -------------------------------------------------
        # Displacement
        # -------------------------------------------------

        displacement_score = min(

            block.displacement_strength * 0.40,

            40.0,

        )

        score += displacement_score

        metadata["displacement_score"] = displacement_score

        # -------------------------------------------------
        # Volume
        # -------------------------------------------------

        volume_score = min(

            block.volume_ratio * 10.0,

            15.0,

        )

        score += volume_score

        metadata["volume_score"] = volume_score

        # -------------------------------------------------
        # Fair Value Gap
        # -------------------------------------------------

        if block.fvg_index >= 0:

            fvg_score = 20.0

        else:

            fvg_score = 0.0

        score += fvg_score

        metadata["fvg_score"] = fvg_score

        # -------------------------------------------------
        # Fresh Block
        # -------------------------------------------------

        freshness_score = (

            15.0

            if not block.mitigated

            else 0.0

        )

        score += freshness_score

        metadata["freshness_score"] = freshness_score

        # -------------------------------------------------
        # Valid Block
        # -------------------------------------------------

        validity_score = (

            10.0

            if not block.invalidated

            else 0.0

        )

        score += validity_score

        metadata["validity_score"] = validity_score

        # -------------------------------------------------
        # Institutional Bonus
        # -------------------------------------------------

        institutional_bonus = min(

            block.strength,

            15.0,

        )

        score += institutional_bonus

        metadata["institutional_bonus"] = institutional_bonus

        # -------------------------------------------------
        # Final Score
        # -------------------------------------------------

        final_score = round(

            min(

                score,

                self.max_score,

            ),

            2,

        )

        metadata["final_score"] = final_score

        block.metadata.update(

            metadata

        )

        block.score = final_score

        return final_score

    # ==================================================
    # Backward Compatibility
    # ==================================================

    def score(

        self,

        block,

    ):

        return self.calculate(

            block,

        )