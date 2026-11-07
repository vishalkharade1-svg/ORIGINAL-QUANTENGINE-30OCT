"""
====================================================

QuantEngine

Institutional Fair Value Gap Lifecycle

Maintains the lifecycle of Institutional
Fair Value Gaps.

====================================================
"""


class FVGLifecycle:

    # ==================================================

    def update(

        self,

        bars,

        registry,

    ):

        if registry.count() == 0:

            return registry

        for gap in registry.active():

            self._update_gap(

                gap,

                bars,

            )

        return registry

    # ==================================================

    def _update_gap(

        self,

        gap,

        bars,

    ):

        start = min(

            gap.index + 1,

            len(bars),

        )

        for candle in bars[start:]:

            # -----------------------------------------
            # Bullish FVG
            # -----------------------------------------

            if gap.direction == "BULLISH":

                # Partial fill

                if (

                    candle.low < gap.upper

                    and candle.low > gap.lower

                ):

                    percent = (

                        (gap.upper - candle.low)

                        / gap.size

                    ) * 100

                    gap.mark_partial(

                        percent,

                    )

                # Completely filled

                if candle.low <= gap.lower:

                    gap.mark_filled(

                        candle.timestamp,

                    )

                    break

            # -----------------------------------------
            # Bearish FVG
            # -----------------------------------------

            else:

                # Partial fill

                if (

                    candle.high > gap.lower

                    and candle.high < gap.upper

                ):

                    percent = (

                        (candle.high - gap.lower)

                        / gap.size

                    ) * 100

                    gap.mark_partial(

                        percent,

                    )

                # Completely filled

                if candle.high >= gap.upper:

                    gap.mark_filled(

                        candle.timestamp,

                    )

                    break