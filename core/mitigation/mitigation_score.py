"""
====================================================

QuantEngine

Institutional Mitigation Score

====================================================
"""


class MitigationScore:

    def __init__(

        self,

        max_score=100.0,

    ):

        self.max_score = max_score

    # ==================================================

    def calculate(

        self,

        mitigation,

    ):

        score = 0.0

        metadata = {}

        # -------------------------------------------------
        # Parent Order Block
        # -------------------------------------------------

        ob_score = min(

            mitigation.score,

            50.0,

        )

        score += ob_score

        metadata["order_block_score"] = ob_score

        # -------------------------------------------------
        # Touches
        # -------------------------------------------------

        touch_score = min(

            mitigation.touches * 5.0,

            20.0,

        )

        score += touch_score

        metadata["touch_score"] = touch_score

        # -------------------------------------------------
        # Fresh Mitigation
        # -------------------------------------------------

        freshness_score = (

            20.0

            if not mitigation.mitigated

            else 0.0

        )

        score += freshness_score

        metadata["freshness_score"] = freshness_score

        # -------------------------------------------------
        # Valid Block
        # -------------------------------------------------

        validity_score = (

            10.0

            if not mitigation.invalidated

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

        mitigation.metadata.update(

            metadata,

        )

        mitigation.score = final_score

        mitigation.institutional_score = final_score

        mitigation.strength = final_score

        return final_score

    # ==================================================
    # Backward Compatibility
    # ==================================================

    def score(

        self,

        mitigation,

    ):

        return self.calculate(

            mitigation,

        )