"""
====================================================

Institutional Confluence Engine

====================================================
"""

from core.confluence.confluence import Confluence


class ConfluenceEngine:
    """
    Institutional Confluence Engine

    Collects evidence from all analysis engines and
    produces a normalized confidence score.

    Existing inputs are fully supported.

    Future modules (Footprint, Volume Profile,
    Fibonacci, Gann, Wyckoff, ICT, AI etc.)
    can contribute without changing this engine.
    """

    DEFAULT_WEIGHTS = {

        "trend": 20,

        "regime": 15,

        "structure_bos": 20,

        "structure_choch": 15,

        "liquidity": 20,

        "institutional": 10,

    }

    # -------------------------------------------------

    def __init__(self):

        self.weights = self.DEFAULT_WEIGHTS.copy()

    # -------------------------------------------------

    def analyze(

        self,

        trend,

        regime,

        structure,

        liquidity_target,

        extra_factors=None,

    ):

        result = Confluence()

        score = 0

        # --------------------------------------------
        # Trend
        # --------------------------------------------

        if trend is not None:

            if getattr(trend, "direction", None) == "BULLISH":

                score += self.weights["trend"]

                result.bullish = True

                result.reasons.append("Bullish trend")

            elif getattr(trend, "direction", None) == "BEARISH":

                score += self.weights["trend"]

                result.bearish = True

                result.reasons.append("Bearish trend")

        # --------------------------------------------
        # Market Regime
        # --------------------------------------------

        if regime is not None:

            if getattr(regime, "regime", None) == "TRENDING":

                score += self.weights["regime"]

                result.reasons.append("Trending market")

        # --------------------------------------------
        # Structure
        # --------------------------------------------

        if structure is not None:

            if getattr(structure, "bos", False):

                score += self.weights["structure_bos"]

                result.reasons.append("BOS confirmed")

            if getattr(structure, "choch", False):

                score += self.weights["structure_choch"]

                result.reasons.append("CHoCH confirmed")

        # --------------------------------------------
        # Liquidity
        # --------------------------------------------

        if liquidity_target is not None:

            score += self.weights["liquidity"]

            result.reasons.append(
                f"Targeting {liquidity_target.side} liquidity"
            )

        # --------------------------------------------
        # Future Institutional Factors
        #
        # Example:
        #
        # {
        #     "Footprint": (8, "Stacked bid imbalance"),
        #     "Fibonacci": (6, "OTE retracement"),
        #     "VolumeProfile": (5, "POC rejection")
        # }
        # --------------------------------------------

        if extra_factors:

            for _, value in extra_factors.items():

                if not value:
                    continue

                weight, reason = value

                score += weight

                if reason:
                    result.reasons.append(reason)

        # --------------------------------------------

        result.score = max(0, min(score, 100))

        return result