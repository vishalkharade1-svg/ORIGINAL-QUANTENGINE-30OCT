"""
====================================================

QuantEngine

Institutional Liquidity Score

Scores Liquidity Pools

====================================================
"""


class LiquidityScore:

    def __init__(

        self,

        max_score=100.0,

    ):

        self.max_score = max_score

    # ==================================================

    def calculate(

        self,

        pool,

        bars,

        current_price,

    ):

        score = 0.0

        metadata = {}

        # -------------------------------------------------
        # Touch Score
        # -------------------------------------------------

        touch_score = min(

            pool.touches * 15.0,

            45.0,

        )

        score += touch_score

        metadata["touch_score"] = touch_score

        # -------------------------------------------------
        # Distance Score
        # -------------------------------------------------

        distance = abs(

            current_price - pool.price

        )

        metadata["distance"] = distance

        if current_price <= 0:

            distance_score = 0.0

        else:

            percent = (

                distance

                / current_price

            ) * 100.0

            metadata["distance_percent"] = percent

            if percent < 0.20:

                distance_score = 25.0

            elif percent < 0.50:

                distance_score = 18.0

            elif percent < 1.00:

                distance_score = 10.0

            else:

                distance_score = 0.0

        score += distance_score

        metadata["distance_score"] = distance_score

        # -------------------------------------------------
        # Fresh Liquidity
        # -------------------------------------------------

        freshness_score = (

            15.0

            if pool.active

            else 0.0

        )

        score += freshness_score

        metadata["freshness_score"] = freshness_score

        # -------------------------------------------------
        # Institutional Bonus
        # -------------------------------------------------

        institutional_score = 0.0

        if getattr(

            pool,

            "strength",

            0.0,

        ) >= 1.0:

            institutional_score = 15.0

        score += institutional_score

        metadata["institutional_score"] = institutional_score

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

        pool.metadata.update(

            metadata

        )

        pool.score = final_score

        return final_score

    # ==================================================
    # Backward Compatibility
    # ==================================================

    def score(

        self,

        pool,

        bars,

        current_price,

    ):

        return self.calculate(

            pool,

            bars,

            current_price,

        )