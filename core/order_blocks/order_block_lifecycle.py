"""
====================================================

QuantEngine

Institutional Order Block Lifecycle

Maintains Order Block state after creation.

====================================================
"""


class OrderBlockLifecycle:

    def update(

        self,

        bars,

        registry,

        current_bar=None,

    ):

        if registry.count() == 0:

            return registry

        for block in registry.active():

            self._update_block(

                block,

                bars,

                current_bar=current_bar,

            )

        return registry

    # ==================================================

    def _update_block(

        self,

        block,

        bars,

        current_bar=None,

    ):

        start = min(

            block.index + 1,

            len(bars),

        )

        for candle in bars[start:]:

            # -----------------------------------------
            # Bullish Order Block
            # -----------------------------------------

            if block.direction == "BULLISH":

                if (

                    candle.low <= block.high

                    and candle.high >= block.low

                ):

                    block.touch()

                    block.last_tested_timestamp = candle.timestamp

                    if current_bar is not None:

                        block.last_tested_bar = current_bar

                # Complete invalidation

                if candle.close < block.low:

                    block.mark_mitigated(

                        candle.timestamp,

                    )

                    block.active = False

                    break

            # -----------------------------------------
            # Bearish Order Block
            # -----------------------------------------

            else:

                if (

                    candle.high >= block.low

                    and candle.low <= block.high

                ):

                    block.touch()

                    block.last_tested_timestamp = candle.timestamp

                    if current_bar is not None:

                        block.last_tested_bar = current_bar

                # Complete invalidation

                if candle.close > block.high:

                    block.mark_mitigated(

                        candle.timestamp,

                    )

                    block.active = False

                    break