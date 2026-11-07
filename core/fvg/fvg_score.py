"""
====================================================

QuantEngine

Institutional Fair Value Gap Score

====================================================
"""


class FVGScore:

    def __init__(

        self,

        max_score=100.0,

    ):

        self.max_score = max_score

    # ==================================================

    def calculate(

        self,

        gap,

    ):

        score = 0.0

        metadata = {}

        # -------------------------------------------------
        # Gap Size
        # -------------------------------------------------

        gap_score = min(

            gap.size * 25.0,

            35.0,

        )

        score += gap_score

        metadata["gap_size_score"] = gap_score

        # -------------------------------------------------
        # Displacement
        # -------------------------------------------------

        displacement_score = min(

            gap.displacement_strength * 0.50,

            35.0,

        )

        score += displacement_score

        metadata["displacement_score"] = displacement_score

        # -------------------------------------------------
        # Volume
        # -------------------------------------------------

        volume_score = min(

            gap.volume_ratio * 10.0,

            15.0,

        )

        score += volume_score

        metadata["volume_score"] = volume_score

        # -------------------------------------------------
        # Fresh Gap
        # -------------------------------------------------

        freshness_score = (

            10.0

            if not gap.filled

            else 0.0

        )

        score += freshness_score

        metadata["freshness_score"] = freshness_score

        # -------------------------------------------------
        # Valid Gap
        # -------------------------------------------------

        validity_score = (

            5.0

            if not gap.invalidated

            else 0.0

        )

        score += validity_score

        metadata["validity_score"] = validity_score

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

        gap.metadata.update(

            metadata,

        )

        gap.score = final_score

        gap.institutional_score = final_score

        return final_score

    # ==================================================
    # Backward Compatibility
    # ==================================================

    def score(

        self,

        gap,

    ):

        return self.calculate(

            gap,

        )