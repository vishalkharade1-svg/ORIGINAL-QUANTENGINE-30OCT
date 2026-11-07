"""
====================================================

Institutional Trend Score

====================================================
"""


class TrendScore:

    def calculate(
        self,
        state,
    ):

        score = 0

        # -------------------------------------------------
        # EMA Alignment
        # -------------------------------------------------

        if state.ema_alignment:

            score += 35

        # -------------------------------------------------
        # Price Position (direction-aware)
        # -------------------------------------------------

        # A perfect BULLISH trend earns price-position points
        # for price ABOVE every EMA. A perfect BEARISH trend
        # must earn the identical points for price BELOW every
        # EMA. Scoring only "price above the EMA" made an
        # equal-strength bearish trend score ~35 points lower
        # than a bullish one -- an unexplainable directional
        # bias that leaked into confidence/strength.
        #
        # RANGE/WARMUP earn no price-position points: in a
        # range, price sits around the EMAs by definition, so
        # being above/below one EMA is not trend strength.

        if state.direction == "BULLISH":

            if state.price_above_ema20:
                score += 10

            if state.price_above_ema50:
                score += 10

            if state.price_above_ema200:
                score += 15

        elif state.direction == "BEARISH":

            if state.price_below_ema20:
                score += 10

            if state.price_below_ema50:
                score += 10

            if state.price_below_ema200:
                score += 15

        # -------------------------------------------------
        # ADX Confirmation
        # -------------------------------------------------

        if state.adx_confirmed:

            score += 20

        # -------------------------------------------------
        # Momentum
        # -------------------------------------------------

        if state.momentum:

            score += 10

        return min(score, 100)