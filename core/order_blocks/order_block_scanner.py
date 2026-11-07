"""
====================================================

QuantEngine

Institutional Order Block Scanner

Pipeline Native

Consumes:
    context.candles
    context.displacement
    context.fvgs

Produces:
    context.order_blocks

====================================================
"""

from core.common.base_engine import BaseEngine

from core.order_blocks.order_block import OrderBlock
from core.order_blocks.order_block_registry import OrderBlockRegistry
from core.order_blocks.order_block_score import OrderBlockScore
from core.order_blocks.zone_freshness import (
    classify_freshness,
    max_order_block_age_bars,
)
from core.common.logging_config import get_logger

log = get_logger(__name__)


class OrderBlockScanner(BaseEngine):

    priority = 320

    dependencies = [
        "DisplacementScanner",
        "FVGScanner",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.registry = OrderBlockRegistry()

        self.scorer = OrderBlockScore()

    # ==================================================

    def _latest_atr(self, context):
        """
        ATR_14 from the canonical IndicatorCache when one is
        published; 0.0 in a scripted harness with no indicator
        stack (the ATR-normalized freshness axes then stay 0.0).
        """

        indicators = getattr(context, "indicators", None)

        if indicators is None:

            return 0.0

        try:

            return float(indicators.latest("ATR_14") or 0.0)

        except Exception:

            return 0.0

    # --------------------------------------------------

    def analyze(self, context):

        self.registry.clear()

        bars = list(context.candles)

        displacement_registry = context.displacement

        fvg_registry = context.fvgs

        if (
            len(bars) < 3
            or displacement_registry is None
            or fvg_registry is None
        ):

            context.order_blocks = self.registry
            return

        atr = self._latest_atr(context)

        # -------------------------------------------------
        # One Order Block per active FVG
        # -------------------------------------------------

        log.debug(
            "Order block scan: strong_displacements=%d active_fvgs=%d",
            len(displacement_registry.strong()),
            len(fvg_registry.active()),
        )

        for fvg in fvg_registry.active():

            log.debug("FVG %d %s", fvg.index, fvg.direction)

            displacement = self._find_displacement(

                displacement_registry,

                fvg,

            )

            log.debug("Matched displacement: %s", displacement is not None)

            if displacement is None:

                continue

            candle, origin_rel = self._find_origin_candle(

                bars,

                displacement,

            )

            log.debug("Origin candle found: %s", candle is not None)

            if candle is None:

                continue

            block = OrderBlock(

                index=displacement.index,

                timestamp=candle.timestamp,

                timeframe=context.market.timeframe,

                direction=displacement.direction,

                open=candle.open,

                high=candle.high,

                low=candle.low,

                close=candle.close,

                strength=displacement.score,

                displacement_strength=displacement.score,

                volume_ratio=getattr(

                    displacement,

                    "volume_ratio",

                    0.0,

                ),

                fvg_index=fvg.index,

            )

            # ------------------------------------------------
            # Phase 4G STEP 1-3: stamp the zone's structural
            # age + freshness snapshot for THIS candle. Blocks
            # are re-created every scan, so every field is a
            # re-derived measurement (never an accumulated counter).
            #
            #     age_bars           bars between the origin candle
            #                        (bars[origin_rel]) and the
            #                        current candle (bars[-1])
            #     origin_bar         absolute bar of the origin
            #                        candle (computed from the
            #                        replay index, so it is stable
            #                        across re-scans)
            #     created_bar        the absolute current bar
            #     freshness          derived FRESH/ACTIVE/TESTED/
            #                        MITIGATED/STALE/INVALIDATED
            #     distance_...       entry -> current close, points
            #                        and ATR multiples
            # ------------------------------------------------

            age_bars = (len(bars) - 1) - origin_rel

            current_ts = bars[-1].timestamp

            block.age_bars = max(0, age_bars)

            block.age_time_seconds = max(
                0, int(current_ts) - int(candle.timestamp)
            )

            block.origin_bar = context.replay_index - block.age_bars

            block.created_bar = context.replay_index

            block.freshness = classify_freshness(
                block,
                age_bars=block.age_bars,
                max_age_bars=max_order_block_age_bars(
                    context.market.timeframe
                ),
            )

            try:

                mark_price = float(
                    getattr(context.market, "mark_price", None)
                    or (bars[-1].close if bars else 0.0)
                    or 0.0
                )

            except (TypeError, ValueError):

                mark_price = float(getattr(bars[-1], "close", 0.0) or 0.0)

            block.distance_from_current_price = abs(
                float(block.entry) - mark_price
            )

            block.distance_from_current_price_atr = (
                block.distance_from_current_price / atr
                if atr and atr > 0
                else 0.0
            )

            self.scorer.calculate(block)

            self.registry.add(block)

            log.debug("Created OB: %s score=%.1f", block.direction, block.score)

        context.order_blocks = self.registry

        log.debug("Total order blocks: %d", len(self.registry.all()))

    # ==================================================

    def _find_displacement(

        self,

        registry,

        fvg,

    ):

        for event in registry.strong():

            if event.index == fvg.index:

                return event

        return None

    # --------------------------------------------------

    def _find_origin_candle(

        self,

        bars,

        displacement,

    ):

        start = max(

            0,

            displacement.index - 10,

        )

        if displacement.direction == "BULLISH":

            for i in range(

                displacement.index - 1,

                start - 1,

                -1,

            ):

                candle = bars[i]

                if candle.close < candle.open:

                    return candle, i

        else:

            for i in range(

                displacement.index - 1,

                start - 1,

                -1,

            ):

                candle = bars[i]

                if candle.close > candle.open:

                    return candle, i

        return None, None

    # ==================================================

    def reset(self):

        self.registry.clear()