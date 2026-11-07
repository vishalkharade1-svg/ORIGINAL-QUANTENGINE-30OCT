"""
====================================================

Institutional Regime Engine

Pipeline Native

Consumes:
    context.trend
    context.market_structure
    context.indicators
    context.displacement
    context.fvgs
    context.order_blocks
    context.breakers
    context.mitigations

Produces:
    context.regime

====================================================
"""

from core.common.base_engine import BaseEngine
from core.regime.regime_state import RegimeState


class RegimeEngine(BaseEngine):

    priority = 500

    dependencies = [
        "IndicatorEngine",
        "TrendEngine",
        "MarketStructureEngine",
        "DisplacementScanner",
        "FVGScanner",
        "OrderBlockScanner",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.state = RegimeState()

    # -------------------------------------------------

    def analyze(self, context):

        # ---------------------------------------------
        # Reset State
        # ---------------------------------------------

        self.state = RegimeState()
        state = self.state

        # ---------------------------------------------
        # Pipeline Inputs
        # ---------------------------------------------

        trend = context.trend
        market_structure = context.market_structure
        indicators = context.indicators
        displacement = context.displacement
        fvgs = context.fvgs
        order_blocks = context.order_blocks
        breakers = context.breakers
        mitigations = context.mitigations

        # ---------------------------------------------
        # Trend
        # ---------------------------------------------

        if trend is not None:

            state.trend = trend.direction

            if trend.direction in ("BULLISH", "BEARISH"):

                state.trend_score = 15

            elif trend.direction == "RANGE":

                state.trend_score = 8

            # else: WARMUP / UNKNOWN -- no trend observation yet,
            # trend_score stays at its default (0). Do not treat
            # this the same as a genuine RANGE reading.

        # ---------------------------------------------
        # Market Structure
        # ---------------------------------------------

        if market_structure is not None:

            if market_structure.bos:

                state.structure_score += 8

            if market_structure.choch:

                state.structure_score += 7

        # ---------------------------------------------
        # Indicators
        # ---------------------------------------------

        adx = None
        atr = None

        if indicators is not None:

            adx = indicators.latest("ADX_14")
            atr = indicators.latest("ATR_14")

        # ---------------------------------------------
        # Momentum
        # ---------------------------------------------

        if adx is not None:

            if adx >= 35:

                state.momentum_score = 15
                state.momentum = "VERY_STRONG"

            elif adx >= 25:

                state.momentum_score = 10
                state.momentum = "STRONG"

            elif adx >= 20:

                state.momentum_score = 6
                state.momentum = "MODERATE"

            else:

                state.momentum_score = 2
                state.momentum = "WEAK"

        # ---------------------------------------------
        # Volatility
        # ---------------------------------------------

        if atr is not None and atr > 0:

            state.volatility_score = 10
            state.volatility = "HIGH"

        # ---------------------------------------------
        # Displacement
        # ---------------------------------------------

        if displacement is not None:

            strong = len(displacement.strong())

            state.displacement_score = min(
                strong * 3,
                15,
            )

        # ---------------------------------------------
        # Fair Value Gaps
        # ---------------------------------------------

        if fvgs is not None:

            active = len(fvgs.active())

            state.fvg_score = min(
                active * 3,
                10,
            )

        # ---------------------------------------------
        # Order Blocks
        # ---------------------------------------------

        if order_blocks is not None:

            active = len(order_blocks.active())

            state.order_block_score = min(
                active * 5,
                10,
            )

        # ---------------------------------------------
        # Breakers
        # ---------------------------------------------

        if breakers is not None:

            state.breaker_score = min(
                breakers.count() * 2,
                5,
            )

        # ---------------------------------------------
        # Mitigations
        # ---------------------------------------------

        if mitigations is not None:

            state.mitigation_score = min(
                mitigations.count() * 2,
                5,
            )

        # ---------------------------------------------
        # Liquidity
        # ---------------------------------------------

        if market_structure is not None:

            if market_structure.bos:

                state.liquidity_score += 5

            if market_structure.choch:

                state.liquidity_score += 5

        # ---------------------------------------------
        # Final Score
        # ---------------------------------------------

        state.score = (

            state.trend_score
            + state.structure_score
            + state.momentum_score
            + state.volatility_score
            + state.liquidity_score
            + state.displacement_score
            + state.fvg_score
            + state.order_block_score
            + state.breaker_score
            + state.mitigation_score

        )

        state.confidence = state.score

        # ---------------------------------------------
        # Warmup Gate
        #
        # During warmup, every sub-score is legitimately 0
        # (no trend reading, no structure, no displacement
        # history yet) which would otherwise fall straight
        # into the score < 40 => "DEAD" bucket below. That is
        # a false signal: DEAD should mean "the market has no
        # activity", not "we have no data yet". Insufficient
        # history is reported as its own state instead.
        # ---------------------------------------------

        if trend is None or trend.direction == "WARMUP":

            state.grade = "N/A"
            state.regime = "WARMUP"

            context.regime = state

            return state

        # ---------------------------------------------
        # Grade
        # ---------------------------------------------

        if state.score >= 95:

            state.grade = "A+"
            state.regime = "INSTITUTIONAL_TREND"

        elif state.score >= 85:

            state.grade = "A"
            state.regime = "STRONG_TREND"

        elif state.score >= 70:

            state.grade = "B"
            state.regime = "TRENDING"

        elif state.score >= 55:

            state.grade = "C"
            state.regime = "TRANSITION"

        elif state.score >= 40:

            state.grade = "D"
            state.regime = "RANGE"

        else:

            state.grade = "F"
            state.regime = "DEAD"

        # ---------------------------------------------
        # Publish
        # ---------------------------------------------

        context.regime = state

        return state

    # -------------------------------------------------

    def reset(self):

        self.state = RegimeState()